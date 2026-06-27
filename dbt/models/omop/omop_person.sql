-- OMOP-CDM — table PERSON (une ligne par personne physique).
-- gender_concept_id : 8507 = MALE, 8532 = FEMALE (vrais concepts standard OMOP).
-- race / ethnicity à 0 : non collectées en France (interdit) ; 0 = « aucun
-- concept » au sens OMOP. person_source_value conserve la clé d'origine.
select
    p.patient_id                          as person_id,
    case p.sexe
        when 'H' then 8507
        when 'F' then 8532
        else 0
    end                                   as gender_concept_id,
    extract(year  from p.date_naissance)  as year_of_birth,
    extract(month from p.date_naissance)  as month_of_birth,
    extract(day   from p.date_naissance)  as day_of_birth,
    cast(p.date_naissance as timestamp)   as birth_datetime,
    0                                     as race_concept_id,
    0                                     as ethnicity_concept_id,
    p.centre_id                           as care_site_id,
    p.cle_uroccr                          as person_source_value,
    p.sexe                                as gender_source_value
from {{ ref('silver_patient') }} as p