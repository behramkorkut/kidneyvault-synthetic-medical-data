"""Génération d'un Data Dictionary REDCap à partir des contrats Pandera.

REDCap est la plateforme standard de saisie en recherche clinique. Un eCRF s'y
définit par un « Data Dictionary » CSV normalisé. Ce module produit ce CSV
directement depuis les schémas Pandera de KidneyVault : les contrats de
validation deviennent la définition de l'eCRF — une seule source de vérité, du
contrat à la saisie.

Mapping :
- énumération (isin)  -> « dropdown » + Choices codés ;
- entier (ge/le)      -> « text » + validation integer + min/max ;
- date                -> « text » + validation date_ymd ;
- booléen             -> « yesno » ;
- chaîne libre        -> « text ».
Nullabilité -> Required Field ; clé de pseudonymisation -> Identifier.

⚠️ Artefact de démonstration : dans un vrai projet REDCap, le record-id et la
structuration des instruments seraient affinés avec l'équipe d'étude.

Usage : uv run python -m kidneyvault.redcap_dictionary
"""

import csv
from collections import OrderedDict
from pathlib import Path

from kidneyvault import schemas

# 18 colonnes standard d'un Data Dictionary REDCap, dans l'ordre attendu à l'import.
COLONNES_REDCAP = [
    "Variable / Field Name",
    "Form Name",
    "Section Header",
    "Field Type",
    "Field Label",
    "Choices, Calculations, OR Slider Labels",
    "Field Note",
    "Text Validation Type OR Show Slider Number",
    "Text Validation Min",
    "Text Validation Max",
    "Identifier?",
    "Branching Logic (Show field only if...)",
    "Required Field?",
    "Custom Alignment",
    "Question Number (surveys only)",
    "Matrix Group Name",
    "Matrix Ranking?",
    "Field Annotation",
]

# Formulaires (instruments) REDCap = tables. Patient en premier : son identifiant
# fait office de record-id REDCap.
FORMULAIRES = OrderedDict(
    [
        ("patient", (schemas.PatientSchema, "Patient (entité pivot)")),
        (
            "examen_pretherapeutique",
            (schemas.ExamenPretherapeutiqueSchema, "Bilan pré-thérapeutique"),
        ),
        ("chirurgie", (schemas.ChirurgieSchema, "Chirurgie")),
        ("anatomopathologie", (schemas.AnatomopathologieSchema, "Anatomopathologie")),
        ("suivi", (schemas.SuiviSchema, "Suivi longitudinal")),
        (
            "traitement_oncologie",
            (schemas.TraitementOncologieSchema, "Traitement oncologique"),
        ),
        ("centre", (schemas.CentreSchema, "Référentiel des centres")),
    ]
)

# Colonnes directement ré-identifiantes (Identifier? = y).
IDENTIFIANTS = {"cle_uroccr"}

# Libellés lisibles pour les champs cryptiques ; sinon dérivés du nom.
LIBELLES = {
    "cle_uroccr": "Clé de pseudonymisation (format UroCCR)",
    "ct": "Classification T clinique (cTNM)",
    "cn": "Classification N clinique (cTNM)",
    "cm": "Classification M clinique (cTNM)",
    "pt": "Classification T pathologique (pTNM)",
    "pn": "Classification N pathologique (pTNM)",
    "score_renal": "Score de complexité R.E.N.A.L.",
    "grade_isup": "Grade nucléaire ISUP",
    "taille_tumeur_mm": "Taille tumorale à l'imagerie (mm)",
    "taille_tumorale_mm": "Taille tumorale sur pièce (mm)",
}


def _code(valeurs, cible) -> int:
    """Code REDCap (1-based) d'une valeur dans son énumération."""
    return list(valeurs).index(cible) + 1


# Code dérivé pour rester robuste à un réordonnancement de l'énumération.
_CODE_CHROMOPHOBE = _code(schemas.TYPES_HISTO, "Chromophobe")

