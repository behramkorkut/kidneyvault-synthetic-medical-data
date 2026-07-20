"""Quota serveur : budget d'appels API par adresse IP et par jour.

Complète la garde de session (rate_limit.py), dont le compteur vit en
`session_state` et repart donc de zéro à chaque rechargement de page — la
faiblesse exacte relevée par l'audit. Ici le compteur est PERSISTANT :

1. dans la couche de service **Postgres** si elle est joignable
   (DATABASE_URL, ou les variables POSTGRES_* du docker-compose) ;
2. sinon, repli sur un petit fichier **DuckDB local** à côté du warehouse
   (`data/quota.duckdb`) — zéro dépendance nouvelle, survit aux rechargements
   de page et aux nouvelles sessions.

Résidu assumé (documenté dans le README) : sur Streamlit Cloud, le fichier
local ne survit pas à un redémarrage du conteneur (mise en veille). Le pire
cas est un budget remis à zéro au réveil — pas un robinet ouvert.

Désactivation (dev local, CI) : KIDNEYVAULT_QUOTA_OFF=1.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

_RACINE = Path(__file__).resolve().parents[2]
CHEMIN_LOCAL = _RACINE / "data" / "quota.duckdb"
MAX_APPELS_JOUR = 6  # budget d'appels API par IP et par jour

_DDL = (
    "CREATE TABLE IF NOT EXISTS {table} ("
    "ip VARCHAR NOT NULL, jour DATE NOT NULL, appels INTEGER NOT NULL)"
)


def _dsn_postgres() -> str | None:
    """DSN Postgres si configuré (DATABASE_URL prioritaire), sinon None.

    Contrairement à publish.py, l'absence de configuration n'est pas une
    erreur : elle déclenche simplement le repli sur le fichier local.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    mot_de_passe = os.environ.get("POSTGRES_PASSWORD")
    if not mot_de_passe:
        return None
    return (
        f"host={os.getenv('PGHOST', 'localhost')} "
        f"port={os.getenv('PGPORT', '5433')} "
        f"dbname={os.getenv('POSTGRES_DB', 'kidneyvault')} "
        f"user={os.getenv('POSTGRES_USER', 'kidney')} "
        f"password={mot_de_passe}"
    )


def _incrementer(
    con: duckdb.DuckDBPyConnection, table: str, ip: str, jour: date, max_jour: int
) -> tuple[bool, str]:
    """Vérifie puis incrémente le compteur (ip, jour). Retourne (autorisé,
    message) — message non vide seulement si refusé."""
    ligne = con.execute(
        f"SELECT appels FROM {table} WHERE ip = ? AND jour = ?", [ip, jour]
    ).fetchone()
    appels = ligne[0] if ligne else 0
    if appels >= max_jour:
        return False, (
            f"Quota journalier de la démo atteint ({max_jour} requêtes par "
            "jour et par adresse). Revenez demain !"
        )
    if ligne:
        con.execute(
            f"UPDATE {table} SET appels = appels + 1 WHERE ip = ? AND jour = ?",
            [ip, jour],
        )
    else:
        con.execute(f"INSERT INTO {table} VALUES (?, ?, 1)", [ip, jour])
    return True, ""


def _consommer_postgres(
    dsn: str, ip: str, jour: date, max_jour: int
) -> tuple[bool, str]:
    """Compteur dans la couche de service Postgres (via l'extension DuckDB,
    même mécanique que publish.py — aucune dépendance nouvelle)."""
    con = duckdb.connect()
    try:
        con.execute("INSTALL postgres; LOAD postgres;")
        dsn_echappe = dsn.replace("'", "''")
        con.execute(f"ATTACH '{dsn_echappe}' AS pg (TYPE postgres)")
        con.execute(_DDL.format(table="pg.quota_ip"))
        return _incrementer(con, "pg.quota_ip", ip, jour, max_jour)
    finally:
        con.close()


def _consommer_local(
    chemin: Path, ip: str, jour: date, max_jour: int
) -> tuple[bool, str]:
    """Compteur dans un fichier DuckDB local : persistant au-delà des sessions
    Streamlit (une connexion courte par appel, pas de verrou durable)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(chemin))
    try:
        con.execute(_DDL.format(table="quota_ip"))
        return _incrementer(con, "quota_ip", ip, jour, max_jour)
    finally:
        con.close()


def consommer(
    ip: str,
    *,
    jour: date | None = None,
    max_jour: int = MAX_APPELS_JOUR,
    chemin_local: Path = CHEMIN_LOCAL,
) -> tuple[bool, str]:
    """Consomme une unité du budget quotidien de l'IP. Retourne (autorisé,
    message).

    Postgres d'abord si configuré ; toute défaillance (hôte injoignable,
    extension absente…) bascule sur le fichier local — la démo publique ne
    doit jamais être ni sans garde, ni bloquée par l'infra.
    """
    if os.environ.get("KIDNEYVAULT_QUOTA_OFF") == "1":
        return True, ""
    jour = jour or date.today()
    dsn = _dsn_postgres()
    if dsn:
        try:
            return _consommer_postgres(dsn, ip, jour, max_jour)
        except Exception:
            logger.warning(
                "Postgres injoignable pour le quota : repli fichier local.",
                exc_info=True,
            )
    return _consommer_local(chemin_local, ip, jour, max_jour)
