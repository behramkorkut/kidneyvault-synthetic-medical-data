-- OMOP DEATH — une ligne par personne décédée.
select
    patient_id                  as person_id,
    date_dernieres_nouvelles    as death_date,
    32817                       as death_type_concept_id,   -- EHR
    0                           as cause_concept_id          -- cause non codée
from {{ ref('silver_patient') }}
where statut_vital = 'décédé'