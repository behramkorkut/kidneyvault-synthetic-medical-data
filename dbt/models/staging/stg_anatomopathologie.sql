select
    anapath_id,
    patient_id,
    chirurgie_id,
    type_histologique,
    grade_isup,
    taille_tumorale_mm,
    pT,
    pN,
    marges_chirurgicales 

from{{ source('bronze', 'anatomopathologie')}}