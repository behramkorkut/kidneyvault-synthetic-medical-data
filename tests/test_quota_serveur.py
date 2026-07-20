"""Tests du quota serveur (6 appels/jour/IP, persistant).

Aucun Postgres réel : la bascule est testée en mockant un backend Postgres
défaillant. Le backend fichier utilise un DuckDB temporaire (tmp_path).
"""

from datetime import date

import pytest

from kidneyvault import quota_serveur
from kidneyvault.quota_serveur import MAX_APPELS_JOUR, consommer

JOUR = date(2026, 7, 20)


@pytest.fixture(autouse=True)
def _sans_postgres_ni_flag(monkeypatch):
    """Environnement neutre : pas de DSN Postgres, flag de désactivation absent."""
    for var in ("DATABASE_URL", "POSTGRES_PASSWORD", "KIDNEYVAULT_QUOTA_OFF"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def chemin(tmp_path):
    return tmp_path / "quota.duckdb"


def test_six_appels_passent_le_septieme_est_bloque(chemin):
    for i in range(MAX_APPELS_JOUR):
        autorise, message = consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)
        assert autorise is True, f"appel {i + 1} refusé à tort"
        assert message == ""
    autorise, message = consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)
    assert autorise is False
    assert "quota" in message.lower()


def test_budgets_independants_par_ip(chemin):
    """Épuiser le budget d'une IP ne touche pas celui d'une autre."""
    for _ in range(MAX_APPELS_JOUR):
        consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)
    assert consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)[0] is False
    assert consommer("5.6.7.8", jour=JOUR, chemin_local=chemin)[0] is True


def test_budget_remis_a_zero_le_lendemain(chemin):
    for _ in range(MAX_APPELS_JOUR):
        consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)
    assert consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)[0] is False
    lendemain = date(2026, 7, 21)
    assert consommer("1.2.3.4", jour=lendemain, chemin_local=chemin)[0] is True


def test_persistance_au_dela_de_la_session(chemin):
    """Le compteur vit dans un fichier : un « rechargement de page » (nouvelle
    session, nouveau session_state) ne le remet PAS à zéro — c'est la faille
    du quota session que ce module corrige. Chaque appel à consommer() ouvre
    sa propre connexion, comme le feraient des sessions distinctes."""
    for _ in range(MAX_APPELS_JOUR):
        consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)
    # « Nouvelle session » : aucun état en mémoire partagé, seul le fichier
    # compte — le refus doit persister.
    autorise, _ = consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)
    assert autorise is False
    assert chemin.exists()


def test_bascule_postgres_injoignable_vers_fichier(chemin, monkeypatch):
    """DSN Postgres configuré mais backend défaillant (mocké) : le quota doit
    basculer sur le fichier local, jamais laisser passer sans garde."""
    monkeypatch.setattr(quota_serveur, "_dsn_postgres", lambda: "dsn-bidon")

    def _postgres_en_panne(dsn, ip, jour, max_jour):
        raise RuntimeError("connexion refusée")

    monkeypatch.setattr(quota_serveur, "_consommer_postgres", _postgres_en_panne)

    for _ in range(MAX_APPELS_JOUR):
        assert consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)[0] is True
    assert consommer("1.2.3.4", jour=JOUR, chemin_local=chemin)[0] is False
    assert chemin.exists()  # preuve que le repli fichier a bien été utilisé


def test_postgres_prioritaire_quand_disponible(chemin, monkeypatch):
    """DSN configuré et backend sain (mocké) : Postgres est utilisé, le
    fichier local n'est pas créé."""
    monkeypatch.setattr(quota_serveur, "_dsn_postgres", lambda: "dsn-bidon")
    monkeypatch.setattr(
        quota_serveur,
        "_consommer_postgres",
        lambda dsn, ip, jour, max_jour: (True, ""),
    )
    assert consommer("1.2.3.4", jour=JOUR, chemin_local=chemin) == (True, "")
    assert not chemin.exists()


def test_flag_de_desactivation(chemin, monkeypatch):
    """KIDNEYVAULT_QUOTA_OFF=1 (dev local, CI) : tout passe, rien n'est écrit."""
    monkeypatch.setenv("KIDNEYVAULT_QUOTA_OFF", "1")
    for _ in range(MAX_APPELS_JOUR * 3):
        assert consommer("1.2.3.4", jour=JOUR, chemin_local=chemin) == (True, "")
    assert not chemin.exists()
