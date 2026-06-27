-- Patients dédoublonnés : pour chaque groupe de doublons probables
-- (même naissance + sexe + lettres de clé), on conserve l'inclusion
-- la PLUS ANCIENNE (la première trace du patient dans le réseau).
with classement as (
    select
        *,
        row_number() over (
            partition by date_naissance, sexe, left(cle_uroccr, 4)
            order by date_inclusion, patient_id
        ) as rang_inclusion
    from {{ ref('stg_patient') }}
)

select
    patient_id,
    cle_uroccr,
    centre_id,
    date_naissance,
    sexe,
    date_inclusion,
    statut_vital,
    date_dernieres_nouvelles
from classement
where rang_inclusion = 1
