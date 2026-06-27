"""Tests des schémas Pandera : vérifient que nos contrats métier acceptent
les données valides et rejettent les données invalides (cas heureux/malheureux)."""

from datetime import date

import polars as pl
import pandera.polars as pa
import pytest

from kidneyvault.schemas import (
    CentreSchema,
    PatientSchema,
    SuiviSchema,
)


# ---------- CentreSchema ----------

def test_centre_valide_passe():
    """Un référentiel de centres bien formé doit être validé tel quel."""
    df = pl.DataFrame(
        {
            "centre_id": [1, 2],
            "nom_centre": ["CHU Bordeaux", "CH Pau"],
            "type_centre": ["CHU", "CH"],
            "region": ["Nouvelle-Aquitaine", "Nouvelle-Aquitaine"],
        }
    )
    valide = CentreSchema.validate(df)
    assert valide.height == 2


def test_centre_type_invalide_rejete():
    """Un type_centre hors énumération doit lever une SchemaError."""
    df = pl.DataFrame(
        {
            "centre_id": [1],
            "nom_centre": ["Centre X"],
            "type_centre": ["Hopital"],  # valeur non autorisée
            "region": ["Occitanie"],
        }
    )
    with pytest.raises(pa.errors.SchemaError):
        CentreSchema.validate(df)


# ---------- PatientSchema (règle métier inter-colonnes) ----------

def test_patient_valide_passe():
    """Patient cohérent : naissance < inclusion."""
    df = pl.DataFrame(
        {
            "patient_id": [1],
            "cle_uroccr": ["JEDU00001"],
            "centre_id": [1],
            "date_naissance": [date(1960, 5, 1)],
            "sexe": ["H"],
            "date_inclusion": [date(2015, 3, 10)],
            "statut_vital": ["vivant"],
            "date_dernieres_nouvelles": [date(2023, 1, 1)],
        }
    )
    assert PatientSchema.validate(df).height == 1


def test_patient_naissance_apres_inclusion_rejete():
    """Naissance postérieure à l'inclusion : viole la règle métier."""
    df = pl.DataFrame(
        {
            "patient_id": [1],
            "cle_uroccr": ["JEDU00001"],
            "centre_id": [1],
            "date_naissance": [date(2020, 5, 1)],   # après inclusion !
            "sexe": ["H"],
            "date_inclusion": [date(2015, 3, 10)],
            "statut_vital": ["vivant"],
            "date_dernieres_nouvelles": [date(2023, 1, 1)],
        }
    )
    with pytest.raises(pa.errors.SchemaError):
        PatientSchema.validate(df)


def test_patient_dernieres_nouvelles_avant_inclusion_rejete():
    """Dernières nouvelles antérieures à l'inclusion : viole la règle métier."""
    df = pl.DataFrame(
        {
            "patient_id": [1],
            "cle_uroccr": ["JEDU00001"],
            "centre_id": [1],
            "date_naissance": [date(1960, 5, 1)],
            "sexe": ["H"],
            "date_inclusion": [date(2015, 3, 10)],
            "statut_vital": ["vivant"],
            "date_dernieres_nouvelles": [date(2014, 1, 1)],  # avant inclusion !
        }
    )
    with pytest.raises(pa.errors.SchemaError):
        PatientSchema.validate(df)


# ---------- SuiviSchema (cohérence récidive/localisation) ----------

def test_suivi_localisation_sans_recidive_rejete():
    """Localisation de récidive renseignée alors que recidive=False : interdit."""
    df = pl.DataFrame(
        {
            "suivi_id": [1],
            "patient_id": [1],
            "date_suivi": [date(2022, 6, 1)],
            "recidive": [False],
            "localisation_recidive": ["Poumon"],  # incohérent avec recidive=False
            "statut": ["Vivant sans maladie"],
        }
    )
    with pytest.raises(pa.errors.SchemaError):
        SuiviSchema.validate(df)
