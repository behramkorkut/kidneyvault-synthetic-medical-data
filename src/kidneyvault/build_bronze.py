"""Point d'entrée : génère l'EDS synthétique, y injecte des défauts réalistes
et le persiste en couche Bronze.

Usage :
    uv run python -m kidneyvault.build_bronze            # Bronze réaliste (défauts)
    uv run python -m kidneyvault.build_bronze --propre   # Bronze parfaite (debug)
"""

import argparse
from pathlib import Path

from kidneyvault.corrupteur import corrompre_eds
from kidneyvault.generator import generer_eds
from kidneyvault.persist import ecrire_bronze


def main() -> None:
    parser = argparse.ArgumentParser(description="Construit la couche Bronze.")
    parser.add_argument(
        "--propre",
        action="store_true",
        help="désactive l'injection de défauts (données parfaites, pour debug)",
    )
    args = parser.parse_args()

    print("Génération de l'EDS synthétique KidneyVault...")
    tables = generer_eds(n_patients=50, n_centres=8)

    if not args.propre:
        tables, verite_terrain = corrompre_eds(tables)
        dossier_vt = Path("data/00_raw")
        dossier_vt.mkdir(parents=True, exist_ok=True)
        chemin_vt = dossier_vt / "verite_terrain_defauts.parquet"
        verite_terrain.write_parquet(chemin_vt)
        print(f"⚠ {verite_terrain.height} défauts injectés → {chemin_vt}")

    print(f"\n{len(tables)} tables. Écriture en couche Bronze :\n")
    ecrire_bronze(tables)
    print("\nTerminé.")


if __name__ == "__main__":
    main()