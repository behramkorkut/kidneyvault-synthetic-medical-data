-- Dimension « centre » de référence, canonique pour toute la couche Silver/Gold.
-- Pass-through typé et documenté : le centre est une donnée de référence stable
-- (pas de nettoyage métier à appliquer). Son existence en Silver évite que Gold
-- et OMOP aillent chercher dans le staging (couche medallion cohérente).
select
    centre_id,
    nom_centre,
    type_centre,
    region
from {{ ref('stg_centre') }}
