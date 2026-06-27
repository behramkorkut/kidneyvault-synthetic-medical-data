"""Tests du générateur d'EDS : reproductibilité, cohérence inter-tables,
conformité aux schémas Pandera."""

import polars as pl
import pytest

from kidneyvault.generator import DATE_EXTRACTION, generer_eds
from kidneyvault.schemas import (
    CentreSchema,
    PatientSchema,
    ExamenPretherapeutiqueSchema,
    ChirurgieSchema,
    AnatomopathologieSchema,
    SuiviSchema,
    TraitementOncologieSchema,
)


@pytest.fixture(scope="module")
def eds():
    """Jeu de données EDS généré une fois pour tout le module (seed fixe)."""
    return generer_eds(n_patients=50, n_centres=8, seed=42)


# ---------- Reproductibilité ----------

def test_reproductibilite():
    """Même graine => exactement les mêmes données."""
    eds1 = generer_eds(n_patients=30, n_centres=8, seed=123)
    eds2 = generer_eds(n_patients=30, n_centres=8, seed=123)
    for table in eds1:
        assert eds1[table].equals(eds2[table]), f"Non-reproductible : {table}"


def test_volumes_attendus(eds):
    """Les volumes de base sont corrects."""
    assert eds["centre"].height == 8
    assert eds["patient"].height == 50
    assert eds["examen_pretherapeutique"].height == 50  # un examen par patient


# ---------- Conformité aux schémas Pandera ----------

def test_toutes_tables_conformes_pandera(eds):
    """Chaque table générée respecte son contrat Pandera."""
    CentreSchema.validate(eds["centre"])
    PatientSchema.validate(eds["patient"])
    ExamenPretherapeutiqueSchema.validate(eds["examen_pretherapeutique"])
    ChirurgieSchema.validate(eds["chirurgie"])
    AnatomopathologieSchema.validate(eds["anatomopathologie"])
    SuiviSchema.validate(eds["suivi"])
    TraitementOncologieSchema.validate(eds["traitement_oncologie"])


# ---------- Cohérence inter-tables ----------

def test_anapath_implique_chirurgie(eds):
    """Toute anapath référence une chirurgie existante (intégrité référentielle)."""
    ids_chirurgie = set(eds["chirurgie"]["chirurgie_id"].to_list())
    ids_anapath_chir = set(eds["anatomopathologie"]["chirurgie_id"].to_list())
    assert ids_anapath_chir.issubset(ids_chirurgie)


def test_integrite_referentielle_patient(eds):
    """Tous les patient_id des tables filles existent dans la table patient."""
    ids_patients = set(eds["patient"]["patient_id"].to_list())
    for table in [
        "examen_pretherapeutique", "chirurgie", "anatomopathologie",
        "suivi", "traitement_oncologie",
    ]:
        ids = set(eds[table]["patient_id"].to_list())
        assert ids.issubset(ids_patients), f"FK orpheline dans {table}"


def test_coherence_deces(eds):
    """Un statut 'Décédé' en suivi implique un patient décédé."""
    decedes_patient = set(
        eds["patient"].filter(
            eds["patient"]["statut_vital"] == "décédé"
        )["patient_id"].to_list()
    )
    decedes_suivi = set(
        eds["suivi"].filter(eds["suivi"]["statut"] == "Décédé")["patient_id"].to_list()
    )
    assert decedes_suivi.issubset(decedes_patient)


def test_traitement_reserve_aux_stades_avances():
    """Aucun patient localisé ne reçoit de traitement oncologique.

    On régénère l'EDS avec conserver_stade=True pour accéder à la colonne
    technique `_stade`, plutôt que de répliquer l'ordre de consommation du
    générateur aléatoire (fragile au moindre refactoring).
    """
    eds_stade = generer_eds(n_patients=50, n_centres=8, seed=42, conserver_stade=True)
    stade_par_patient = dict(
        zip(
            eds_stade["patient"]["patient_id"].to_list(),
            eds_stade["patient"]["_stade"].to_list(),
        )
    )
    for pid in eds_stade["traitement_oncologie"]["patient_id"].to_list():
        assert stade_par_patient[pid] in ("localement_avance", "metastatique")


# ---------- Cohérence temporelle ----------

def test_aucune_date_apres_extraction(eds):
    """Aucune date générée ne dépasse la date d'extraction simulée de l'EDS."""
    for nom_table, df in eds.items():
        for col in df.columns:
            if df[col].dtype == pl.Date:
                assert df[col].max() <= DATE_EXTRACTION, f"{nom_table}.{col}"


def test_suivis_dans_fenetre_observation(eds):
    """Aucun suivi postérieur aux dernières nouvelles du patient."""
    joint = eds["suivi"].join(eds["patient"], on="patient_id")
    assert (joint["date_suivi"] <= joint["date_dernieres_nouvelles"]).all()


def test_traitements_dans_fenetre_observation(eds):
    """Aucun traitement ne débute ou ne finit après les dernières nouvelles."""
    joint = eds["traitement_oncologie"].join(eds["patient"], on="patient_id")
    assert (joint["date_debut"] <= joint["date_dernieres_nouvelles"]).all()
    fins = joint.filter(joint["date_fin"].is_not_null())
    assert (fins["date_fin"] <= fins["date_dernieres_nouvelles"]).all()
