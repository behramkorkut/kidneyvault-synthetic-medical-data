# Data Dictionary — KidneyVault

Document de référence du modèle de données source (couche Bronze) du projet
KidneyVault, un EDS de recherche oncologique simulé inspiré du réseau UroCCR
(cancer du rein, CHU de Bordeaux).

> ⚠️ Toutes les données sont **100 % synthétiques**. Aucune donnée réelle de
> patient n'est utilisée. Le modèle s'inspire des onglets cliniques publics
> d'UroCCR à des fins pédagogiques et de démonstration.

Date : 2026-06-04
Version : 1.0
Couche : Bronze (modèle source normalisé, fidèle à la saisie eCRF)

---

## Vue d'ensemble du modèle

Le modèle décrit le parcours de soin d'un patient atteint d'une tumeur du rein,
de l'inclusion au suivi longitudinal. L'entité pivot est le **patient**, autour
duquel gravitent des entités cliniques événementielles (datées).

### Entités et relations

| Entité                    | Description                              | Relation au patient |
|---------------------------|------------------------------------------|---------------------|
| `centre`                  | Référentiel des centres participants     | 1 centre → N patients |
| `patient`                 | Patient inclus dans le réseau            | Entité pivot |
| `examen_pretherapeutique` | Bilan d'imagerie avant traitement        | 1 patient → 1..N examens |
| `chirurgie`               | Acte chirurgical                         | 1 patient → 0..N chirurgies |
| `anatomopathologie`       | Analyse de la pièce opératoire           | 1 chirurgie → 0..1 anapath |
| `suivi`                   | Suivi longitudinal (données vie réelle)  | 1 patient → 1..N suivis |
| `traitement_oncologie`    | Thérapie systémique (formes avancées)    | 1 patient → 0..N traitements |

### Diagramme des relations (textuel)

centre (1) ──< patient (N) 
│               ├──< examen_pretherapeutique (1..N) 
                ├──< chirurgie (0..N) ──< anatomopathologie (0..1) 
                ├──< suivi (1..N) 
                └──< traitement_oncologie (0..N)


### Conventions générales

