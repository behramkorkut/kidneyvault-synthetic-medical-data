select
    traitement_id,
    patient_id,
    date_debut,
    date_fin,
    ligne_traitement,
    classe_therapeutique,
    molecule,
    reponse,
    arret_pour_toxicite
from{{source('bronze', 'traitement_oncologie')}}