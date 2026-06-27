"""Persistance des couches de données (écriture sur disque)."""

from pathlib import Path

import polars as pl


def ecrire_bronze(
    tables: dict[str, pl.DataFrame],
    dossier: str | Path = "data/01_bronze",
) -> None:
    """Écrit chaque table de l'EDS en Parquet dans la couche Bronze.

    Parquet : format colonnaire compressé, standard de l'analytique moderne.
    Un fichier par table, nommé d'après la table.
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)

    for nom_table, df in tables.items():
        chemin = dossier / f"{nom_table}.parquet"
        df.write_parquet(chemin)
        print(f"✓ {nom_table:28s} → {chemin}  ({df.height} lignes)")
