"""Tests du corrupteur : reproductibilité, vérité terrain exacte,
non-mutation des originaux, et défauts invisibles aux contrats Pandera."""

import polars as pl
import pytest

from kidneyvault import schemas
from kidneyvault.corrupteur import (
    DEFAUT_CHIRURGIE_AVANT_EXAMEN,
    DEFAUT_COMPLETUDE_SCORE_RENAL,
    DEFAUT_DIVERGENCE_TAILLE,
    DEFAUT_DOUBLON_INTER_CENTRES,
    corrompre_eds,
)
from kidneyvault.generator import generer_eds


@pytest.fixture(scope="module")
def propre():
    return generer_eds(n_patients=50, n_centres=8, seed=42)


@pytest.fixture(scope="module")
def corrompu(propre):
    """Tuple (tables corrompues, vérité terrain), partagé par tout le module."""
    return corrompre_eds(propre, seed=2025)


def test_reproductibilite_corruption(propre):
    """Même graine de corruption => mêmes défauts, même vérité terrain."""
    c1, vt1 = corrompre_eds(propre, seed=99)
    c2, vt2 = corrompre_eds(propre, seed=99)
    assert vt1.equals(vt2)
    for table in c1:
        assert c1[table].equals(c2[table]), f"Non-reproductible : {table}"


def test_originaux_non_modifies(propre):
    """Le corrupteur travaille sur copie : l'EDS propre reste intact."""
    avant = {nom: df.clone() for nom, df in propre.items()}
    corrompre_eds(propre)
    for nom in propre:
        assert propre[nom].equals(avant[nom]), f"Table mutée : {nom}"


def test_verite_terrain_exhaustive(corrompu):
    """Chaque défaut commandé est consigné dans la vérité terrain."""
    _, vt = corrompu

    def n(defaut: str) -> int:
        return vt.filter(pl.col("defaut") == defaut).height

    assert n(DEFAUT_CHIRURGIE_AVANT_EXAMEN) == 3
    assert n(DEFAUT_DOUBLON_INTER_CENTRES) == 2
    assert n(DEFAUT_DIVERGENCE_TAILLE) == 3
    assert n(DEFAUT_COMPLETUDE_SCORE_RENAL) > 0


def test_chirurgies_antidatees_effectives(propre, corrompu):
    """Les chirurgies ciblées sont réellement antérieures au bilan."""
    corrompues, vt = corrompu
    ids = vt.filter(pl.col("defaut") == DEFAUT_CHIRURGIE_AVANT_EXAMEN)["id_ligne"].to_list()
    examen_ref = (
        propre["examen_pretherapeutique"]
        .group_by("patient_id")
        .agg(pl.col("date_examen").min().alias("ref"))
    )
    chir = (
        corrompues["chirurgie"]
        .filter(pl.col("chirurgie_id").is_in(ids))
        .join(examen_ref, on="patient_id")
    )
    assert chir.height == 3
    assert (chir["date_chirurgie"] < chir["ref"]).all()


def test_doublons_presents(propre, corrompu):
    """Les doublons ajoutent des lignes patient, avec clés uniques."""
    corrompues, _ = corrompu
    assert corrompues["patient"].height == propre["patient"].height + 2
    assert corrompues["patient"]["cle_uroccr"].n_unique() == corrompues["patient"].height


def test_contrats_aveugles_aux_defauts(corrompu):
    """DOCUMENTE UNE LIMITE : les défauts injectés passent tous les contrats
    Pandera (intra-table). Leur détection relève de la couche qualité SQL
    (règles inter-tables et indicateurs statistiques)."""
    corrompues, _ = corrompu
    schemas.CentreSchema.validate(corrompues["centre"])
    schemas.PatientSchema.validate(corrompues["patient"])
    schemas.ExamenPretherapeutiqueSchema.validate(corrompues["examen_pretherapeutique"])
    schemas.ChirurgieSchema.validate(corrompues["chirurgie"])
    schemas.AnatomopathologieSchema.validate(corrompues["anatomopathologie"])
    schemas.SuiviSchema.validate(corrompues["suivi"])
    schemas.TraitementOncologieSchema.validate(corrompues["traitement_oncologie"])