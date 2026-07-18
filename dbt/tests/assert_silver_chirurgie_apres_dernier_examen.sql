-- La règle d'exclusion de silver_chirurgie est effective : aucune chirurgie
-- Silver n'est antérieure au bilan pré-thérapeutique LE PLUS RÉCENT du patient
-- (règle M3 du data_dictionary). Les patients sans bilan sont hors périmètre
-- (leur chirurgie est conservée : voir silver_chirurgie).
with dernier_examen as (
    select patient_id, max(date_examen) as date_dernier_examen
    from {{ ref('silver_examen_pretherapeutique') }}
    group by patient_id
)

select c.chirurgie_id
from {{ ref('silver_chirurgie') }} as c
join dernier_examen as e using (patient_id)
where c.date_chirurgie < e.date_dernier_examen
