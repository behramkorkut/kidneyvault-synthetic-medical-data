"""Auto-amorçage de la couche analytique (pour les déploiements).

Sur un déploiement (Streamlit Community Cloud), le warehouse n'est pas committé
(discipline « aucune donnée dans Git »). Au premier démarrage, on génère la
couche Bronze puis on matérialise les modèles dbt — exactement comme le pipeline
local — pour que l'application fonctionne sans provisioning manuel.

Idempotent : si la couche Gold existe déjà, on ne refait rien.
"""

import os
from pathlib import Path

import duckdb

# Racine du dépôt (src/kidneyvault/bootstrap.py -> remonte de deux niveaux).
RACINE = Path(__file__).resolve().parents[2]
BASE = RACINE / "data" / "kidneyvault.duckdb"


def warehouse_pret() -> bool:
    """Vrai si le fichier DuckDB existe et contient la table Gold attendue."""
    if not BASE.exists():
        return False
    try:
        con = duckdb.connect(str(BASE), read_only=True)
        tables = {ligne[0] for ligne in con.execute("SHOW TABLES").fetchall()}
        con.close()
        return "gold_cohorte_patient" in tables
    except duckdb.Error:
        return False


def ensure_warehouse() -> None:
    """Construit Bronze + modèles dbt si le warehouse n'est pas déjà prêt.

    S'exécute depuis la racine du dépôt : les chemins relatifs de dbt
    (`--project-dir dbt`) et des sources Parquet (`data/01_bronze/...`) en
    dépendent. Le répertoire courant est restauré ensuite.
    """
    if warehouse_pret():
        return

    from kidneyvault.corrupteur import corrompre_eds
    from kidneyvault.generator import generer_eds
    from kidneyvault.persist import ecrire_bronze

    ancien_cwd = Path.cwd()
    os.chdir(RACINE)
    try:
        # 1. Couche Bronze : données synthétiques + défauts réalistes injectés
        tables = generer_eds()
        tables, _ = corrompre_eds(tables)
        ecrire_bronze(tables)

        # 2. Matérialisation des modèles dbt (staging -> silver -> gold)
        os.environ.setdefault("DBT_SEND_ANONYMOUS_USAGE_STATS", "0")
        from dbt.cli.main import dbtRunner

        resultat = dbtRunner().invoke(
            ["run", "--project-dir", "dbt", "--profiles-dir", "dbt"]
        )
        if not resultat.success:
            raise RuntimeError("Échec du `dbt run` pendant l'auto-amorçage.")
    finally:
        os.chdir(ancien_cwd)
