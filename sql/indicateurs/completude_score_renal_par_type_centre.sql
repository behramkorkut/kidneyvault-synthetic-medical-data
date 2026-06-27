-- Indicateur : taux de complétude du score RENAL par type de centre.
-- Un null isolé est licite (colonne nullable) ; c'est la comparaison ENTRE
-- centres qui révèle un problème de saisie systémique. En vie réelle, cet
-- indicateur déclenche un retour vers les ARC du centre concerné.
SELECT
    c.type_centre,
    COUNT(*)                                            AS n_examens,
    COUNT(e.score_renal)                                AS n_renseignes,
    ROUND(100.0 * COUNT(e.score_renal) / COUNT(*), 1)   AS completude_pct
FROM examen_pretherapeutique AS e
JOIN patient AS p USING (patient_id)
JOIN centre  AS c ON p.centre_id = c.centre_id
GROUP BY c.type_centre
ORDER BY completude_pct