select
    chirurgie_id,
    patient_id,
    date_chirurgie,
    type_chirurgie,
    voie_abord,
    duree_minutes,
    complications

from{{ source('bronze', 'chirurgie')}}