"""Injection contrôlée de défauts réalistes dans l'EDS synthétique.

Le générateur (generator.py) produit des données propres ; ce module les
dégrade volontairement pour donner à la couche qualité une matière première
réaliste. Principes :

- Jamais de modification en place : on retourne des copies corrompues.
- Chaque défaut est consigné dans un rapport « vérité terrain » qui permettra
  d'évaluer objectivement la couche qualité (tout détecté ? aucun faux positif ?).
- Reproductible : graine dédiée, indépendante de celle du générateur.
"""

from __future__ import annotations

import random
from datetime import timedelta

import polars as pl

# Graine dédiée à la corruption (indépendante de celle du générateur :
# on peut regénérer les mêmes données propres avec d'autres défauts, et vice versa)
DEFAULT_SEED_CORRUPTION = 2025

# Nomenclature stable des types de défauts — sera réutilisée telle quelle
# par les contrôles qualité pour croiser détections et vérité terrain.
DEFAUT_CHIRURGIE_AVANT_EXAMEN = "chirurgie_avant_examen"
DEFAUT_DOUBLON_INTER_CENTRES = "doublon_inter_centres"
DEFAUT_DIVERGENCE_TAILLE = "divergence_taille_imagerie_anapath"
DEFAUT_COMPLETUDE_SCORE_RENAL = "completude_degradee_score_renal"

# Colonnes du rapport de vérité terrain
_COLONNES_RAPPORT = {
    "table": pl.String,
    "defaut": pl.String,
    "id_ligne": pl.Int64,
    "detail": pl.String,
}


def _corrompre_dates_chirurgie(
    chirurgie: pl.DataFrame,
    examen: pl.DataFrame,
    rng: random.Random,
    n_defauts: int,
) -> tuple[pl.DataFrame, list[dict]]:
    """Antidate n chirurgies avant le bilan pré-thérapeutique du patient.

    Simule l'erreur de saisie de date eCRF (année/mois erroné), fréquente
    en multicentrique. Défaut inter-tables : indétectable par les schémas
    Pandera (qui valident table par table), détectable en SQL.
    """
    k = min(n_defauts, chirurgie.height)
    cibles = rng.sample(chirurgie["chirurgie_id"].to_list(), k=k)

    # Date d'examen de référence (le plus ancien bilan du patient)
    examen_ref = examen.group_by("patient_id").agg(
        pl.col("date_examen").min().alias("date_examen_ref")
    )
    jointes = chirurgie.join(examen_ref, on="patient_id", how="left")

    remplacements: list[dict] = []
    rapport: list[dict] = []
    for ligne in jointes.filter(pl.col("chirurgie_id").is_in(cibles)).iter_rows(
        named=True
    ):
        nouvelle_date = ligne["date_examen_ref"] - timedelta(days=rng.randint(30, 365))
        remplacements.append(
            {"chirurgie_id": ligne["chirurgie_id"], "date_corrompue": nouvelle_date}
        )
        rapport.append(
            {
                "table": "chirurgie",
                "defaut": DEFAUT_CHIRURGIE_AVANT_EXAMEN,
                "id_ligne": ligne["chirurgie_id"],
                "detail": (
                    f"date_chirurgie {ligne['date_chirurgie']} → {nouvelle_date} "
                    f"(examen de référence : {ligne['date_examen_ref']})"
                ),
            }
        )

    df_remplacements = pl.DataFrame(
        remplacements, schema={"chirurgie_id": pl.Int64, "date_corrompue": pl.Date}
    )
    corrompue = (
        chirurgie.join(df_remplacements, on="chirurgie_id", how="left")
        .with_columns(
            pl.coalesce("date_corrompue", "date_chirurgie").alias("date_chirurgie")
        )
        .drop("date_corrompue")
    )
    return corrompue, rapport


def _corrompre_doublons_patients(
    patient: pl.DataFrame,
    centre: pl.DataFrame,
    rng: random.Random,
    n_defauts: int,
) -> tuple[pl.DataFrame, list[dict]]:
    """Duplique n patients dans un autre centre, avec une nouvelle clé.

    Simule le doublon inter-centres : même personne incluse deux fois.
    La nouvelle clé garde les 4 lettres (même prénom/nom) mais change de
    numéro d'inclusion — l'unicité de cle_uroccr est donc respectée :
    seul un rapprochement (naissance + sexe + lettres) peut le détecter.
    """
    k = min(n_defauts, patient.height)
    cibles = rng.sample(patient["patient_id"].to_list(), k=k)
    prochain_id = patient["patient_id"].max() + 1
    tous_centres = centre["centre_id"].to_list()

    doublons: list[dict] = []
    rapport: list[dict] = []
    for ligne in patient.filter(pl.col("patient_id").is_in(cibles)).iter_rows(
        named=True
    ):
        autres_centres = [c for c in tous_centres if c != ligne["centre_id"]]
        doublon = dict(ligne)
        doublon["patient_id"] = prochain_id
        doublon["cle_uroccr"] = f"{ligne['cle_uroccr'][:4]}{prochain_id:05d}"
        doublon["centre_id"] = rng.choice(autres_centres)
        # Seconde inclusion plus tardive, bornée par les dernières nouvelles
        doublon["date_inclusion"] = min(
            ligne["date_inclusion"] + timedelta(days=rng.randint(60, 540)),
            ligne["date_dernieres_nouvelles"],
        )
        doublons.append(doublon)
        rapport.append(
            {
                "table": "patient",
                "defaut": DEFAUT_DOUBLON_INTER_CENTRES,
                "id_ligne": prochain_id,
                "detail": (
                    f"doublon du patient {ligne['patient_id']} "
                    f"(centre {ligne['centre_id']} → {doublon['centre_id']})"
                ),
            }
        )
        prochain_id += 1

    corrompue = pl.concat([patient, pl.DataFrame(doublons, schema=patient.schema)])
    return corrompue, rapport