- **Clés primaires techniques** : suffixe `_id`, identifiant unique synthétique.
- **Clés étrangères** : reprennent le nom de la clé primaire référencée.
- **Dates** : format ISO 8601 (`YYYY-MM-DD`).
- **Pseudonymisation** : aucune donnée directement identifiante. La `cle_uroccr`
  reproduit le format du réseau (2 lettres prénom + 2 lettres nom + n° d'inclusion)
  mais est générée à partir de données synthétiques.
- **Nullabilité** : colonne `Null ?` à `Oui` = valeur manquante autorisée
  (fréquent en données de vie réelle).

---

## Table `centre`

Référentiel des centres participant au réseau (CHU, CH, centre privé, CLCC).

| Colonne       | Type    | Null ? | Description                                    | Valeurs autorisées |
|---------------|---------|--------|------------------------------------------------|--------------------|
| `centre_id`   | INTEGER | Non    | Identifiant unique du centre (PK)              | 1 à N |
| `nom_centre`  | VARCHAR | Non    | Nom du centre (synthétique)                    | texte libre |
| `type_centre` | VARCHAR | Non    | Catégorie d'établissement                      | `CHU`, `CH`, `Privé`, `CLCC` |
| `region`      | VARCHAR | Non    | Région d'implantation                          | régions FR métropole |

---

## Table `patient`

Entité pivot. Une ligne par patient inclus dans le réseau.

| Colonne                   | Type    | Null ? | Description                                  | Valeurs autorisées |
|---------------------------|---------|--------|----------------------------------------------|--------------------|
| `patient_id`              | INTEGER | Non    | Identifiant unique du patient (PK)           | 1 à N |
| `cle_uroccr`              | VARCHAR | Non    | Clé de pseudonymisation (format UroCCR-like) | ex. `JEDU00123` |
| `centre_id`               | INTEGER | Non    | Centre d'inclusion (FK → centre)             | clé existante |
| `date_naissance`          | DATE    | Non    | Date de naissance                            | < date_inclusion |
| `sexe`                    | VARCHAR | Non    | Sexe administratif                           | `H`, `F` |
| `date_inclusion`          | DATE    | Non    | Date d'entrée dans le réseau                 | ≥ 2012-01-01 |
| `statut_vital`            | VARCHAR | Non    | Statut vital à la dernière nouvelle          | `vivant`, `décédé` |
| `date_dernieres_nouvelles`| DATE    | Oui    | Date des dernières nouvelles connues         | ≥ date_inclusion |

**Règles métier**
- `date_naissance` < `date_inclusion` < `date_dernieres_nouvelles`.
- Si `statut_vital` = `décédé`, `date_dernieres_nouvelles` doit être renseignée.

---

## Table `examen_pretherapeutique`

Bilan d'imagerie réalisé avant le traitement. Plusieurs examens possibles.

| Colonne            | Type    | Null ? | Description                               | Valeurs autorisées |
|--------------------|---------|--------|-------------------------------------------|--------------------|
| `examen_id`        | INTEGER | Non    | Identifiant de l'examen (PK)              | 1 à N |
| `patient_id`       | INTEGER | Non    | Patient concerné (FK → patient)           | clé existante |
| `date_examen`      | DATE    | Non    | Date de réalisation                       | ≥ date_inclusion |
| `type_imagerie`    | VARCHAR | Non    | Modalité d'imagerie                       | `Scanner`, `IRM` |
| `taille_tumeur_mm` | INTEGER | Oui    | Plus grand diamètre tumoral (mm)          | 1 à 250 |
| `score_renal`      | INTEGER | Oui    | Score de complexité chirurgicale R.E.N.A.L| 4 à 12 |
| `lateralite`       | VARCHAR | Non    | Rein concerné                             | `Droit`, `Gauche`, `Bilatéral` |
| `cT`               | VARCHAR | Oui    | Classification T clinique (TNM)           | `cT1a`, `cT1b`, `cT2`, `cT3`, `cT4` |
| `cN`               | VARCHAR | Oui    | Classification N clinique (TNM)           | `cN0`, `cN1`, `cNx` |
| `cM`               | VARCHAR | Oui    | Classification M clinique (TNM)           | `cM0`, `cM1` |

**Règles métier**
- `taille_tumeur_mm` cohérente avec `cT` (ex. cT1a ≤ 40 mm).

---

## Table `chirurgie`

Acte chirurgical d'exérèse tumorale. Tous les patients n'opèrent pas
(surveillance active, traitement ablatif, formes d'emblée métastatiques).

| Colonne          | Type    | Null ? | Description                            | Valeurs autorisées |
|------------------|---------|--------|----------------------------------------|--------------------|
| `chirurgie_id`   | INTEGER | Non    | Identifiant de la chirurgie (PK)       | 1 à N |
| `patient_id`     | INTEGER | Non    | Patient concerné (FK → patient)        | clé existante |
| `date_chirurgie` | DATE    | Non    | Date de l'intervention                 | ≥ date_inclusion |
| `type_chirurgie` | VARCHAR | Non    | Type d'exérèse                         | `Néphrectomie partielle`, `Néphrectomie totale` |
| `voie_abord`     | VARCHAR | Non    | Voie d'abord chirurgicale              | `Ouverte`, `Laparoscopique`, `Robot-assistée` |
| `duree_minutes`  | INTEGER | Oui    | Durée opératoire (minutes)             | 30 à 600 |
| `complications`  | VARCHAR | Oui    | Complication post-op (Clavien-Dindo)   | `Aucune`, `I`, `II`, `III`, `IV`, `V` |

**Règles métier**
- `date_chirurgie` ≥ `date_examen` du bilan pré-thérapeutique le plus récent.

---

## Table `anatomopathologie`

Analyse de la pièce opératoire. Liée à une chirurgie (0..1 par chirurgie).

| Colonne                 | Type    | Null ? | Description                          | Valeurs autorisées |
|-------------------------|---------|--------|--------------------------------------|--------------------|
| `anapath_id`            | INTEGER | Non    | Identifiant de l'analyse (PK)        | 1 à N |
| `patient_id`            | INTEGER | Non    | Patient concerné (FK → patient)      | clé existante |
| `chirurgie_id`          | INTEGER | Non    | Chirurgie associée (FK → chirurgie)  | clé existante |
| `type_histologique`     | VARCHAR | Non    | Sous-type histologique               | `Cellules claires`, `Papillaire`, `Chromophobe`, `Autre` |
| `grade_isup`            | INTEGER | Oui    | Grade nucléaire ISUP/OMS             | 1 à 4 |
| `taille_tumorale_mm`    | INTEGER | Non    | Taille mesurée sur pièce (mm)        | 1 à 250 |
| `pT`                    | VARCHAR | Non    | Classification T pathologique (TNM)  | `pT1a`, `pT1b`, `pT2`, `pT3`, `pT4` |
| `pN`                    | VARCHAR | Oui    | Classification N pathologique (TNM)  | `pN0`, `pN1`, `pNx` |
| `marges_chirurgicales`  | VARCHAR | Non    | Statut des marges d'exérèse          | `Négatives`, `Positives` |

**Règles métier**
- `grade_isup` non applicable (Null) pour certains sous-types (ex. chromophobe).
- `taille_tumorale_mm` (sur pièce) peut différer de `taille_tumeur_mm` (imagerie).

---

## Table `suivi`

Suivi longitudinal du patient. Données de vie réelle, plusieurs lignes/patient.

| Colonne                 | Type    | Null ? | Description                         | Valeurs autorisées |
|-------------------------|---------|--------|-------------------------------------|--------------------|
| `suivi_id`              | INTEGER | Non    | Identifiant du suivi (PK)           | 1 à N |
| `patient_id`            | INTEGER | Non    | Patient concerné (FK → patient)     | clé existante |
| `date_suivi`            | DATE    | Non    | Date de la consultation de suivi    | ≥ date_inclusion |
| `recidive`              | BOOLEAN | Non    | Récidive constatée                  | `true`, `false` |
| `localisation_recidive` | VARCHAR | Oui    | Site de la récidive si applicable   | `Locale`, `Poumon`, `Os`, `Foie`, `Autre` |
| `statut`                | VARCHAR | Non    | Statut oncologique à la date        | `Vivant sans maladie`, `Vivant avec maladie`, `Décédé` |

**Règles métier**
- Si `recidive` = `false`, `localisation_recidive` doit être Null.
- Si `statut` = `Décédé`, le `statut_vital` patient doit être `décédé`.

---

## Table `traitement_oncologie`

Thérapie systémique pour formes avancées/métastatiques. Relation optionnelle
(0..N) : la majorité des patients (formes localisées) n'en reçoivent pas.

| Colonne               | Type    | Null ? | Description                              | Valeurs autorisées |
|-----------------------|---------|--------|------------------------------------------|--------------------|
| `traitement_id`       | INTEGER | Non    | Identifiant du traitement (PK)           | 1 à N |
| `patient_id`          | INTEGER | Non    | Patient concerné (FK → patient)          | clé existante |
| `date_debut`          | DATE    | Non    | Date de début du traitement              | ≥ date_inclusion |
| `date_fin`            | DATE    | Oui    | Date de fin (Null si en cours)           | ≥ date_debut |
| `ligne_traitement`    | INTEGER | Non    | Rang de la ligne thérapeutique           | 1 à 5 |
| `classe_therapeutique`| VARCHAR | Non    | Famille thérapeutique                    | `Anti-angiogénique`, `Immunothérapie`, `Thérapie ciblée` |
| `molecule`            | VARCHAR | Non    | Molécule administrée                     | ex. `Sunitinib`, `Nivolumab`, `Pembrolizumab`, `Cabozantinib`, `Axitinib` |
| `reponse`             | VARCHAR | Oui    | Réponse tumorale (critères RECIST)       | `Complète`, `Partielle`, `Stable`, `Progression` |
| `arret_pour_toxicite` | BOOLEAN | Non    | Arrêt anticipé pour toxicité             | `true`, `false` |

**Règles métier**
- `ligne_traitement` croissante dans le temps pour un même patient.
- Cohérence `classe_therapeutique` / `molecule` (ex. Nivolumab → Immunothérapie).

---

## Notes sur la qualité des données (données de vie réelle)

Conformément à la réalité d'un EDS multicentrique, le générateur de données
introduira **volontairement** des imperfections réalistes que les couches de
contrôle qualité devront détecter :

- valeurs manquantes non aléatoires (ex. `score_renal` souvent absent) ;
- incohérences de dates inter-tables ;
- doublons potentiels inter-centres (même patient suivi dans 2 centres) ;
- divergences imagerie/anapath sur la taille tumorale ;
- variabilité de complétude selon le `type_centre`.

Ces défauts sont la matière première de la couche qualité (Pandera + dbt tests).
