"""Évaluation de la couche qualité contre la vérité terrain du corrupteur.

Croise les anomalies détectées (contrôles SQL) avec les défauts injectés :
- rappel : part des défauts injectés effectivement détectés (rien raté ?) ;
- précision : part des détections qui sont de vrais défauts (pas de bruit ?).

Les défauts de *pattern* (complétude dégradée) ne sont pas évaluables ligne
à ligne : un null isolé est licite, c'est la distribution par centre qui est
anormale. Ils relèvent d'indicateurs agrégés, traités séparément.
"""

from pathlib import Path

import polars as pl

from kidneyvault.corrupteur import DEFAUT_COMPLETUDE_SCORE_RENAL
from kidneyvault.qualite import connexion_bronze, executer_controles

CHEMIN_VERITE_TERRAIN = Path("data/00_raw/verite_terrain_defauts.parquet")


def evaluer(anomalies: pl.DataFrame, verite_terrain: pl.DataFrame) -> pl.DataFrame:
    """Rappel et précision par type de défaut (granularité ligne)."""
    cle = ["defaut", "id_ligne"]
    injectes = (
        verite_terrain.filter(pl.col("defaut") != DEFAUT_COMPLETUDE_SCORE_RENAL)
        .select(cle)
        .unique()
    )
    detections = anomalies.select(cle).unique()

    defauts = sorted(
        set(injectes["defaut"].to_list()) | set(detections["defaut"].to_list())
    )
    lignes = []
    for defaut in defauts:
        d = detections.filter(pl.col("defaut") == defaut)
        i = injectes.filter(pl.col("defaut") == defaut)
        vrais_positifs = d.join(i, on=cle, how="inner").height
        lignes.append(
            {
                "defaut": defaut,
                "injectes": i.height,
                "detectes": d.height,
                "vrais_positifs": vrais_positifs,
                "faux_positifs": d.height - vrais_positifs,
                "faux_negatifs": i.height - vrais_positifs,
                "rappel": vrais_positifs / i.height if i.height else None,
                "precision": vrais_positifs / d.height if d.height else None,
            }
        )
    return pl.DataFrame(lignes)


def main() -> None:
    con = connexion_bronze()
    anomalies = executer_controles(con)
    verite_terrain = pl.read_parquet(CHEMIN_VERITE_TERRAIN)
    print(evaluer(anomalies, verite_terrain))


if __name__ == "__main__":
    main()
