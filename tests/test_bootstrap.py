"""Tests de l'auto-amorçage, en particulier sa résilience au réveil de veille.

Panne observée sur Streamlit Community Cloud : après une mise en sommeil, la
base DuckDB reste dans un état inexploitable (WAL orphelin, fichier tronqué),
`dbt run` échoue dessus et l'application refuse de démarrer jusqu'à un vidage
manuel du cache. On teste ici que l'amorçage repart d'un fichier propre.

`dbt` et la génération sont remplacés par des doublures : on valide la logique
de purge et de reprise, pas le pipeline lui-même (couvert ailleurs).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from kidneyvault import bootstrap


@pytest.fixture
def racine(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture
def base(racine: Path) -> Path:
    return racine / "data" / "kidneyvault.duckdb"


@pytest.fixture
def _generation_muette(monkeypatch):
    """Neutralise la génération Bronze (testée dans ses propres modules)."""
    monkeypatch.setattr("kidneyvault.generator.generer_eds", lambda: {})
    monkeypatch.setattr("kidneyvault.corrupteur.corrompre_eds", lambda t: (t, None))
    monkeypatch.setattr("kidneyvault.persist.ecrire_bronze", lambda t: None)


def _base_abimee(base: Path) -> Path:
    """Simule l'état laissé par une veille : fichier illisible + WAL orphelin."""
    base.write_bytes(b"ceci n'est pas une base DuckDB")
    wal = Path(f"{base}.wal")
    wal.write_bytes(b"WAL orphelin")
    return wal


# ---------- Détection ----------


def test_gold_pret_faux_sur_base_abimee(base):
    _base_abimee(base)
    assert bootstrap._gold_pret(base) is False


def test_gold_pret_faux_sans_fichier(base):
    assert bootstrap._gold_pret(base) is False


def test_purger_efface_base_et_wal(base):
    wal = _base_abimee(base)
    bootstrap.purger(base)
    assert not base.exists()
    assert not wal.exists()


# ---------- Reconstruction ----------


def test_base_abimee_purgee_avant_dbt(racine, base, monkeypatch, _generation_muette):
    """Cœur du correctif : `dbt run` ne doit JAMAIS hériter du résidu de veille."""
    wal = _base_abimee(base)
    vu = {}

    def faux_dbt(*args, **kwargs):
        vu["base_presente"] = base.exists()
        vu["wal_present"] = wal.exists()
        base.write_bytes(b"nouvelle base")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(bootstrap.subprocess, "run", faux_dbt)
    bootstrap.ensure_warehouse(racine)

    assert vu["base_presente"] is False, "la base abîmée n'a pas été purgée"
    assert vu["wal_present"] is False, "le WAL orphelin n'a pas été purgé"


def test_echec_dbt_purge_et_retente_une_fois(
    racine, base, monkeypatch, _generation_muette
):
    """Un premier échec déclenche une purge et une seconde tentative."""
    _base_abimee(base)
    appels = []

    def faux_dbt(*args, **kwargs):
        appels.append(base.exists())
        base.write_bytes(b"residu")  # chaque tentative laisse un fichier
        return SimpleNamespace(
            returncode=0 if len(appels) == 2 else 1, stdout="", stderr="boum"
        )

    monkeypatch.setattr(bootstrap.subprocess, "run", faux_dbt)
    bootstrap.ensure_warehouse(racine)

    assert len(appels) == 2, "la seconde tentative n'a pas eu lieu"
    assert appels[1] is False, "la base n'a pas été purgée avant la 2e tentative"


def test_deux_echecs_leve_avec_details(racine, base, monkeypatch, _generation_muette):
    """Après deux échecs, on abandonne — en remontant la sortie de dbt."""
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="", stderr="Could not set lock on file"
        ),
    )
    with pytest.raises(RuntimeError, match="Could not set lock on file"):
        bootstrap.ensure_warehouse(racine)


def test_cwd_restaure_apres_echec(racine, monkeypatch, _generation_muette):
    """Le répertoire courant est rendu même quand l'amorçage échoue."""
    monkeypatch.setattr(
        bootstrap.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="ko"),
    )
    avant = Path.cwd()
    with pytest.raises(RuntimeError):
        bootstrap.ensure_warehouse(racine)
    assert Path.cwd() == avant


def test_gold_deja_pret_ne_reconstruit_pas(racine, base, monkeypatch):
    """Idempotence : une base saine n'est ni purgée ni reconstruite."""
    import duckdb

    con = duckdb.connect(str(base))
    con.execute("CREATE TABLE gold_cohorte_patient AS SELECT 1 AS x")
    con.close()

    def interdit(*args, **kwargs):  # pragma: no cover - ne doit pas être appelé
        raise AssertionError("dbt run ne devrait pas être relancé")

    monkeypatch.setattr(bootstrap.subprocess, "run", interdit)
    bootstrap.ensure_warehouse(racine)
    assert base.exists()
