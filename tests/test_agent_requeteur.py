"""Tests du garde-fou de l'agent requêteur.

On NE teste PAS l'appel au LLM (non-déterministe, payant, hors CI). On teste
la couche de validation déterministe qui entoure le modèle : c'est elle qui
garantit qu'aucune requête dangereuse ne sera exécutée, quel que soit ce que
le LLM produit.
"""

import duckdb
import pytest

from kidneyvault.agent_requeteur import MAX_LIGNES, _borner, _extraire_json, valider_sql


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


# ---------- Lecture du système de fichiers (audit M7) ----------

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_text('/etc/hostname')",
        "SELECT * FROM parquet_scan('data/kidneyvault.duckdb')",
        "SELECT * FROM glob('/**')",
    ],
)
def test_lecture_fichier_rejetee(sql):
    """read_csv & co : la validation refuse toute fonction de lecture externe."""
    with pytest.raises(ValueError):
        valider_sql(sql)


def test_acces_externe_coupe_au_niveau_moteur():
    """Même si la validation était contournée, le moteur refuse : c'est le
    rempart dur (enable_external_access = false, verrouillé)."""
    con = duckdb.connect(":memory:")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    with pytest.raises(duckdb.Error):
        con.execute("SELECT * FROM read_csv('/etc/passwd')")
    with pytest.raises(duckdb.Error):  # et le réglage ne peut pas être réactivé
        con.execute("SET enable_external_access = true")
    con.close()


# ---------- Allowlist de tables (couche Gold uniquement) ----------

def test_table_hors_gold_rejetee():
    with pytest.raises(ValueError):
        valider_sql("SELECT * FROM silver_patient")


def test_table_hors_gold_dans_cte_rejetee():
    """La table interdite cachée dans une CTE est vue aussi."""
    with pytest.raises(ValueError):
        valider_sql("WITH t AS (SELECT * FROM stg_patient) SELECT * FROM t")


def test_jointure_implicite_virgule_rejetee():
    """Régression R1 : une table interdite jointe par virgule doit être vue."""
    with pytest.raises(ValueError):
        valider_sql("SELECT * FROM gold_cohorte_patient, silver_patient")


def test_jointure_implicite_gold_seules_acceptee():
    """Deux tables Gold jointes par virgule restent licites."""
    sql = "SELECT * FROM gold_cohorte_patient, gold_kpi_histologie"
    assert valider_sql(sql) == sql


# ---------- LIMIT forcé (sans casser le ORDER BY — régression R2) ----------

def test_borner_ajoute_limit_sans_encapsuler():
    """R2 : on n'encapsule plus dans une sous-requête (qui perdait l'ordre) ;
    on ajoute un LIMIT en fin de requête."""
    borne = _borner("SELECT * FROM gold_cohorte_patient ORDER BY age DESC")
    assert f"limit {MAX_LIGNES + 1}" in borne.lower()
    assert "order by age desc" in borne.lower()
    assert not borne.lower().startswith("select * from (")
    # le ORDER BY précède le LIMIT ajouté
    assert borne.lower().index("order by") < borne.lower().index("limit")


def test_borner_respecte_limit_du_modele_sous_plafond():
    """Un LIMIT déjà posé sous le plafond est conservé tel quel."""
    assert _borner("SELECT * FROM gold_cohorte_patient LIMIT 5").endswith("LIMIT 5")


def test_borner_plafonne_limit_excessif():
    """Un LIMIT au-dessus du plafond est ramené à MAX_LIGNES + 1."""
    borne = _borner(f"SELECT * FROM gold_cohorte_patient LIMIT {MAX_LIGNES + 9000}")
    assert borne.lower().count("limit") == 1
    assert f"limit {MAX_LIGNES + 1}" in borne.lower()


def test_borner_preserve_ordre_a_l_execution():
    """Preuve d'exécution : l'ordre demandé survit au bornage."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE gold_t AS SELECT * FROM (VALUES (13), (24)) t(age)")
    direct = con.execute("SELECT age FROM gold_t ORDER BY age DESC").fetchall()
    borne = con.execute(_borner("SELECT age FROM gold_t ORDER BY age DESC")).fetchall()
    con.close()
    assert direct == borne == [(24,), (13,)]


# ---------- Extraction JSON ----------

def test_extraire_json_retire_balises_markdown():
    brut = '```json\n{"sql": "SELECT 1", "hypotheses": "", "non_couvert": ""}\n```'
    assert _extraire_json(brut)["sql"] == "SELECT 1"