# ADR 0001 — Choix de la stack technique du cœur

Date : 2026-06-04
Statut : Accepté

## Contexte
Projet portfolio simulant un EDS de recherche oncologique (cancer du rein),
inspiré du réseau UroCCR / CHU de Bordeaux. Objectif : démontrer la chaîne
complète de gestion de données cliniques (ingestion → standardisation OMOP →
qualité → cohortes) avec une stack moderne, légère et reproductible.

## Décision
Stack légère pour le cœur :
- uv (gestion de projet et dépendances, Python 3.12)
- DuckDB (base analytique embarquée, zéro serveur)
- dbt-duckdb (transformations SQL versionnées, tests, lineage)
- Polars (génération et manipulation de données)
- Faker (données synthétiques + logique métier oncologique)
- Pandera (data contracts / validation de schéma)
- Streamlit (interface de screening / extraction de cohortes)
- Ruff + pytest (qualité de code et tests)

Version industrialisée prévue ultérieurement : Docker/Colima + Postgres + Dagster.

## Conséquences
+ Repo clonable et exécutable en local sans infra lourde.
+ Reproductibilité et auditabilité (lock file, versions épinglées).
+ Aucune donnée réelle ; données 100 % synthétiques.
- DuckDB en local ne reflète pas une vraie infra serveur : compensé par la
  version dockerisée Postgres + Dagster.
