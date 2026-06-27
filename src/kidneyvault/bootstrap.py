"""Auto-amorçage de la couche analytique (pour les déploiements).

Sur un déploiement (Streamlit Community Cloud), le warehouse n'est pas committé
(discipline « aucune donnée dans Git »). Au premier démarrage, on génère la
couche Bronze puis on matérialise les modèles dbt — exactement comme le pipeline
local — pour que l'application fonctionne sans provisioning manuel.

La racine du dépôt est TRANSMISE par l'appelant (la page Streamlit, qui vit
toujours dans le dépôt), et non devinée depuis ce module : en déploiement, le
package est *installé* dans le venv, donc son chemin ne reflète pas le dépôt.

Idempotent : si la couche Gold existe déjà, on ne refait rien.
"""

import os
import subprocess
from pathlib import Path

import duckdb


def _gold_pret(base: Path) -> bool:
    """Vrai si le fichier DuckDB existe et contient la table Gold attendue."""
    if not base.exists():
        return False
    try:
        con = duckdb.connect(str(base), read_only=True)
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        con.close()
        return "gold_cohorte_patient" in tables
    except duckdb.Error:
        return False


def ensure_warehouse(racine: Path) -> None:
    """Construit Bronze + modèles dbt si le warehouse n'est pas déjà prêt.

    Args:
        racine: racine du dépôt (contient `dbt/`, `data/`). Les chemins relatifs
            de dbt et des sources Parquet sont résolus depuis là.
    """
    racine = Path(racine).resolve()
    base = racine / "data" / "kidneyvault.duckdb"
    if _gold_pret(base):
        return

    from kidneyvault.corrupteur import corrompre_eds
    from kidneyvault.generator import generer_eds
    from kidneyvault.persist import ecrire_bronze

    ancien_cwd = Path.cwd()
    os.chdir(racine)
    try:
        # 1. Couche Bronze : données synthétiques + défauts réalistes injectés
        tables = generer_eds()
        tables, _ = corrompre_eds(tables)
        ecrire_bronze(tables)

        # 2. Matérialisation des modèles dbt, dans un SOUS-PROCESSUS.
        # Indispensable : dbt-duckdb garderait sa connexion lecture-écriture
        # ouverte in-process ; une connexion read_only ouverte ensuite dans le
        # même process échouerait (« different configuration »). En se terminant,
        # le sous-processus libère le fichier DuckDB.
        env = {**os.environ, "DBT_SEND_ANONYMOUS_USAGE_STATS": "0"}
        proc = subprocess.run(
            ["dbt", "run", "--project-dir", "dbt", "--profiles-dir", "dbt"],
            cwd=racine,
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            details = (proc.stderr or proc.stdout or "").strip()[-2000:]
            raise RuntimeError(
                f"`dbt run` a échoué pendant l'auto-amorçage :\n{details}"
            )
    finally:
        os.chdir(ancien_cwd)
