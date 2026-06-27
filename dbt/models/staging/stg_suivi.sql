select
    suivi_id,
    patient_id,
    date_suivi,
    recidive,
    localisation_recidive,
    statut
from{{ source('bronze', 'suivi')}}