-- Anapaths enrichies d'un drapeau de divergence avec l'imagerie.
-- On ne corrige PAS (impossible de savoir quelle mesure est la bonne) :
-- on flague, et le chercheur décide selon son protocole.
select
    a.*,
    abs(a.taille_tumorale_mm - e.taille_tumeur_mm) > 30 as taille_divergente
from {{ ref('stg_anatomopathologie') }} as a
join {{ ref('stg_examen_pretherapeutique') }} as e using (patient_id)