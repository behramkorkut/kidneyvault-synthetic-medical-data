-- OMOP DRUG_EXPOSURE — thérapies systémiques mappées (ingrédient RxNorm).
select
    t.traitement_id                      as drug_exposure_id,
    t.patient_id                         as person_id,
    coalesce(m.target_concept_id, 0)     as drug_concept_id,
    t.date_debut                         as drug_exposure_start_date,
    coalesce(t.date_fin, t.date_debut)   as drug_exposure_end_date,
    32817                                as drug_type_concept_id,        -- EHR
    t.molecule                           as drug_source_value
from {{ ref('stg_traitement_oncologie') }} as t
left join {{ ref('source_to_concept_map') }} as m
    on t.molecule = m.source_value