-- OMOP CONDITION_OCCURRENCE — le cancer du rein, via le sous-type histologique.
select
    a.anapath_id                         as condition_occurrence_id,
    a.patient_id                         as person_id,
    coalesce(m.target_concept_id, 0)     as condition_concept_id,
    c.date_chirurgie                     as condition_start_date,
    32817                                as condition_type_concept_id,   -- EHR
    a.type_histologique                  as condition_source_value
from {{ ref('silver_anatomopathologie') }} as a
join {{ ref('silver_chirurgie') }} as c on a.chirurgie_id = c.chirurgie_id
left join {{ ref('source_to_concept_map') }} as m
    on a.type_histologique = m.source_value