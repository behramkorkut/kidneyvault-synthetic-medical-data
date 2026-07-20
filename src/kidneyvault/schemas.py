"""Schémas Pandera — contrats de validation du modèle source (couche Bronze).

Chaque classe DataFrameModel encode le contrat décrit dans docs/data_dictionary.md :
types attendus, nullabilité, valeurs autorisées et règles métier inter-colonnes.

Validation des VALEURS : passer des pl.DataFrame (eager) à .validate(), pas des
LazyFrame (qui ne valident que le schéma).
"""

import pandera.polars as pa
import polars as pl


# Valeurs de référence (énumérations métier), centralisées pour réutilisation
TYPES_CENTRE = ["CHU", "CH", "Privé", "CLCC"]
SEXES = ["H", "F"]
STATUTS_VITAUX = ["vivant", "décédé"]
TYPES_IMAGERIE = ["Scanner", "IRM"]
LATERALITES = ["Droit", "Gauche", "Bilatéral"]
CT = ["cT1a", "cT1b", "cT2", "cT3", "cT4"]
CN = ["cN0", "cN1", "cNx"]
CM = ["cM0", "cM1"]
TYPES_CHIRURGIE = ["Néphrectomie partielle", "Néphrectomie totale"]
VOIES_ABORD = ["Ouverte", "Laparoscopique", "Robot-assistée"]
COMPLICATIONS = ["Aucune", "I", "II", "III", "IV", "V"]
TYPES_HISTO = ["Cellules claires", "Papillaire", "Chromophobe", "Autre"]
PT = ["pT1a", "pT1b", "pT2", "pT3", "pT4"]
PN = ["pN0", "pN1", "pNx"]
MARGES = ["Négatives", "Positives"]
LOCALISATIONS_RECIDIVE = ["Locale", "Poumon", "Os", "Foie", "Autre"]
STATUTS_SUIVI = ["Vivant sans maladie", "Vivant avec maladie", "Décédé"]
CLASSES_THERAPEUTIQUES = ["Anti-angiogénique", "Immunothérapie", "Thérapie ciblée"]
MOLECULES = ["Sunitinib", "Nivolumab", "Pembrolizumab", "Cabozantinib", "Axitinib"]
REPONSES_RECIST = ["Complète", "Partielle", "Stable", "Progression"]


class CentreSchema(pa.DataFrameModel):
    """Référentiel des centres participant au réseau."""

    centre_id: int = pa.Field(unique=True, ge=1)
    nom_centre: str = pa.Field(nullable=False)
    type_centre: str = pa.Field(isin=TYPES_CENTRE)
    region: str = pa.Field(nullable=False)

    class Config:
        strict = True  # rejette toute colonne non déclarée
        coerce = False  # ne convertit pas les types silencieusement


class PatientSchema(pa.DataFrameModel):
    """Entité pivot : un patient inclus dans le réseau."""

    patient_id: int = pa.Field(unique=True, ge=1)
    cle_uroccr: str = pa.Field(unique=True)  # clé de pseudonymisation unique
    centre_id: int = pa.Field(ge=1)  # FK → centre (intégrité vérifiée en dbt)
    date_naissance: pl.Date = pa.Field(nullable=False)
    sexe: str = pa.Field(isin=SEXES)
    date_inclusion: pl.Date = pa.Field(nullable=False)
    statut_vital: str = pa.Field(isin=STATUTS_VITAUX)
    date_dernieres_nouvelles: pl.Date = pa.Field(nullable=True)  # peut manquer

    class Config:
        strict = True
        coerce = False

    # Règle métier : on naît avant d'être inclus dans le réseau
    @pa.dataframe_check
    def naissance_avant_inclusion(cls, data) -> pl.LazyFrame:
        return data.lazyframe.select(
            pl.col("date_naissance") < pl.col("date_inclusion")
        )

    # Règle métier : les dernières nouvelles ne précèdent pas l'inclusion
    @pa.dataframe_check
    def dernieres_nouvelles_apres_inclusion(cls, data) -> pl.LazyFrame:
        return data.lazyframe.select(
            pl.col("date_dernieres_nouvelles").is_null()
            | (pl.col("date_dernieres_nouvelles") >= pl.col("date_inclusion"))
        )