# Branching logic : expression REDCap, à la SAISIE, des règles de cohérence
# inter-champs encodées par les @pa.dataframe_check Pandera (prévention à la
# source, là où le pipeline fait de la détection en aval).
BRANCHEMENTS = {
    # localisation_recidive visible seulement si récidive (yesno : oui = 1)
    ("suivi", "localisation_recidive"): "[recidive] = '1'",
    # grade ISUP non applicable au chromophobe -> champ masqué dans ce cas
    (
        "anatomopathologie",
        "grade_isup",
    ): f"[type_histologique] <> '{_CODE_CHROMOPHOBE}'",
}


def _libelle(nom: str) -> str:
    return LIBELLES.get(nom, nom.replace("_", " ").capitalize())


def _stats(colonne) -> dict:
    """Fusionne les statistiques de tous les checks d'une colonne Pandera."""
    fusion: dict = {}
    for check in getattr(colonne, "checks", []) or []:
        stat = getattr(check, "statistics", None)
        if isinstance(stat, dict):
            fusion.update(stat)
    return fusion


def _genre(colonne) -> str:
    """Type logique simplifié à partir du dtype Pandera/Polars."""
    t = str(colonne.dtype).lower()
    if "bool" in t:
        return "bool"
    if "date" in t or "time" in t:
        return "date"
    if "int" in t:
        return "int"
    return "str"


def _choices(valeurs) -> str:
    """Encode une énumération au format REDCap : '1, Label | 2, Label'."""
    return " | ".join(f"{i}, {v}" for i, v in enumerate(valeurs, start=1))


def _champ(nom, formulaire, colonne, section) -> dict:
    """Construit une ligne de Data Dictionary pour une colonne."""
    stats = _stats(colonne)
    genre = _genre(colonne)
    allowed = stats.get("allowed_values")

    field_type, choices, validation, vmin, vmax = "text", "", "", "", ""
    if allowed is not None:
        field_type = "dropdown"
        choices = _choices(list(allowed))
    elif genre == "bool":
        field_type = "yesno"
    elif genre == "int":
        validation = "integer"
        if stats.get("min_value") is not None:
            vmin = str(int(stats["min_value"]))
        if stats.get("max_value") is not None:
            vmax = str(int(stats["max_value"]))
    elif genre == "date":
        validation = "date_ymd"

    requis = "" if getattr(colonne, "nullable", False) else "y"
    identifiant = "y" if nom in IDENTIFIANTS else ""

    return {
        "Variable / Field Name": nom.lower(),
        "Form Name": formulaire,
        "Section Header": section,
        "Field Type": field_type,
        "Field Label": _libelle(nom.lower()),
        "Choices, Calculations, OR Slider Labels": choices,
        "Field Note": "",
        "Text Validation Type OR Show Slider Number": validation,
        "Text Validation Min": vmin,
        "Text Validation Max": vmax,
        "Identifier?": identifiant,
        "Branching Logic (Show field only if...)": BRANCHEMENTS.get(
            (formulaire, nom.lower()), ""
        ),
        "Required Field?": requis,
        "Custom Alignment": "",
        "Question Number (surveys only)": "",
        "Matrix Group Name": "",
        "Matrix Ranking?": "",
        "Field Annotation": "",
    }


def construire_dictionnaire() -> list[dict]:
    """Génère toutes les lignes du Data Dictionary depuis les schémas Pandera."""
    lignes: list[dict] = []
    for formulaire, (schema, description) in FORMULAIRES.items():
        colonnes = schema.to_schema().columns
        for i, (nom, colonne) in enumerate(colonnes.items()):
            section = description if i == 0 else ""  # titre de bloc sur le 1er champ
            lignes.append(_champ(nom, formulaire, colonne, section))
    return lignes


def ecrire_csv(
    lignes: list[dict],
    chemin: str | Path = "data/redcap/instruments_data_dictionary.csv",
) -> Path:
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with chemin.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLONNES_REDCAP)
        writer.writeheader()
        writer.writerows(lignes)
    return chemin


def main() -> None:
    lignes = construire_dictionnaire()
    chemin = ecrire_csv(lignes)
    n_forms = len({row["Form Name"] for row in lignes})
    print(
        f"Data Dictionary REDCap généré : {len(lignes)} champs, "
        f"{n_forms} formulaires → {chemin}"
    )


if __name__ == "__main__":
    main()
