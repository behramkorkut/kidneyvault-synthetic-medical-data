"""Auto-amorçage de la couche analytique (pour les déploiements).

Sur un déploiement (Streamlit Community Cloud), le warehouse n'est pas committé
(discipline « aucune donnée dans Git »). Au premier démarrage, on génère la
couche Bronze puis on matérialise les modèles dbt — exactement comme le pipeline
local — pour que l'application fonctionne sans provisioning manuel.

La racine du dépôt est TRANSMISE par l'appelant (la page Streamlit, qui vit
toujours dans le dépôt), et non devinée depuis ce module : en déploiement, le
package est *installé* dans le venv, donc son chemin ne reflète pas le dépôt.

Idempotent : si la couche Gold existe déjà, on ne refait rien.

Résilient au réveil de veille (Streamlit Community Cloud) : un conteneur mis en
sommeil pendant une écriture laisse une base inexploitable (WAL orphelin,
fichier tronqué ou verrouillé). `dbt run` échouait alors sur ce résidu et
l'application refusait de démarrer jusqu'à un vidage manuel du cache. On repart
donc systématiquement d'un fichier propre dès que la base n'est pas exploitable.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)


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


def purger(base: Path) -> None:
    """Efface la base et ses fichiers satellites (WAL, répertoire temporaire).

    Appelé quand la base n'est pas exploitable : sans cela, `dbt run` hérite du
    résidu et échoue — c'est la panne observée au réveil de veille.
    """
    for chemin in (base, Path(f"{base}.wal")):
        try:
            chemin.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - dépend du système de fichiers
            logger.warning("Purge impossible : %s", chemin, exc_info=True)
    shutil.rmtree(Path(f"{base}.tmp"), ignore_errors=True)


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

    # La base n'est pas exploitable : soit elle n'existe pas (1er démarrage),
    # soit elle est abîmée (réveil de veille). Dans les deux cas on repart d'un
    # fichier propre — laisser un résidu ferait échouer `dbt run`.
    if base.exists():
        logger.warning("Base DuckDB inexploitable : purge avant reconstruction.")
    purger(base)

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
        commande = ["dbt", "run", "--project-dir", "dbt", "--profiles-dir", "dbt"]

        # Deux tentatives : un échec peut venir d'un fichier DuckDB encore
        # verrouillé par un processus mourant (cas du réveil de veille). On
        # purge et on retente une fois sur une base vierge avant d'abandonner.
        for tentative in (1, 2):
            proc = subprocess.run(
                commande, cwd=racine, env=env, capture_output=True, text=True
            )
            if proc.returncode == 0:
                return
            details = (proc.stderr or proc.stdout or "").strip()[-2000:]
            # Journalisé : sur Streamlit Cloud le navigateur masque l'erreur,
            # seuls les logs (« Manage app ») la montrent.
            logger.error(
                "`dbt run` a échoué (tentative %d/2) :\n%s", tentative, details
            )
            if tentative == 1:
                purger(base)
                continue
            raise RuntimeError(
                f"`dbt run` a échoué pendant l'auto-amorçage :\n{details}"
            )
    finally:
        os.chdir(ancien_cwd)
