-- OMOP MEASUREMENT — mesures quantitatives du parcours.
-- Taille tumorale (imagerie + anapath) mappée au concept standard 4265162.
-- score R.E.N.A.L. et grade ISUP : concept_id 0 (pas de concept standard),
-- mais conservés via value_as_number + measurement_source_value — la bonne
-- pratique OMOP « source-only » pour ce qui n'est pas mappable.
with mesures as (

    select
        e.patient_id                        as person_id,
        e.date_examen                       as measurement_date,
        4265162                             as measurement_concept_id,
        cast(e.taille_tumeur_mm as double)  as value_as_number,
        'taille_tumeur_mm (imagerie)'       as measurement_source_value
    from {{ ref('silver_examen_pretherapeutique') }} as e
    where e.taille_tumeur_mm is not null

    union all

    select
        a.patient_id,
        c.date_chirurgie,
        4265162,
        cast(a.taille_tumorale_mm as double),
        'taille_tumorale_mm (anapath)'
    from {{ ref('silver_anatomopathologie') }} as a
    join {{ ref('silver_chirurgie') }} as c on a.chirurgie_id = c.chirurgie_id

    union all

    select
        e.patient_id,
        e.date_examen,
        0,
        cast(e.score_renal as double),
        'score_renal'
    from {{ ref('silver_examen_pretherapeutique') }} as e
    where e.score_renal is not null

    union all

    select
        a.patient_id,
        c.date_chirurgie,
        0,
        cast(a.grade_isup as double),
        'grade_isup'
    from {{ ref('silver_anatomopathologie') }} as a
    join {{ ref('silver_chirurgie') }} as c on a.chirurgie_id = c.chirurgie_id
    where a.grade_isup is not null

)

select
    row_number() over (
        order by person_id, measurement_date, measurement_source_value
    )                          as measurement_id,
    person_id,
    measurement_concept_id,
    measurement_date,
    32817                      as measurement_type_concept_id,  -- EHR
    value_as_number,
    measurement_source_value
from mesures