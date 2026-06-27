-- Chirurgies plausibles : on écarte celles antérieures au premier bilan
-- pré-thérapeutique (erreur de saisie de date probable). Les lignes écartées
-- restent en Bronze et sont signalées par la couche qualité (sql/qualite/).
with premier_examen as (
    select patient_id, min(date_examen) as date_premier_examen
    from {{ ref('stg_examen_pretherapeutique') }}
    group by patient_id
)

select c.*
from {{ ref('stg_chirurgie') }} as c
join premier_examen as e using (patient_id)
where c.date_chirurgie >= e.date_premier_examen