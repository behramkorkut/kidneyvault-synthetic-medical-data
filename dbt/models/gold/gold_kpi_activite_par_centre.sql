-- KPI : activité et résultats agrégés par type de centre.
-- Agrégat descriptif (aucun patient nominatif) : la matière d'un dashboard.
select
    type_centre,
    count(*)                                                        as n_patients,
    round(100.0 * avg(case when a_ete_opere then 1 else 0 end), 1)  as pct_operes,
    round(100.0 * avg(case when a_recidive then 1 else 0 end), 1)   as pct_recidive,
    round(median(age_inclusion), 0)                                 as age_median,
    round(
        100.0 * sum(case when statut_vital = 'décédé' then 1 else 0 end)
        / count(*), 1
    )                                                               as pct_deces
from {{ ref('gold_cohorte_patient') }}
group by type_centre
order by n_patients desc