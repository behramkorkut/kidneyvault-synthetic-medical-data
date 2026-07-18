-- Le drapeau date_fin_incoherente de silver_traitement_oncologie est fiable :
-- il vaut true SI ET SEULEMENT SI date_fin < date_debut. Ce test échoue s'il
-- laisse passer une incohérence (faux négatif) ou se déclenche à tort (faux
-- positif). C'est la garantie « chaque règle métier devient un test ».
select traitement_id
from {{ ref('silver_traitement_oncologie') }}
where date_fin is not null
  and (date_fin < date_debut) <> date_fin_incoherente
