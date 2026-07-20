-- Datamart « jeu de données chercheur » : une ligne par patient, variables
-- d'analyse à plat. Construit sur la Silver (donc dédoublonné, chirurgies
-- douteuses exclues). Prêt à charger dans R/SAS sans jointure.

with chirurgie as (
    -- Une chirurgie de référence par patient (la première plausible).
    select
        patient_id,
        min(date_chirurgie) as date_chirurgie,
        arg_min(type_chirurgie, date_chirurgie) as type_chirurgie,
        arg_min(voie_abord, date_chirurgie)     as voie_abord
    from {{ ref('silver_chirurgie') }}
    group by patient_id
),

anapath as (
    -- Une anapath de référence par patient (via sa chirurgie).
    select
        patient_id,
        any_value(type_histologique) as type_histologique,
        max(grade_isup)              as grade_isup,
        bool_or(taille_divergente)   as taille_divergente
    from {{ ref('silver_anatomopathologie') }}
    group by patient_id
),

suivi as (
    select
        patient_id,
        count(*)            as n_suivis,
        max(date_suivi)     as date_dernier_suivi,
        bool_or(recidive)   as a_recidive,
        -- Localisation de la PREMIÈRE récidive (la plus précoce).
        -- FILTER ne garde que les consultations avec récidive ;
        -- arg_min renvoie la localisation à la date la plus ancienne.
        arg_min(localisation_recidive, date_suivi)
            filter (where recidive) as localisation_premiere_recidive
    from {{ ref('silver_suivi') }}
    group by patient_id
),

traitement as (
    select
        patient_id,
        count(*)                  as n_lignes_traitement,
        max(ligne_traitement)     as ligne_max,
        bool_or(arret_pour_toxicite) as arret_toxicite
    from {{ ref('silver_traitement_oncologie') }}
    group by patient_id
)

select
    p.patient_id,
    p.cle_uroccr,
    c_ref.type_centre,
    c_ref.region,
    p.sexe,
    date_diff('year', p.date_naissance, p.date_inclusion) as age_inclusion,
    p.date_inclusion,
    p.statut_vital,
    p.date_dernieres_nouvelles,
    date_diff('month', p.date_inclusion, p.date_dernieres_nouvelles) as suivi_mois,

    -- Parcours chirurgical
    ch.date_chirurgie is not null as a_ete_opere,
    ch.type_chirurgie,
    ch.voie_abord,

    -- Anatomopathologie
    a.type_histologique,
    a.grade_isup,
    coalesce(a.taille_divergente, false) as anapath_taille_divergente,

    -- Suivi longitudinal
    coalesce(s.n_suivis, 0) as n_suivis,
    coalesce(s.a_recidive, false) as a_recidive,
    s.localisation_premiere_recidive,
    s.date_dernier_suivi,

    -- Oncologie
    coalesce(t.n_lignes_traitement, 0) as n_lignes_traitement,
    coalesce(t.arret_toxicite, false) as arret_pour_toxicite

from {{ ref('silver_patient') }} as p
left join {{ ref('silver_centre') }} as c_ref on p.centre_id = c_ref.centre_id
left join chirurgie  as ch using (patient_id)
left join anapath    as a  using (patient_id)
left join suivi      as s  using (patient_id)
left join traitement as t  using (patient_id)