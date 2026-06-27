-- Interface 1:1 sur la table patient Bronze.
select
    patient_id,
    cle_uroccr,
    centre_id,
    date_naissance,
    sexe,
    date_inclusion,
    statut_vital,
    date_dernieres_nouvelles
from {{ source('bronze', 'patient') }}