def _corrompre_divergence_taille(
    anapath: pl.DataFrame,
    rng: random.Random,
    n_defauts: int,
) -> tuple[pl.DataFrame, list[dict]]:
    """Rend n tailles anapath aberrantes vs l'imagerie (erreur d'unité type cm/mm).

    On reste dans les bornes du contrat (1-250 mm) : le défaut est
    contractuellement valide, seul le croisement avec l'imagerie le révèle.
    """
    k = min(n_defauts, anapath.height)
    cibles = rng.sample(anapath["anapath_id"].to_list(), k=k)

    remplacements: list[dict] = []
    rapport: list[dict] = []
    for ligne in anapath.filter(pl.col("anapath_id").is_in(cibles)).iter_rows(
        named=True
    ):
        taille = ligne["taille_tumorale_mm"]
        delta = rng.randint(60, 120) * rng.choice([-1, 1])
        nouvelle = max(1, min(250, taille + delta))
        if abs(nouvelle - taille) < 40:  # le clamp a trop réduit l'écart : on inverse
            nouvelle = max(1, min(250, taille - delta))
        remplacements.append(
            {"anapath_id": ligne["anapath_id"], "taille_corrompue": nouvelle}
        )
        rapport.append(
            {
                "table": "anatomopathologie",
                "defaut": DEFAUT_DIVERGENCE_TAILLE,
                "id_ligne": ligne["anapath_id"],
                "detail": f"taille_tumorale_mm {taille} → {nouvelle}",
            }
        )

    df_remplacements = pl.DataFrame(
        remplacements, schema={"anapath_id": pl.Int64, "taille_corrompue": pl.Int64}
    )
    corrompue = (
        anapath.join(df_remplacements, on="anapath_id", how="left")
        .with_columns(
            pl.coalesce("taille_corrompue", "taille_tumorale_mm").alias(
                "taille_tumorale_mm"
            )
        )
        .drop("taille_corrompue")
    )
    return corrompue, rapport


def _corrompre_completude_score_renal(
    examen: pl.DataFrame,
    patient: pl.DataFrame,
    centre: pl.DataFrame,
    rng: random.Random,
    proportion: float = 0.8,
) -> tuple[pl.DataFrame, list[dict]]:
    """Vide le score RENAL pour une forte proportion des examens CH/Privé.

    Défaut de *pattern* : pris ligne à ligne, un null est licite (colonne
    nullable). C'est la complétude par type de centre, comparée entre
    centres, qui révèle l'anomalie — d'où les futurs indicateurs qualité.
    """
    centres_cibles = centre.filter(pl.col("type_centre").is_in(["CH", "Privé"]))[
        "centre_id"
    ].to_list()
    patients_cibles = patient.filter(pl.col("centre_id").is_in(centres_cibles))[
        "patient_id"
    ].to_list()
    candidats = examen.filter(
        pl.col("patient_id").is_in(patients_cibles)
        & pl.col("score_renal").is_not_null()
    )["examen_id"].to_list()
    cibles = rng.sample(candidats, k=int(len(candidats) * proportion))

    corrompue = examen.with_columns(
        pl.when(pl.col("examen_id").is_in(cibles))
        .then(pl.lit(None, dtype=pl.Int64))
        .otherwise(pl.col("score_renal"))
        .alias("score_renal")
    )
    rapport = [
        {
            "table": "examen_pretherapeutique",
            "defaut": DEFAUT_COMPLETUDE_SCORE_RENAL,
            "id_ligne": examen_id,
            "detail": "score_renal vidé (centre CH/Privé)",
        }
        for examen_id in sorted(cibles)
    ]
    return corrompue, rapport


def corrompre_eds(
    tables: dict[str, pl.DataFrame],
    seed: int = DEFAULT_SEED_CORRUPTION,
    n_dates_chirurgie: int = 3,
    n_doublons: int = 2,
    n_divergences_taille: int = 3,
    proportion_score_renal: float = 0.8,
) -> tuple[dict[str, pl.DataFrame], pl.DataFrame]:
    """Applique l'ensemble des défauts à une copie de l'EDS.

    Returns:
        (tables corrompues, rapport de vérité terrain).
        Les tables non ciblées sont retournées telles quelles.
    """
    rng = random.Random(seed)
    corrompues = dict(tables)
    verite_terrain: list[dict] = []

    corrompues["chirurgie"], rapport = _corrompre_dates_chirurgie(
        tables["chirurgie"],
        tables["examen_pretherapeutique"],
        rng,
        n_defauts=n_dates_chirurgie,
    )
    verite_terrain.extend(rapport)

    corrompues["patient"], rapport = _corrompre_doublons_patients(
        tables["patient"], tables["centre"], rng, n_defauts=n_doublons
    )
    verite_terrain.extend(rapport)

    corrompues["anatomopathologie"], rapport = _corrompre_divergence_taille(
        tables["anatomopathologie"], rng, n_defauts=n_divergences_taille
    )
    verite_terrain.extend(rapport)

    corrompues["examen_pretherapeutique"], rapport = _corrompre_completude_score_renal(
        tables["examen_pretherapeutique"],
        tables["patient"],
        tables["centre"],
        rng,
        proportion=proportion_score_renal,
    )
    verite_terrain.extend(rapport)

    return corrompues, pl.DataFrame(verite_terrain, schema=_COLONNES_RAPPORT)
