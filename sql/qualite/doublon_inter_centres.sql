-- Contrôle : doublon probable de patient entre deux centres.
-- Rapprochement sur date de naissance + sexe + lettres de la clé (prénom/nom).
-- La condition p1.patient_id < p2.patient_id évite de compter chaque paire
-- deux fois et désigne l'inclusion la plus récente comme doublon.
SELECT
    'patient'                 AS table_cible,
    'doublon_inter_centres'   AS defaut,
    p2.patient_id             AS id_ligne,
    'doublon probable du patient ' || p1.patient_id
        || ' (clés ' || p1.cle_uroccr || ' / ' || p2.cle_uroccr || ')' AS detail
FROM patient AS p1
JOIN patient AS p2
    ON  p1.date_naissance = p2.date_naissance
    AND p1.sexe = p2.sexe
    AND LEFT(p1.cle_uroccr, 4) = LEFT(p2.cle_uroccr, 4)
    AND p1.patient_id < p2.patient_id
WHERE p1.centre_id <> p2.centre_id