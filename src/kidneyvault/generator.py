"""Générateur de données synthétiques réalistes pour l'EDS KidneyVault.

Simule un parcours de soin cohérent en cancérologie rénale. Les données sont
générées patient par patient sous contraintes métier (cohérence stade →
parcours), avec une graine aléatoire pour la reproductibilité.

⚠️ Données 100 % synthétiques. Aucune donnée réelle de patient.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import polars as pl
from faker import Faker


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Graine par défaut : garantit la reproductibilité du jeu de données.
DEFAULT_SEED = 42

# Date d'extraction simulée de l'EDS : un entrepôt réel est figé au moment de
# son extraction, aucune donnée ne peut donc être postérieure à cette date.
# Constante (et non date.today()) pour préserver la reproductibilité.
DATE_EXTRACTION = date(2025, 12, 31)

# Référentiel de centres (noms synthétiques, types réalistes : CHU/CH/Privé/CLCC)
CENTRES = [
    ("CHU Bordeaux", "CHU", "Nouvelle-Aquitaine"),
    ("CHU Toulouse", "CHU", "Occitanie"),
    ("CH Pau", "CH", "Nouvelle-Aquitaine"),
    ("CH Bayonne", "CH", "Nouvelle-Aquitaine"),
    ("Clinique Bel-Air", "Privé", "Nouvelle-Aquitaine"),
    ("Clinique Saint-Jean", "Privé", "Occitanie"),
    ("Institut Bergonié", "CLCC", "Nouvelle-Aquitaine"),
    ("IUCT Oncopole", "CLCC", "Occitanie"),
]

# Profils de gravité initiaux et leurs proportions réalistes
STADES = ["localise", "localement_avance", "metastatique"]
STADES_POIDS = [0.70, 0.20, 0.10]


# --------------------------------------------------------------------------
# Génération du référentiel des centres
# --------------------------------------------------------------------------


def generer_centres(n_centres: int = 8) -> pl.DataFrame:
    """Génère la table `centre` à partir du référentiel prédéfini.

    On limite au nombre de centres demandé (max = len(CENTRES)).
    """
    selection = CENTRES[:n_centres]
    return pl.DataFrame(
        {
            "centre_id": list(range(1, len(selection) + 1)),
            "nom_centre": [c[0] for c in selection],
            "type_centre": [c[1] for c in selection],
            "region": [c[2] for c in selection],
        }
    )


# --------------------------------------------------------------------------
# Génération des patients
# --------------------------------------------------------------------------


def _cle_uroccr(faker: Faker, numero: int) -> str:
    """Reproduit le format de clé de pseudonymisation UroCCR :
    2 premières lettres du prénom + 2 du nom + numéro d'inclusion sur 5 chiffres.
    """
    prenom = faker.first_name()
    nom = faker.last_name()
    # On retire les accents/caractères spéciaux et on majuscule
    p = "".join(ch for ch in prenom if ch.isalpha())[:2].upper()
    n = "".join(ch for ch in nom if ch.isalpha())[:2].upper()
    return f"{p}{n}{numero:05d}"


def generer_patients(
    n_patients: int,
    n_centres: int,
    faker: Faker,
    rng: random.Random,
) -> pl.DataFrame:
    """Génère la table `patient` avec un stade de gravité par patient.

    Le stade est tiré ici car il pilotera tout le parcours en aval.
    On le conserve dans une colonne technique `_stade` (préfixe _ = interne,
    non destinée à la couche finale ; on la retirera avant persistance Bronze).
    """
    lignes = []
    for pid in range(1, n_patients + 1):
        # Date de naissance : adulte entre 30 et 85 ans à l'inclusion
        age_inclusion = rng.randint(30, 85)
        # Inclusion entre 2012 et 2023 (cohérent avec la profondeur UroCCR)
        annee_inclusion = rng.randint(2012, 2023)
        date_inclusion = date(annee_inclusion, rng.randint(1, 12), rng.randint(1, 28))
        date_naissance = date(
            annee_inclusion - age_inclusion,
            rng.randint(1, 12),
            rng.randint(1, 28),
        )

        stade = rng.choices(STADES, weights=STADES_POIDS, k=1)[0]

        # Statut vital : plus de décès chez les métastatiques
        proba_deces = {
            "localise": 0.05,
            "localement_avance": 0.20,
            "metastatique": 0.55,
        }
        decede = rng.random() < proba_deces[stade]
        statut_vital = "décédé" if decede else "vivant"

        # Dernières nouvelles : entre 1 et 10 ans après l'inclusion,
        # bornées par la date d'extraction de l'EDS (pas de date future)
        delai_jours = rng.randint(365, 365 * 10)
        date_dn = min(date_inclusion + timedelta(days=delai_jours), DATE_EXTRACTION)

        lignes.append(
            {
                "patient_id": pid,
                "cle_uroccr": _cle_uroccr(faker, pid),
                "centre_id": rng.randint(1, n_centres),
                "date_naissance": date_naissance,
                "sexe": rng.choices(["H", "F"], weights=[0.65, 0.35])[0],  # rein : +H
                "date_inclusion": date_inclusion,
                "statut_vital": statut_vital,
                "date_dernieres_nouvelles": date_dn,
                "_stade": stade,  # colonne technique interne
            }
        )

    return pl.DataFrame(lignes)


# --------------------------------------------------------------------------
# Fonctions d'aide cliniques (une règle métier = une fonction testable)
# --------------------------------------------------------------------------


def _tirer_taille_cT(stade: str, rng: random.Random) -> tuple[int, str]:
    """Tire une taille tumorale (mm) cohérente avec le stade, et le cT associé.

    Logique clinique simplifiée :
    - localisé : petites tumeurs (cT1a ≤ 40mm, cT1b 41-70mm)
    - localement avancé : tumeurs plus grosses ou envahissantes (cT2-cT4)
    - métastatique : souvent volumineuses (cT3-cT4)
    """
    if stade == "localise":
        if rng.random() < 0.6:
            return rng.randint(10, 40), "cT1a"
        return rng.randint(41, 70), "cT1b"
    if stade == "localement_avance":
        taille = rng.randint(71, 130)
        return taille, rng.choice(["cT2", "cT3"])
    # métastatique
    taille = rng.randint(80, 200)
    return taille, rng.choice(["cT3", "cT4"])


def _tirer_cN_cM(stade: str, rng: random.Random) -> tuple[str, str]:
    """Statut ganglionnaire (cN) et métastatique (cM) selon le stade."""
    if stade == "metastatique":
        return rng.choice(["cN0", "cN1"]), "cM1"
    if stade == "localement_avance":
        return rng.choice(["cN0", "cN1", "cNx"]), "cM0"
    return "cN0", "cM0"  # localisé


def _est_opere(stade: str, rng: random.Random) -> bool:
    """Décision chirurgicale selon le stade (probabilités cliniques)."""
    proba_chirurgie = {
        "localise": 0.95,
        "localement_avance": 0.85,
        "metastatique": 0.30,  # chirurgie cytoréductive, minoritaire
    }
    return rng.random() < proba_chirurgie[stade]


def _tirer_type_chirurgie(cT: str, rng: random.Random) -> str:
    """Partielle (préservation du rein) plutôt pour les petites tumeurs."""
    if cT == "cT1a":
        return "Néphrectomie partielle" if rng.random() < 0.8 else "Néphrectomie totale"
    if cT == "cT1b":
        return "Néphrectomie partielle" if rng.random() < 0.4 else "Néphrectomie totale"
    return "Néphrectomie totale"  # tumeurs plus grosses


def _tirer_histologie_grade(rng: random.Random) -> tuple[str, int | None]:
    """Type histologique et grade ISUP.

    Règle métier : le sous-type chromophobe ne se gradue pas en ISUP (→ None).
    Proportions réalistes : cellules claires majoritaire (~75%).
    """
    histo = rng.choices(
        ["Cellules claires", "Papillaire", "Chromophobe", "Autre"],
        weights=[0.75, 0.15, 0.07, 0.03],
    )[0]
    if histo == "Chromophobe":
        return histo, None  # pas de grade ISUP applicable
    grade = rng.choices([1, 2, 3, 4], weights=[0.2, 0.45, 0.25, 0.1])[0]
    return histo, grade


def _ct_vers_pt(cT: str, rng: random.Random) -> str:
    """Le pT (pathologique) est souvent proche du cT (clinique), parfois recalé."""
    correspondance = {
        "cT1a": "pT1a",
        "cT1b": "pT1b",
        "cT2": "pT2",
        "cT3": "pT3",
        "cT4": "pT4",
    }
    pt = correspondance.get(cT, "pT1a")
    # 15% de discordance clinico-pathologique (réaliste)
    if rng.random() < 0.15:
        return rng.choice(["pT1a", "pT1b", "pT2", "pT3"])
    return pt


# --------------------------------------------------------------------------
# Génération des entités cliniques (par patient)
# --------------------------------------------------------------------------


def _date_apres(
    date_ref: date, jours_min: int, jours_max: int, rng: random.Random
) -> date:
    """Tire une date située entre jours_min et jours_max après une date de référence."""
    return date_ref + timedelta(days=rng.randint(jours_min, jours_max))


def generer_parcours_clinique(
    patients: pl.DataFrame,
    rng: random.Random,
) -> dict[str, pl.DataFrame]:
    """Génère examen, chirurgie et anapath de façon cohérente, patient par patient.

    Retourne un dict de DataFrames : {"examen": ..., "chirurgie": ..., "anapath": ...}.
    L'anapath n'existe que si le patient a été opéré (règle métier).
    """
    examens: list[dict] = []
    chirurgies: list[dict] = []
    anapaths: list[dict] = []

    examen_id = chirurgie_id = anapath_id = 0

    for patient in patients.iter_rows(named=True):
        pid = patient["patient_id"]
        stade = patient["_stade"]
        date_inclusion = patient["date_inclusion"]

        # --- 1. Examen pré-thérapeutique (toujours au moins un) ---
        examen_id += 1
        taille, cT = _tirer_taille_cT(stade, rng)
        cN, cM = _tirer_cN_cM(stade, rng)
        date_examen = _date_apres(date_inclusion, 0, 30, rng)
        # score RENAL souvent absent en vraie vie (~40% manquant) -> on le gère ici
        score_renal = rng.randint(4, 12) if rng.random() < 0.6 else None

        examens.append(
            {
                "examen_id": examen_id,
                "patient_id": pid,
                "date_examen": date_examen,
                "type_imagerie": rng.choices(["Scanner", "IRM"], weights=[0.8, 0.2])[0],
                "taille_tumeur_mm": taille,
                "score_renal": score_renal,
                "lateralite": rng.choices(
                    ["Droit", "Gauche", "Bilatéral"], weights=[0.48, 0.48, 0.04]
                )[0],
                "cT": cT,
                "cN": cN,
                "cM": cM,
            }
        )

        # --- 2. Chirurgie (conditionnelle au stade) ---
        if _est_opere(stade, rng):
            chirurgie_id += 1
            type_chir = _tirer_type_chirurgie(cT, rng)
            date_chir = _date_apres(date_examen, 15, 90, rng)
            chirurgies.append(
                {
                    "chirurgie_id": chirurgie_id,
                    "patient_id": pid,
                    "date_chirurgie": date_chir,
                    "type_chirurgie": type_chir,
                    "voie_abord": rng.choices(
                        ["Ouverte", "Laparoscopique", "Robot-assistée"],
                        weights=[0.25, 0.35, 0.40],
                    )[0],
                    "duree_minutes": rng.randint(90, 300),
                    "complications": rng.choices(
                        ["Aucune", "I", "II", "III", "IV", "V"],
                        weights=[0.70, 0.10, 0.10, 0.06, 0.03, 0.01],
                    )[0],
                }
            )

            # --- 3. Anapath (existe SI ET SEULEMENT SI opéré) ---
            anapath_id += 1
            histo, grade = _tirer_histologie_grade(rng)
            # taille sur pièce : proche de l'imagerie, légère variation
            taille_piece = max(1, taille + rng.randint(-8, 8))
            anapaths.append(
                {
                    "anapath_id": anapath_id,
                    "patient_id": pid,
                    "chirurgie_id": chirurgie_id,
                    "type_histologique": histo,
                    "grade_isup": grade,
                    "taille_tumorale_mm": taille_piece,
                    "pT": _ct_vers_pt(cT, rng),
                    "pN": rng.choices(["pN0", "pN1", "pNx"], weights=[0.8, 0.1, 0.1])[
                        0
                    ],
                    "marges_chirurgicales": rng.choices(
                        ["Négatives", "Positives"], weights=[0.9, 0.1]
                    )[0],
                }
            )

    return {
        "examen": pl.DataFrame(examens),
        "chirurgie": pl.DataFrame(chirurgies),
        "anapath": pl.DataFrame(anapaths),
    }


# --------------------------------------------------------------------------
# Fonctions d'aide : oncologie et suivi
# --------------------------------------------------------------------------

# Cohérence molécule <-> classe thérapeutique (règle métier)
MOLECULE_PAR_CLASSE = {
    "Anti-angiogénique": ["Sunitinib", "Cabozantinib", "Axitinib"],
    "Immunothérapie": ["Nivolumab", "Pembrolizumab"],
    "Thérapie ciblée": ["Cabozantinib", "Axitinib"],
}


def _nb_lignes_traitement(stade: str, rng: random.Random) -> int:
    """Nombre de lignes de traitement systémique selon le stade.

    Localisé : 0 (sauf rare récidive, géré ailleurs). Métastatique : 1 à 4.
    """
    if stade == "metastatique":
        return rng.choices([1, 2, 3, 4], weights=[0.4, 0.3, 0.2, 0.1])[0]
    if stade == "localement_avance":
        return rng.choices([0, 1, 2], weights=[0.7, 0.2, 0.1])[0]
    return 0  # localisé


def _tirer_traitement(rng: random.Random) -> tuple[str, str]:
    """Tire une classe thérapeutique puis une molécule cohérente avec elle."""
    classe = rng.choice(list(MOLECULE_PAR_CLASSE.keys()))
    molecule = rng.choice(MOLECULE_PAR_CLASSE[classe])
    return classe, molecule


def _nb_suivis(stade: str, rng: random.Random) -> int:
    """Nombre de consultations de suivi (les cas graves sont suivis plus souvent)."""
    base = {"localise": (2, 6), "localement_avance": (3, 8), "metastatique": (3, 10)}
    return rng.randint(*base[stade])


def _proba_recidive(stade: str) -> float:
    """Probabilité de récidive par consultation selon le stade."""
    return {"localise": 0.05, "localement_avance": 0.20, "metastatique": 0.45}[stade]


def generer_suivi_et_oncologie(
    patients: pl.DataFrame,
    rng: random.Random,
) -> dict[str, pl.DataFrame]:
    """Génère le suivi longitudinal et les traitements oncologiques, par patient.

    Cohérences garanties :
    - statut "Décédé" en suivi seulement si le patient est décédé (statut_vital)
    - localisation_recidive renseignée seulement si recidive=True
    - traitements oncologiques surtout pour les stades avancés/métastatiques
    """
    suivis: list[dict] = []
    traitements: list[dict] = []

    suivi_id = traitement_id = 0

    for patient in patients.iter_rows(named=True):
        pid = patient["patient_id"]
        stade = patient["_stade"]
        date_inclusion = patient["date_inclusion"]
        date_dn = patient["date_dernieres_nouvelles"]
        patient_decede = patient["statut_vital"] == "décédé"

        # --- Traitements oncologiques (lignes successives) ---
        # Fenêtre d'observation : rien après les dernières nouvelles du patient.
        n_lignes = _nb_lignes_traitement(stade, rng)
        date_courante = _date_apres(date_inclusion, 30, 180, rng)
        for ligne in range(1, n_lignes + 1):
            if date_courante > date_dn:
                break  # hors fenêtre d'observation : lignes suivantes inconnues
            traitement_id += 1
            classe, molecule = _tirer_traitement(rng)
            duree = rng.randint(60, 400)
            date_fin = min(date_courante + timedelta(days=duree), date_dn)
            # dernière ligne parfois encore en cours -> date_fin null
            en_cours = (ligne == n_lignes) and (rng.random() < 0.3)
            traitements.append(
                {
                    "traitement_id": traitement_id,
                    "patient_id": pid,
                    "date_debut": date_courante,
                    "date_fin": None if en_cours else date_fin,
                    "ligne_traitement": ligne,
                    "classe_therapeutique": classe,
                    "molecule": molecule,
                    "reponse": rng.choices(
                        ["Complète", "Partielle", "Stable", "Progression"],
                        weights=[0.1, 0.3, 0.3, 0.3],
                    )[0],
                    "arret_pour_toxicite": rng.random() < 0.15,
                }
            )
            date_courante = date_fin + timedelta(days=rng.randint(15, 90))

        # --- Suivi longitudinal ---
        # On tire d'abord les dates, filtrées par la fenêtre d'observation,
        # PUIS on pose les statuts : le décès doit tomber sur le dernier
        # suivi réellement conservé (et non sur un suivi écarté car futur).
        n_suivis = _nb_suivis(stade, rng)
        dates_suivi: list[date] = []
        d = _date_apres(date_inclusion, 90, 180, rng)
        for _ in range(n_suivis):
            if d > date_dn:
                break
            dates_suivi.append(d)
            d = d + timedelta(days=rng.randint(90, 270))
        if not dates_suivi:
            # Règle 1..N suivis par patient : à défaut, un suivi unique
            # calé sur la date des dernières nouvelles.
            dates_suivi = [date_dn]

        deja_recidive = False
        proba_rec = _proba_recidive(stade)

        for i, date_suivi in enumerate(dates_suivi):
            suivi_id += 1
            # une fois récidivé, on le reste
            if not deja_recidive and rng.random() < proba_rec:
                deja_recidive = True
            recidive = deja_recidive
            localisation = (
                rng.choice(["Locale", "Poumon", "Os", "Foie", "Autre"])
                if recidive
                else None
            )

            # statut : le décès n'arrive qu'au dernier suivi, et seulement si
            # le patient est marqué décédé au global (cohérence inter-tables)
            dernier = i == len(dates_suivi) - 1
            if dernier and patient_decede:
                statut = "Décédé"
            elif recidive:
                statut = "Vivant avec maladie"
            else:
                statut = "Vivant sans maladie"

            suivis.append(
                {
                    "suivi_id": suivi_id,
                    "patient_id": pid,
                    "date_suivi": date_suivi,
                    "recidive": recidive,
                    "localisation_recidive": localisation,
                    "statut": statut,
                }
            )

    return {
        "suivi": pl.DataFrame(suivis),
        "traitement": pl.DataFrame(traitements),
    }


# --------------------------------------------------------------------------
# Orchestration : génère l'EDS complet (7 tables)
# --------------------------------------------------------------------------


def generer_eds(
    n_patients: int = 50,
    n_centres: int = 8,
    seed: int = DEFAULT_SEED,
    conserver_stade: bool = False,
) -> dict[str, pl.DataFrame]:
    """Génère l'EDS synthétique complet (7 tables cohérentes).

    Args:
        n_patients: nombre de patients à générer.
        n_centres: nombre de centres (max = len(CENTRES)).
        seed: graine aléatoire pour la reproductibilité.
        conserver_stade: si True, conserve la colonne technique `_stade` dans
            la table patient (usage : tests des propriétés métier). Ne pas
            utiliser pour la couche Bronze (le schéma Pandera la rejette).

    Returns:
        dict {nom_table: DataFrame} pour les 7 tables, prêtes pour la couche Bronze.
        La colonne technique `_stade` est retirée de la table patient.
    """
    faker = Faker("fr_FR")
    Faker.seed(seed)
    rng = random.Random(seed)

    centres = generer_centres(n_centres=n_centres)
    patients = generer_patients(
        n_patients=n_patients, n_centres=n_centres, faker=faker, rng=rng
    )
    parcours = generer_parcours_clinique(patients, rng=rng)
    longi = generer_suivi_et_oncologie(patients, rng=rng)

    return {
        "centre": centres,
        "patient": patients if conserver_stade else patients.drop("_stade"),
        "examen_pretherapeutique": parcours["examen"],
        "chirurgie": parcours["chirurgie"],
        "anatomopathologie": parcours["anapath"],
        "suivi": longi["suivi"],
        "traitement_oncologie": longi["traitement"],
    }
