-- OMOP CONDITION_OCCURRENCE — le cancer du rein.
-- Tout patient inclus dans UroCCR a un cancer du rein : on garantit AU MOINS
-- une occurrence par personne. Quand l'anatomopathologie existe, on mappe le
-- sous-type histologique au concept standard (via le seed). Sinon (non-opéré,
-- ou chirurgie sans anapath), on émet une occurrence « base » datée de
-- l'inclusion, concept 0 (sous-type non déterminé) — c'est la correction du
-- trou de couverture : les non-opérés n'apparaissaient nulle part.
with anapath_condition as (
    select
        a.patient_id                     as person_id,
        coalesce(m.target_concept_id, 0) as condition_concept_id,
        c.date_chirurgie                 as condition_start_date,
        a.type_histologique              as condition_source_value
    from {{ ref('silver_anatomopathologie') }} as a
    join {{ ref('silver_chirurgie') }} as c on a.chirurgie_id = c.chirurgie_id
    left join {{ ref('source_to_concept_map') }} as m
        on a.type_histologique = m.source_value
),

base_condition as (
    select
        p.patient_id     as person_id,
        0                as condition_concept_id,
        p.date_inclusion as condition_start_date,
        'Cancer du rein (inclusion, sans anatomopathologie)'
                         as condition_source_value
    from {{ ref('silver_patient') }} as p
    where p.patient_id not in (select person_id from anapath_condition)
),

toutes as (
    select * from anapath_condition
    union all
    select * from base_condition
)

select
    row_number() over (
        order by person_id, condition_start_date, condition_source_value
    )                          as condition_occurrence_id,
    person_id,
    condition_concept_id,
    condition_start_date,
    32817                      as condition_type_concept_id,   -- EHR
    condition_source_value
from toutes
