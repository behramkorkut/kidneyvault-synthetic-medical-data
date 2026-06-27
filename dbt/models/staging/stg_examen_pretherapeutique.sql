select
    examen_id,
    patient_id,
    date_examen, 
    type_imagerie, 
    taille_tumeur_mm,
    score_renal,
    lateralite,
    cT,
    cN,
    cM
from {{source('bronze', 'examen_pretherapeutique')}}