"""Garde de coût pour la démo publique du Requêteur IA (audit M10).

Chaque requête déclenche un appel à l'API Claude, donc un coût. Sur une démo
accessible publiquement, rien n'empêchait un visiteur d'enchaîner les appels.
Ce module fournit une logique de quota PURE (sans dépendance à Streamlit) donc
testable : la page ne fait que brancher l'historique de session dessus.

Deux bornes : un plafond d'appels par session et un intervalle minimal entre
deux appels (anti-marteau). Volontairement en mémoire de session — suffisant
pour une démo ; une vraie prod utiliserait un quota côté serveur (Redis, etc.).
"""

from __future__ import annotations

MAX_APPELS_SESSION = 15   # plafond d'appels API par session
INTERVALLE_MIN_S = 5.0    # délai minimal entre deux appels


def etat_quota(
    appels: list[float],
    maintenant: float,
    *,
    max_session: int = MAX_APPELS_SESSION,
    intervalle_s: float = INTERVALLE_MIN_S,
) -> tuple[bool, str]:
    """Décide si un nouvel appel est autorisé.

    `appels` : timestamps (secondes epoch) des appels déjà effectués dans la
    session, dans l'ordre chronologique. `maintenant` : timestamp courant.
    Retourne (autorisé, message) — message non vide seulement si refusé.
    """
    if len(appels) >= max_session:
        return False, (
            f"Quota de démonstration atteint ({max_session} requêtes par "
            "session). Rechargez la page pour repartir de zéro."
        )
    if appels:
        ecoule = maintenant - appels[-1]
        if ecoule < intervalle_s:
            reste = intervalle_s - ecoule
            return False, f"Merci de patienter {reste:.0f} s entre deux requêtes."
    return True, ""
