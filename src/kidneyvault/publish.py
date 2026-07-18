"""Publication des tables Gold vers la couche de service Postgres.

dbt construit l'entrepôt analytique en DuckDB ; cette étape ELT « sert » les
tables consommables (cohorte + KPI) dans Postgres, que Metabase interroge.
On sépare ainsi l'entrepôt (DuckDB, calcul) de la couche de service
(Postgres, lecture BI) — exactement la version industrialisée de l'ADR.

Prérequis : la stack docker-compose est démarrée (Postgres en bonne santé).
Usage : uv run python -m kidneyvault.publish
"""

import logging
import os
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

RACINE = Path(__file__).resolve().parents[2]
# Chemin absolu dérivé du module : indépendant du répertoire d'appel (M9).
BASE = str(RACINE / "data" / "kidneyvault.duckdb")


# Seules ces tables sont exposées à la BI (la couche de service ne montre
# que le consommable, pas le staging ni le silver).
TABLES_SERVIES = [
    "gold_cohorte_patient",
    "gold_kpi_activite_par_centre",
    "gold_kpi_inclusions_annuelles",
    "gold_kpi_histologie",
]


def _charger_env(chemin: Path = RACINE / ".env") -> None:
    """Charge un fichier .env (clé=valeur) sans écraser l'environnement existant.

    Évite une dépendance externe pour un besoin simple ; en production réelle,
    un gestionnaire de secrets prendrait le relais.
    """
    if not chemin.exists():
        return
    for ligne in chemin.read_text().splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        os.environ.setdefault(cle.strip(), valeur.strip())


def _dsn() -> str:
    """Construit le DSN Postgres depuis l'environnement (jamais en dur)."""
    _charger_env()
    try:
        mot_de_passe = os.environ["POSTGRES_PASSWORD"]
    except KeyError as exc:
        raise RuntimeError(
            "POSTGRES_PASSWORD manquant : copiez .env.example vers .env et "
            "renseignez-le (cp .env.example .env)."
        ) from exc
    return (
        f"host={os.getenv('PGHOST', 'localhost')} "
        f"port={os.getenv('PGPORT', '5433')} "
        f"dbname={os.getenv('POSTGRES_DB', 'kidneyvault')} "
        f"user={os.getenv('POSTGRES_USER', 'kidney')} "
        f"password={mot_de_passe}"
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s"
    )
    # Connexion en lecture-écriture : on LIT l'entrepôt DuckDB, mais on doit
    # pouvoir ÉCRIRE dans le catalogue Postgres attaché. Une connexion
    # read_only forcerait AUSSI le Postgres attaché en lecture seule.
    # Pas de contention : la publication ne tourne jamais pendant dbt.
    con = duckdb.connect(BASE)
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{_dsn()}' AS pg (TYPE postgres);")
    logger.info("Publication vers Postgres — %d tables.", len(TABLES_SERVIES))

    # Publication ATOMIQUE : les DROP/CREATE de toutes les tables sont dans une
    # seule transaction. En cas d'échec en cours de route, un ROLLBACK laisse la
    # couche de service Postgres exactement dans son état antérieur — jamais
    # à moitié republiée (BI qui lirait des tables manquantes ou incohérentes).
    con.execute("BEGIN TRANSACTION;")
    try:
        for table in TABLES_SERVIES:
            con.execute(f"DROP TABLE IF EXISTS pg.{table};")
            con.execute(f"CREATE TABLE pg.{table} AS SELECT * FROM {table};")
            n = con.execute(f"SELECT count(*) FROM pg.{table}").fetchone()[0]
            logger.info("  %-32s → Postgres (%d lignes)", table, n)
        con.execute("COMMIT;")
    except Exception:
        con.execute("ROLLBACK;")
        logger.exception("Échec de publication : ROLLBACK, Postgres inchangé.")
        raise
    finally:
        con.close()
    logger.info("Couche de service publiée (transaction validée).")


if __name__ == "__main__":
    main()