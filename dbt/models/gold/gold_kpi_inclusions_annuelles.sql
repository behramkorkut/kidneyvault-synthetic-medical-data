-- KPI : flux d'inclusions par année (suivi d'activité du réseau).
select
    extract(year from date_inclusion)            as annee_inclusion,
    count(*)                                     as n_inclusions,
    sum(case when a_ete_opere then 1 else 0 end) as n_operes,
    sum(case when a_recidive then 1 else 0 end)  as n_recidives
from {{ ref('gold_cohorte_patient') }}
group by 1
order by 1