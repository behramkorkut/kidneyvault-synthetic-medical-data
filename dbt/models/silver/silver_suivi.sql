-- Consultations de suivi longitudinal — interface Silver stable.
-- Pass-through typé : le suivi est conservé intégralement (chaque consultation
-- compte pour l'analyse de récidive), exposé en Silver pour alimenter Gold sans
-- court-circuiter le staging.
select
    suivi_id,
    patient_id,
    date_suivi,
    recidive,
    localisation_recidive,
    statut
from {{ ref('stg_suivi') }}
