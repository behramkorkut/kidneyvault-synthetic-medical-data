"""Page Streamlit — Requêteur IA (text-to-SQL sur la couche Gold).

Interroge la cohorte en langage naturel via l'agent (API Claude). Garde-fous :
lecture seule, SQL validé ET affiché, hypothèses et limites déclarées.

⚠️ Démonstration sur données 100 % synthétiques. En production santé, le modèle
serait auto-hébergé sur infrastructure HDS (aucune sortie de donnée patient).
"""

import os
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]

st.set_page_config(
    page_title="KidneyVault — Requêteur IA", page_icon="🤖", layout="wide"
)

st.title("🤖 Requêteur IA — interrogation en langage naturel")
st.caption(
    "Pose une question en français ; l'agent la traduit en SQL (lecture seule) "
    "sur la couche Gold, affiche la requête, et déclare ce qu'il ne peut pas "
    "satisfaire. Données 100 % synthétiques."
)

# Sur Streamlit Cloud, la clé vit dans les secrets : on la mappe vers l'env
# (le SDK anthropic lit ANTHROPIC_API_KEY dans os.environ).
try:
    if not os.environ.get("ANTHROPIC_API_KEY") and st.secrets.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass


@st.cache_resource
def _bootstrap() -> bool:
    """Construit le warehouse au premier démarrage (utile en déploiement)."""
    from kidneyvault.bootstrap import ensure_warehouse

    ensure_warehouse(REPO_ROOT)
    return True


with st.spinner("Préparation de l'entrepôt (jusqu'à ~30 s au 1er lancement)…"):
    _bootstrap()

# L'agent a besoin de la clé API (extra « agent »). On échoue proprement sinon.
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.warning(
        "Variable ANTHROPIC_API_KEY absente. Lance Streamlit dans un terminal "
        "où la clé est exportée :  export ANTHROPIC_API_KEY=sk-ant-..."
    )
    st.stop()

EXEMPLES = [
    "Combien de patients décédés ont été opérés au robot, par type de centre ?",
    "Les patients âgés avec une récidive au poumon",
    "Répartition des types histologiques chez les patients opérés",
]

st.write("**Exemples :**")
for col, ex in zip(st.columns(len(EXEMPLES)), EXEMPLES):
    if col.button(ex, use_container_width=True):
        st.session_state["question"] = ex

from kidneyvault.agent_requeteur import MAX_QUESTION  # noqa: E402

question = st.text_input(
    "Votre question", value=st.session_state.get("question", ""), max_chars=MAX_QUESTION
)

if st.button("Interroger", type="primary") and question:
    import time

    from kidneyvault.agent_requeteur import repondre
    from kidneyvault.quota_serveur import consommer
    from kidneyvault.rate_limit import etat_quota

    # Borne de question : max_chars borne déjà la saisie, on revalide ici
    # (session_state peut être pré-rempli) avec un message clair.
    if len(question.strip()) > MAX_QUESTION:
        st.warning(
            f"Question trop longue ({len(question.strip())} caractères) : "
            f"maximum {MAX_QUESTION}. Reformulez plus court."
        )
        st.stop()

    # Garde de session (anti-marteau) : intervalle minimal entre deux appels
    # et plafond par session, via l'historique de timestamps en session.
    appels = st.session_state.setdefault("appels_ia", [])
    autorise, message = etat_quota(appels, time.time())
    if not autorise:
        st.warning(message)
        st.stop()

    # Garde serveur (persistante) : budget quotidien par adresse IP, stocké
    # dans Postgres ou un fichier local — survit aux rechargements de page.
    ip = getattr(st.context, "ip_address", None) or "ip-inconnue"
    autorise, message = consommer(ip)
    if not autorise:
        st.warning(message)
        st.stop()
    appels.append(time.time())

    with st.spinner("L'agent réfléchit..."):
        try:
            rep = repondre(question)
        except Exception as exc:  # garde-fou, erreur API, SQL erroné…
            st.error(f"Échec : {exc}")
            st.stop()

    if rep.hypotheses:
        st.info(f"⚙ Hypothèses d'interprétation : {rep.hypotheses}")
    if rep.non_couvert:
        st.warning(f"⚠ Non couvert par les données : {rep.non_couvert}")

    if rep.sql is None:
        st.error("Aucune requête : question non satisfaisable avec le schéma.")
        st.stop()

    st.write("**SQL généré (lecture seule, validé) :**")
    st.code(rep.sql, language="sql")

    if rep.tronque:
        st.caption("⚠ Résultat tronqué (borne de sécurité sur le nombre de lignes).")
    st.write(f"**Résultat — {rep.resultat.height} ligne(s) :**")
    st.dataframe(rep.resultat, use_container_width=True, hide_index=True)
    st.download_button(
        "⬇ Exporter (CSV)",
        data=rep.resultat.write_csv(),
        file_name="resultat_requete.csv",
        mime="text/csv",
    )
