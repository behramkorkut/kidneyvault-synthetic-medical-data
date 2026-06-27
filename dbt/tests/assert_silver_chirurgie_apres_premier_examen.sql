-- La règle d'exclusion de silver_chirurgie est effective :
-- aucune chirurgie Silver n'est antérieure au premier bilan.
with premier_examen as (
    select patient_id, min(date_examen) as date_premier_examen
    from {{ ref('stg_examen_pretherapeutique') }}
    group by patient_id
)

select c.chirurgie_id
from {{ ref('silver_chirurgie') }} as c
join premier_examen as e using (patient_id)
where c.date_chirurgie < e.date_premier_examen