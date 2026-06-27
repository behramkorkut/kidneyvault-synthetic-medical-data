"""Couche qualité : exécution des contrôles SQL sur la couche Bronze.

Chaque contrôle est un fichier sql/qualite/*.sql qui retourne les lignes en
anomalie au format standard (table_cible, defaut, id_ligne, detail), aligné
sur la vérité terrain du corrupteur — ce qui permet d'évaluer la couche
qualité objectivement (rappel/précision).

DuckDB requête les Parquet Bronze via des vues, sans copie (pattern lakehouse).
"""

from pathlib import Path

import duckdb
import polars as pl

DOSSIER_BRONZE = Path("data/01_bronze")
DOSSIER_CONTROLES = Path("sql/qualite")
DOSSIER_INDICATEURS = Path("sql/indicateurs")

# Format de sortie standard d'un contrôle
_COLONNES_ANOMALIES = {
    "table_cible": pl.String,
    "defaut": pl.String,
    "id_ligne": pl.Int64,
    "detail": pl.String,
}


def connexion_bronze(
    dossier: str | Path = DOSSIER_BRONZE,
) -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB en mémoire, une vue par table Bronze."""
    con = duckdb.connect()
    for parquet in sorted(Path(dossier).glob("*.parquet")):
        con.execute(
            f"CREATE VIEW {parquet.stem} AS "
            f"SELECT * FROM read_parquet('{parquet.as_posix()}')"
        )
    return con


def executer_controles(
    con: duckdb.DuckDBPyConnection,
    dossier: str | Path = DOSSIER_CONTROLES,
) -> pl.DataFrame:
    """Exécute tous les contrôles SQL, concatène les anomalies détectées."""
    anomalies = [pl.DataFrame(schema=_COLONNES_ANOMALIES)]  # base typée si 0 anomalie
    for fichier in sorted(Path(dossier).glob("*.sql")):
        resultat = con.execute(fichier.read_text()).pl()
        anomalies.append(resultat.cast(_COLONNES_ANOMALIES))
    return pl.concat(anomalies)

def executer_indicateurs(
    con: duckdb.DuckDBPyConnection,
    dossier: str | Path = DOSSIER_INDICATEURS,
) -> dict[str, pl.DataFrame]:
    """Exécute les indicateurs qualité (schéma libre, contrairement aux contrôles)."""
    return {
        fichier.stem: con.execute(fichier.read_text()).pl()
        for fichier in sorted(Path(dossier).glob("*.sql"))
    }


def main() -> None:
    con = connexion_bronze()
    anomalies = executer_controles(con)
    if anomalies.is_empty():
        print("Aucune anomalie détectée.")
    else:
        print(f"{anomalies.height} anomalie(s) détectée(s) :\n")
        print(anomalies.group_by("defaut").len().sort("defaut"))
        print()
        print(anomalies)

    for nom, resultat in executer_indicateurs(con).items():
        print(f"\nIndicateur : {nom}")
        print(resultat)




if __name__ == "__main__":
    main()