-- KPI : répartition des sous-types histologiques (patients opérés).
-- La fenêtre sum(count(*)) over () calcule le total pour le pourcentage,
-- sans seconde requête.
select
    coalesce(type_histologique, 'Non opéré / inconnu') as type_histologique,
    count(*)                                           as n_patients,
    round(100.0 * count(*) / sum(count(*)) over (), 1) as pct
from {{ ref('gold_cohorte_patient') }}
group by 1
order by n_patients desc