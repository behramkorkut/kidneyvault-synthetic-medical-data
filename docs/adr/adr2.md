# ADR 0002 — Standardisation OMOP-CDM en couche Silver

Date : 2026-06-27
Statut : Accepté

## Contexte

Les EDS de recherche français (dont celui du CHU de Bordeaux) s'appuient sur
**OMOP-CDM** (OHDSI) pour l'interopérabilité et la portabilité des analyses entre
institutions. Pour rapprocher KidneyVault d'un EDS réel, on mappe le modèle source
(Silver) vers OMOP-CDM.

## Décision

Construire une couche `dbt/models/omop/` qui mappe la Silver vers les tables
cliniques cœur d'OMOP-CDM : `person`, `condition_occurrence`,
`procedure_occurrence`, `drug_exposure`, `measurement`, `death`.

**Mapping du vocabulaire.** Le cœur d'OMOP n'est pas la structure mais la
traduction de chaque valeur source en **concept standard** (SNOMED, RxNorm…).
Plutôt que de charger les vocabulaires Athena complets (plusieurs Go), on
maintient un **seed curé** `source_to_concept_map` (à la manière de la table
OMOP `SOURCE_TO_CONCEPT_MAP`), dont les `concept_id` ont été relevés sur
[Athena](https://athena.ohdsi.org) en ne retenant que des concepts *Standard* et
*Valid* dans le bon domaine.

**Conventions.**
- Double colonne systématique : `*_concept_id` (standard) + `*_source_value`
  (valeur d'origine préservée).
- Ce qui n'a pas de concept standard (score R.E.N.A.L., grade ISUP) reste à
  `concept_id = 0` avec `value_as_number` + `source_value` — la convention OMOP
  pour le non-mappable, pas un pis-aller.
- `race_concept_id` / `ethnicity_concept_id` à `0` : ces données ne sont pas
  collectées en France (interdites par la loi).
- `*_type_concept_id = 32817` (« EHR »).

## Conséquences

+ Le projet démontre le mapping signature attendu dans un EDS français, avec un
  seed versionné et reproductible.
+ Le SQL standard et les outils OHDSI (ATLAS, HADES) pourraient interroger ces
  tables sans adaptation.
+ La frontière « mappable / non-mappable » est explicite et défendable.
- Le seed ne couvre que les quelques valeurs synthétiques du projet ; un mapping
  de production chargerait les vocabulaires Athena complets pour automatiser et
  valider la correspondance (cf. feuille de route).
- Les `concept_id` sont figés manuellement : ils devraient être revérifiés à
  chaque montée de version des vocabulaires OMOP.
