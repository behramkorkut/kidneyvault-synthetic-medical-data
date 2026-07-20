"""Test d'intégration de la couche qualité : génération → corruption →
persistance Bronze → contrôles SQL → évaluation contre vérité terrain."""

import pytest

from kidneyvault.corrupteur import corrompre_eds
from kidneyvault.evaluation import evaluer
from kidneyvault.generator import generer_eds
from kidneyvault.persist import ecrire_bronze
from kidneyvault.qualite import connexion_bronze, executer_controles


@pytest.fixture(scope="module")
def bronze_corrompue(tmp_path_factory):
    """Bronze corrompue persistée dans un dossier temporaire (test hermétique)."""
    dossier = tmp_path_factory.mktemp("bronze")
    tables = generer_eds(n_patients=50, n_centres=8, seed=42)
    corrompues, verite_terrain = corrompre_eds(tables, seed=2025)
    ecrire_bronze(corrompues, dossier=dossier)
    return dossier, verite_terrain


def test_chaine_qualite_complete(bronze_corrompue):
    """Sur la configuration de référence : tout détecté, aucun faux positif."""
    dossier, verite_terrain = bronze_corrompue
    anomalies = executer_controles(connexion_bronze(dossier))
    rapport = evaluer(anomalies, verite_terrain)
    assert rapport.height == 3  # les 3 défauts ligne à ligne
    assert (rapport["rappel"] == 1.0).all()
    assert (rapport["precision"] == 1.0).all()


def test_controles_generalisent(tmp_path):
    """Les contrôles ne sont pas surajustés à la graine de référence :
    avec d'autres graines et volumes, le rappel reste à 100 %.
    (La précision n'est pas exigée ici : un doublon fortuit — deux vrais
    patients partageant naissance, sexe et lettres — est un faux positif
    légitime du rapprochement déterministe.)"""
    tables = generer_eds(n_patients=80, n_centres=8, seed=7)
    corrompues, verite_terrain = corrompre_eds(
        tables, seed=31, n_dates_chirurgie=5, n_doublons=3, n_divergences_taille=4
    )
    ecrire_bronze(corrompues, dossier=tmp_path)
    anomalies = executer_controles(connexion_bronze(tmp_path))
    rapport = evaluer(anomalies, verite_terrain)
    assert (rapport["rappel"] == 1.0).all()
