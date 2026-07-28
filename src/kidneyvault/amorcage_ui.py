"""Amorçage de l'entrepôt côté interface : point d'entrée UNIQUE et résilient.

Auparavant, chaque page Streamlit portait sa propre fonction `_bootstrap`
décorée `@st.cache_resource` : deux fonctions distinctes = deux entrées de
cache = deux verrous indépendants, donc deux `dbt run` possibles en parallèle
sur le même fichier DuckDB. Ici, une seule fonction cachée est partagée par
toutes les pages : Streamlit sérialise les appels concurrents sur son verrou.

En cas d'échec, l'utilisateur voit un message clair et un bouton de
reconstruction plutôt qu'une trace brute — et l'entrepôt est purgé avant la
nouvelle tentative (sinon le résidu qui a causé l'échec est toujours là).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from kidneyvault.bootstrap import ensure_warehouse, purger


@st.cache_resource(show_spinner=False)
def _amorcer(racine: str) -> bool:
    """Cache partagé : l'argument est une chaîne (clé de cache stable)."""
    ensure_warehouse(Path(racine))
    return True


def amorcer(racine: Path) -> None:
    """Construit l'entrepôt si nécessaire, ou affiche une porte de sortie.

    À appeler au début de chaque page, avant toute lecture de la couche Gold.
    """
    with st.spinner("Préparation de l'entrepôt (jusqu'à ~1 min au 1er lancement)…"):
        try:
            _amorcer(str(racine))
            return
        except Exception as exc:  # noqa: BLE001 - on veut dégrader proprement
            # Rien n'est mis en cache quand la fonction lève : le prochain
            # passage retentera. On nettoie quand même l'entrée par sécurité.
            _amorcer.clear()
            erreur = exc

    st.error(
        "L'entrepôt n'a pas pu être préparé. Cela arrive après une mise en "
        "veille de la démonstration, quand la base est laissée dans un état "
        "incohérent. Le bouton ci-dessous la reconstruit de zéro (~1 min)."
    )
    with st.expander("Détail technique"):
        st.code(str(erreur))
    if st.button("Reconstruire l'entrepôt", type="primary"):
        purger(Path(racine) / "data" / "kidneyvault.duckdb")
        _amorcer.clear()
        st.cache_data.clear()
        st.rerun()
    st.stop()
