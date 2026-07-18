"""Tests de la garde de coût (audit M10) : logique de quota pure."""

from kidneyvault.rate_limit import (
    INTERVALLE_MIN_S,
    MAX_APPELS_SESSION,
    etat_quota,
)


def test_premier_appel_autorise():
    autorise, message = etat_quota([], maintenant=1000.0)
    assert autorise is True
    assert message == ""


def test_intervalle_trop_court_refuse():
    """Deux appels rapprochés : le second est refusé."""
    autorise, message = etat_quota([1000.0], maintenant=1002.0)
    assert autorise is False
    assert "patienter" in message.lower()


def test_intervalle_respecte_autorise():
    autorise, _ = etat_quota([1000.0], maintenant=1000.0 + INTERVALLE_MIN_S)
    assert autorise is True


def test_plafond_session_atteint_refuse():
    """Au-delà du plafond, plus aucun appel, même espacé dans le temps."""
    appels = [1000.0 + i * 100 for i in range(MAX_APPELS_SESSION)]
    autorise, message = etat_quota(appels, maintenant=1_000_000.0)
    assert autorise is False
    assert "quota" in message.lower()


def test_plafond_prime_sur_intervalle():
    """Le plafond est vérifié même si l'intervalle serait respecté."""
    appels = [float(i) for i in range(MAX_APPELS_SESSION)]
    autorise, _ = etat_quota(appels, maintenant=1_000_000.0)
    assert autorise is False
