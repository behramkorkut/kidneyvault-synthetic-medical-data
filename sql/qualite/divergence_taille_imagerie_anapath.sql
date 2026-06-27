-- Contrôle : taille sur pièce opératoire incohérente avec l'imagerie.
-- Seuil : 30 mm. Justification : la variation de mesure naturelle est de
-- l'ordre de ±8 mm ; au-delà de 30 mm on suspecte une erreur de saisie
-- (unité cm/mm, inversion de champs). Un seuil est une DÉCISION : on la
-- documente ici pour pouvoir la discuter et l'ajuster.
SELECT
    'anatomopathologie'                    AS table_cible,
    'divergence_taille_imagerie_anapath'   AS defaut,
    a.anapath_id                           AS id_ligne,
    'taille anapath ' || a.taille_tumorale_mm
        || ' mm vs imagerie ' || e.taille_tumeur_mm || ' mm' AS detail
FROM anatomopathologie AS a
JOIN examen_pretherapeutique AS e USING (patient_id)
WHERE ABS(a.taille_tumorale_mm - e.taille_tumeur_mm) > 30