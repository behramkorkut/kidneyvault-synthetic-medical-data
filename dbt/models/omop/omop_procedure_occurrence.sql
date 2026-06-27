-- OMOP PROCEDURE_OCCURRENCE — actes chirurgicaux mappés via le seed.
select
    c.chirurgie_id                       as procedure_occurrence_id,
    c.patient_id                         as person_id,
    coalesce(m.target_concept_id, 0)     as procedure_concept_id,
    c.date_chirurgie                     as procedure_date,
    32817                                as procedure_type_concept_id,  -- EHR
    c.type_chirurgie                     as procedure_source_value
from {{ ref('silver_chirurgie') }} as c
left join {{ ref('source_to_concept_map') }} as m
    on c.type_chirurgie = m.source_value