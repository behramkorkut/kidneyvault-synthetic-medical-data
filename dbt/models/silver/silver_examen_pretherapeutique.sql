-- Bilans pré-thérapeutiques (imagerie) — interface Silver stable.
-- Pass-through typé : les examens sont conservés tels quels (aucune règle
-- d'exclusion ne s'applique à l'imagerie), mais exposés en Silver pour que
-- silver_chirurgie, silver_anatomopathologie, Gold et OMOP s'appuient sur la
-- couche nettoyée plutôt que sur le staging.
select
    examen_id,
    patient_id,
    date_examen,
    type_imagerie,
    taille_tumeur_mm,
    score_renal,
    lateralite,
    cT,
    cN,
    cM
from {{ ref('stg_examen_pretherapeutique') }}
