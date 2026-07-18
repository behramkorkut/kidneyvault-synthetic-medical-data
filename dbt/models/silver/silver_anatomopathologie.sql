-- Anapaths enrichies d'un drapeau de divergence avec l'imagerie.
-- Référence : le bilan pré-thérapeutique le plus récent du patient — une seule
-- ligne par patient, donc AUCUN fan-out possible si un patient cumule
-- plusieurs examens (le test d'unicité sur anapath_id le garantit).
-- On ne corrige PAS (impossible de savoir quelle mesure est la bonne) :
-- on flague, et le chercheur décide selon son protocole. Une taille manquante
-- (examen absent ou mesure nulle) donne taille_divergente = false : les
-- données manquantes relèvent de la couche qualité, pas de ce drapeau.
with dernier_examen as (
    select patient_id, taille_tumeur_mm
    from {{ ref('stg_examen_pretherapeutique') }}
    qualify row_number() over (
        partition by patient_id
        order by date_examen desc
    ) = 1
)

select
    a.*,
    coalesce(
        abs(a.taille_tumorale_mm - e.taille_tumeur_mm) > 30,
        false
    ) as taille_divergente
from {{ ref('stg_anatomopathologie') }} as a
left join dernier_examen as e using (patient_id)
