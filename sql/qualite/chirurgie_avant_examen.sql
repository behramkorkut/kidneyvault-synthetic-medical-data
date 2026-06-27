-- Contrôle : une chirurgie ne peut précéder le premier bilan pré-thérapeutique.
-- Règle métier du data dictionary (table chirurgie) ; inter-tables, donc
-- hors de portée des contrats Pandera.
SELECT
    'chirurgie'                AS table_cible,
    'chirurgie_avant_examen'   AS defaut,
    c.chirurgie_id             AS id_ligne,
    'date_chirurgie ' || CAST(c.date_chirurgie AS VARCHAR)
        || ' < premier examen ' || CAST(e.premier_examen AS VARCHAR) AS detail
FROM chirurgie AS c
JOIN (
    SELECT patient_id, MIN(date_examen) AS premier_examen
    FROM examen_pretherapeutique
    GROUP BY patient_id
) AS e USING (patient_id)
WHERE c.date_chirurgie < e.premier_examen