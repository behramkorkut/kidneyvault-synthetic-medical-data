"""Tests du générateur de Data Dictionary REDCap."""

from kidneyvault.redcap_dictionary import COLONNES_REDCAP, construire_dictionnaire


def _index():
    return {
        (r["Form Name"], r["Variable / Field Name"]): r
        for r in construire_dictionnaire()
    }


def test_toutes_colonnes_presentes():
    """Chaque ligne possède exactement les 18 colonnes REDCap, dans l'ordre."""
    for row in construire_dictionnaire():
        assert list(row.keys()) == COLONNES_REDCAP


def test_enumeration_devient_dropdown():
    sexe = _index()[("patient", "sexe")]
    assert sexe["Field Type"] == "dropdown"
    choices = sexe["Choices, Calculations, OR Slider Labels"]
    assert "H" in choices and "F" in choices


def test_entier_borne_valide():
    taille = _index()[("examen_pretherapeutique", "taille_tumeur_mm")]
    assert taille["Field Type"] == "text"
    assert taille["Text Validation Type OR Show Slider Number"] == "integer"
    assert taille["Text Validation Min"] == "1"
    assert taille["Text Validation Max"] == "250"


def test_date_validation():
    naissance = _index()[("patient", "date_naissance")]
    assert naissance["Text Validation Type OR Show Slider Number"] == "date_ymd"


def test_booleen_devient_yesno():
    assert _index()[("suivi", "recidive")]["Field Type"] == "yesno"


def test_identifiant_flague():
    assert _index()[("patient", "cle_uroccr")]["Identifier?"] == "y"


def test_required_suit_nullabilite():
    idx = _index()
    assert idx[("patient", "patient_id")]["Required Field?"] == "y"
    assert idx[("patient", "date_dernieres_nouvelles")]["Required Field?"] == ""
    


def test_branching_logic_recidive():
    """localisation_recidive n'est visible que si récidive = oui."""
    loc = _index()[("suivi", "localisation_recidive")]
    assert loc["Branching Logic (Show field only if...)"] == "[recidive] = '1'"


def test_branching_logic_grade_chromophobe():
    """grade_isup masqué pour le chromophobe (non gradé en ISUP)."""
    grade = _index()[("anatomopathologie", "grade_isup")]
    bl = grade["Branching Logic (Show field only if...)"]
    assert bl.startswith("[type_histologique] <> '")