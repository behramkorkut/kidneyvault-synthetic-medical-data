-- Chirurgies plausibles : une chirurgie doit suivre le bilan pré-thérapeutique
-- le plus récent du patient (règle du data_dictionary). Les chirurgies
-- antidatées (erreur de saisie probable) sont écartées ; elles restent en
-- Bronze et sont signalées par la couche qualité (sql/qualite/).
-- Les chirurgies SANS bilan pré-thérapeutique sont CONSERVÉES : leur absence
-- de bilan est une anomalie à signaler, pas une raison de les supprimer
-- silencieusement.
with dernier_examen as (
    select patient_id, max(date_examen) as date_dernier_examen
    from {{ ref('stg_examen_pretherapeutique') }}
    group by patient_id
)

select c.*
from {{ ref('stg_chirurgie') }} as c
left join dernier_examen as e using (patient_id)
where e.date_dernier_examen is null
   or c.date_chirurgie >= e.date_dernier_examen
