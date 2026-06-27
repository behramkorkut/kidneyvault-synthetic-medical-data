"""Tests du garde-fou de l'agent requêteur.

On NE teste PAS l'appel au LLM (non-déterministe, payant, hors CI). On teste
la couche de validation déterministe qui entoure le modèle : c'est elle qui
garantit qu'aucune requête dangereuse ne sera exécutée, quel que soit ce que
le LLM produit.
"""

import pytest

from kidneyvault.agent_requeteur import _extraire_json, valider_sql


# ---------- Requêtes licites ----------

def test_select_simple_valide():
    sql = "SELECT * FROM gold_cohorte_patient"
    assert valider_sql(sql) == sql


def test_with_valide():
    sql = "WITH t AS (SELECT 1 AS x) SELECT x FROM t"
    assert valider_sql(sql) == sql


def test_point_virgule_final_toleré():
    """Un ; final unique est nettoyé, pas rejeté."""
    assert valider_sql("SELECT 1;") == "SELECT 1"


# ---------- Requêtes rejetées (le cœur du garde-fou) ----------

@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE gold_cohorte_patient",
        "DELETE FROM gold_cohorte_patient",
        "UPDATE gold_cohorte_patient SET sexe = 'H'",
        "INSERT INTO gold_cohorte_patient VALUES (1)",
        "ATTACH 'x.db' AS y",
    ],
)
def test_mutation_rejetee(sql):
    """Toute requête qui ne commence pas par SELECT/WITH est refusée."""
    with pytest.raises(ValueError):
        valider_sql(sql)


def test_multi_instructions_rejete():
    """Deux instructions (injection classique) : refusé."""
    with pytest.raises(ValueError):
        valider_sql("SELECT 1; DROP TABLE gold_cohorte_patient")


def test_mot_cle_interdit_dans_cte_rejete():
    """Un SELECT bien formé mais contenant une commande dangereuse : refusé."""
    with pytest.raises(ValueError):
        valider_sql("WITH t AS (SELECT 1) DELETE FROM gold_cohorte_patient")


# ---------- Extraction JSON ----------

def test_extraire_json_retire_balises_markdown():
    brut = '```json\n{"sql": "SELECT 1", "hypotheses": "", "non_couvert": ""}\n```'
    assert _extraire_json(brut)["sql"] == "SELECT 1"