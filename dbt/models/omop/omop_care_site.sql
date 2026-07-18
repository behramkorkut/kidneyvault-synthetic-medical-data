-- OMOP CARE_SITE — établissements du réseau, référencés par PERSON.care_site_id.
-- Complète l'intégrité du modèle : jusqu'ici PERSON.care_site_id pointait vers
-- une table inexistante. place_of_service_concept_id = 0 (le type
-- d'établissement n'est pas mappé à un concept standard ; conservé en source).
select
    centre_id    as care_site_id,
    nom_centre   as care_site_name,
    0            as place_of_service_concept_id,
    type_centre  as care_site_source_value
from {{ ref('silver_centre') }}
