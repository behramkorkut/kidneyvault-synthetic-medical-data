select
    centre_id,
    nom_centre,
    type_centre,
    region
from {{ source('bronze', 'centre') }}