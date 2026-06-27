"""Interface de screening de cohortes — couche Gold de KidneyVault.

L'app NE FAIT AUCUNE transformation métier : elle filtre la table d'analyse
gold_cohorte_patient, déjà nettoyée et dédoublonnée par le pipeline dbt.
Toute la logique vit en amont (générateur, qualité, dbt) — l'interface n'est
qu'une vitrine d'exploration et d'export.

Lancement : uv run streamlit run app/screening.py
"""

from pathlib import Path

import duckdb
import polars as pl
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = REPO_ROOT / "data" / "kidneyvault.duckdb"

st.set_page_config(page_title="KidneyVault — Screening", page_icon="🔬", layout="wide")


@st.cache_data
def charger_cohorte() -> pl.DataFrame:
    """Charge la cohorte Gold (lecture seule, mise en cache par Streamlit)."""
    con = duckdb.connect(str(BASE), read_only=True)
    df = con.execute("select * from gold_cohorte_patient").pl()
    con.close()
    return df


st.title("🔬 KidneyVault — Screening de cohortes")
st.caption(
    "Sélection de patients sur la couche Gold (données 100 % synthétiques). "
    "Cas d'usage : études de faisabilité, jeux de données de projets ancillaires."
)

@st.cache_resource
def _bootstrap() -> bool:
    """Construit le warehouse au premier démarrage (utile en déploiement)."""
    from kidneyvault.bootstrap import ensure_warehouse

    ensure_warehouse(REPO_ROOT)
    return True


with st.spinner("Préparation de l'entrepôt (jusqu'à ~30 s au 1er lancement)…"):
    _bootstrap()

cohorte = charger_cohorte()

# --- Filtres (barre latérale) ---
st.sidebar.header("Critères d'inclusion")

sexes = st.sidebar.multiselect(
    "Sexe", options=sorted(cohorte["sexe"].unique().to_list())
)
types_centre = st.sidebar.multiselect(
    "Type de centre", options=sorted(cohorte["type_centre"].unique().to_list())
)
histologies = st.sidebar.multiselect(
    "Type histologique",
    options=sorted(cohorte["type_histologique"].drop_nulls().unique().to_list()),
)

age_min, age_max = int(cohorte["age_inclusion"].min()), int(
    cohorte["age_inclusion"].max()
)
age = st.sidebar.slider("Âge à l'inclusion", age_min, age_max, (age_min, age_max))

opere = st.sidebar.selectbox("Opéré ?", ["Indifférent", "Oui", "Non"])
recidive = st.sidebar.selectbox("Récidive ?", ["Indifférent", "Oui", "Non"])

# --- Application des filtres ---
filtre = cohorte.filter(
    pl.col("age_inclusion").is_between(age[0], age[1])
)
if sexes:
    filtre = filtre.filter(pl.col("sexe").is_in(sexes))
if types_centre:
    filtre = filtre.filter(pl.col("type_centre").is_in(types_centre))
if histologies:
    filtre = filtre.filter(pl.col("type_histologique").is_in(histologies))
if opere != "Indifférent":
    filtre = filtre.filter(pl.col("a_ete_opere") == (opere == "Oui"))
if recidive != "Indifférent":
    filtre = filtre.filter(pl.col("a_recidive") == (recidive == "Oui"))

# --- Indicateurs de la cohorte sélectionnée ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Patients", filtre.height)
c2.metric(
    "Âge médian",
    f"{filtre['age_inclusion'].median():.0f} ans" if filtre.height else "—",
)
c3.metric(
    "Opérés",
    f"{100 * filtre['a_ete_opere'].mean():.0f} %" if filtre.height else "—",
)
c4.metric(
    "Récidives",
    f"{100 * filtre['a_recidive'].mean():.0f} %" if filtre.height else "—",
)

# --- Table + export ---
st.dataframe(filtre, use_container_width=True, hide_index=True)

st.download_button(
    "⬇ Exporter la cohorte (CSV pour R/SAS)",
    data=filtre.write_csv(),
    file_name="cohorte_kidneyvault.csv",
    mime="text/csv",
    disabled=filtre.height == 0,
)