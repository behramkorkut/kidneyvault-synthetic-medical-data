-- Lignes de traitement systémique — interface Silver avec contrôle de cohérence.
-- On NE supprime PAS : on enrichit d'un drapeau de date incohérente
-- (date_fin < date_debut, saisie douteuse) et de la durée en jours, laissée à
-- NULL quand la fin est absente (traitement en cours) ou incohérente. Le
-- chercheur décide selon son protocole ; la couche qualité (sql/qualite/)
-- recense les lignes signalées.
select
    traitement_id,
    patient_id,
    date_debut,
    date_fin,
    ligne_traitement,
    classe_therapeutique,
    molecule,
    reponse,
    arret_pour_toxicite,
    coalesce(date_fin < date_debut, false) as date_fin_incoherente,
    case
        when date_fin is not null and date_fin >= date_debut
        then date_diff('day', date_debut, date_fin)
    end as duree_traitement_jours
from {{ ref('stg_traitement_oncologie') }}