class ExamenPretherapeutiqueSchema(pa.DataFrameModel):
    """Bilan d'imagerie avant traitement."""

    examen_id: int = pa.Field(unique=True, ge=1)
    patient_id: int = pa.Field(ge=1)
    date_examen: pl.Date = pa.Field(nullable=False)
    type_imagerie: str = pa.Field(isin=TYPES_IMAGERIE)
    taille_tumeur_mm: int = pa.Field(ge=1, le=250, nullable=True)
    score_renal: int = pa.Field(ge=4, le=12, nullable=True)
    lateralite: str = pa.Field(isin=LATERALITES)
    cT: str = pa.Field(isin=CT, nullable=True)
    cN: str = pa.Field(isin=CN, nullable=True)
    cM: str = pa.Field(isin=CM, nullable=True)

    class Config:
        strict = True
        coerce = False


class ChirurgieSchema(pa.DataFrameModel):
    """Acte chirurgical d'exérèse."""

    chirurgie_id: int = pa.Field(unique=True, ge=1)
    patient_id: int = pa.Field(ge=1)
    date_chirurgie: pl.Date = pa.Field(nullable=False)
    type_chirurgie: str = pa.Field(isin=TYPES_CHIRURGIE)
    voie_abord: str = pa.Field(isin=VOIES_ABORD)
    duree_minutes: int = pa.Field(ge=30, le=600, nullable=True)
    complications: str = pa.Field(isin=COMPLICATIONS, nullable=True)

    class Config:
        strict = True
        coerce = False


class AnatomopathologieSchema(pa.DataFrameModel):
    """Analyse de la pièce opératoire."""

    anapath_id: int = pa.Field(unique=True, ge=1)
    patient_id: int = pa.Field(ge=1)
    chirurgie_id: int = pa.Field(ge=1)
    type_histologique: str = pa.Field(isin=TYPES_HISTO)
    grade_isup: int = pa.Field(ge=1, le=4, nullable=True)  # NA pour chromophobe
    taille_tumorale_mm: int = pa.Field(ge=1, le=250)
    pT: str = pa.Field(isin=PT)
    pN: str = pa.Field(isin=PN, nullable=True)
    marges_chirurgicales: str = pa.Field(isin=MARGES)

    class Config:
        strict = True
        coerce = False


class SuiviSchema(pa.DataFrameModel):
    """Suivi longitudinal (données de vie réelle)."""

    suivi_id: int = pa.Field(unique=True, ge=1)
    patient_id: int = pa.Field(ge=1)
    date_suivi: pl.Date = pa.Field(nullable=False)
    recidive: bool = pa.Field(nullable=False)
    localisation_recidive: str = pa.Field(isin=LOCALISATIONS_RECIDIVE, nullable=True)
    statut: str = pa.Field(isin=STATUTS_SUIVI)

    class Config:
        strict = True
        coerce = False

    # Règle métier : pas de localisation de récidive si pas de récidive
    @pa.dataframe_check
    def coherence_recidive(cls, data) -> pl.LazyFrame:
        # Si recidive == False, localisation doit être nulle.
        # Condition valide = (recidive vrai) OU (localisation nulle)
        return data.lazyframe.select(
            pl.col("recidive") | pl.col("localisation_recidive").is_null()
        )


class TraitementOncologieSchema(pa.DataFrameModel):
    """Thérapie systémique (formes avancées/métastatiques)."""

    traitement_id: int = pa.Field(unique=True, ge=1)
    patient_id: int = pa.Field(ge=1)
    date_debut: pl.Date = pa.Field(nullable=False)
    date_fin: pl.Date = pa.Field(nullable=True)  # nulle = traitement en cours
    ligne_traitement: int = pa.Field(ge=1, le=5)
    classe_therapeutique: str = pa.Field(isin=CLASSES_THERAPEUTIQUES)
    molecule: str = pa.Field(isin=MOLECULES)
    reponse: str = pa.Field(isin=REPONSES_RECIST, nullable=True)
    arret_pour_toxicite: bool = pa.Field(nullable=False)

    class Config:
        strict = True
        coerce = False

    # Règle métier : la fin ne peut précéder le début (si fin renseignée)
    @pa.dataframe_check
    def fin_apres_debut(cls, data) -> pl.LazyFrame:
        return data.lazyframe.select(
            pl.col("date_fin").is_null() | (pl.col("date_fin") >= pl.col("date_debut"))
        )
