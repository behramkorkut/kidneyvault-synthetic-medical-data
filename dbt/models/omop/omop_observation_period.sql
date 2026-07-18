-- OMOP OBSERVATION_PERIOD — une période d'observation par personne.
-- Table REQUISE par l'écosystème OHDSI (Achilles, Data Quality Dashboard) :
-- sans elle, la plupart des analyses standard refusent de tourner. La période
-- court de l'inclusion aux dernières nouvelles ; type 32817 = EHR.
select
    row_number() over (order by patient_id)  as observation_period_id,
    patient_id                                as person_id,
    date_inclusion                            as observation_period_start_date,
    date_dernieres_nouvelles                  as observation_period_end_date,
    32817                                     as period_type_concept_id
from {{ ref('silver_patient') }}
