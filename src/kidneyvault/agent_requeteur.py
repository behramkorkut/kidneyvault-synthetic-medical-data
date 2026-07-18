"""Agent requêteur : traduit une question en langage naturel en SQL (lecture
seule) sur la couche Gold, via l'API Claude.

Garde-fous (défense en profondeur) :
1. connexion DuckDB en lecture seule (aucune écriture possible) ;
2. accès externe coupé au niveau moteur : SET enable_external_access = false
   (bloque read_csv/read_parquet/ATTACH… donc toute lecture du système de
   fichiers), verrouillé par SET lock_configuration = true ;
3. validation du SQL généré (un seul SELECT, mots-clés et fonctions de lecture
   externe interdits, tables restreintes à la couche Gold) ;
4. LIMIT forcé à l'exécution (MAX_LIGNES) : borne le coût de toute requête ;
5. sortie structurée : le modèle déclare ses hypothèses d'interprétation et les
   parties de la question qu'il n'a PAS pu satisfaire (anti-dérapage sémantique) ;
6. transparence : le SQL exécuté est toujours retourné à l'utilisateur.

⚠️ Démonstration sur données 100 % synthétiques. En production santé, le modèle
serait auto-hébergé sur infrastructure HDS (aucune sortie de donnée patient).

Prérequis : variable d'environnement ANTHROPIC_API_KEY, extra « agent » installé.
Usage : uv run python -m kidneyvault.agent_requeteur "ta question"
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import polars as pl

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import Anthropic


# Chemin absolu dérivé du module (ne dépend plus du répertoire d'appel).
_RACINE = Path(__file__).resolve().parents[2]
BASE = str(_RACINE / "data" / "kidneyvault.duckdb")
MODELE = "claude-sonnet-4-6"
MAX_LIGNES = 500  # borne dure sur le nombre de lignes retournées

_INTERDITS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma|"
    r"install|load|export|import|truncate|replace|grant|revoke|"
    # Fonctions de lecture externe : déjà neutralisées par
    # enable_external_access=false, re-bloquées ici (défense en profondeur).
    r"read_\w+|\w*_scan|glob|sniff_csv|getenv)\b",
    re.IGNORECASE,
)

# Tables et CTE : seules les tables Gold sont interrogeables.
# On capture le CONTENU complet d'une clause FROM/JOIN (jusqu'à la clause
# suivante) pour attraper AUSSI les jointures implicites par virgule
# — « FROM gold_x, silver_y » — que la lecture du seul 1er identifiant ratait.
_CLAUSE_TABLES = re.compile(
    r"\b(?:from|join)\s+(.+?)"
    r"(?=\b(?:where|group|order|having|limit|qualify|window|on|using|"
    r"inner|left|right|full|cross|natural|join|union|except|intersect)\b|\)|$)",
    re.IGNORECASE | re.DOTALL,
)
_IDENT_INITIAL = re.compile(r"^([a-zA-Z_]\w*)")
_NOM_CTE = re.compile(r"\b([a-zA-Z_]\w*)\s+as\s*\(", re.IGNORECASE)


def _tables_referencees(sql: str) -> set[str]:
    """Toutes les tables citées dans les clauses FROM/JOIN, virgules comprises.
    Les sous-requêtes « FROM (SELECT … ) » ne produisent pas de table ici : leur
    propre FROM interne est capturé séparément par finditer."""
    tables: set[str] = set()
    for clause in _CLAUSE_TABLES.finditer(sql):
        for partie in clause.group(1).split(","):
            m = _IDENT_INITIAL.match(partie.strip())
            if m:
                tables.add(m.group(1).lower())
    return tables


@dataclass
class Reponse:
    """Résultat de l'agent : SQL, données, et ce que le modèle déclare."""

    sql: str | None          # None si la question est inanswerable
    resultat: pl.DataFrame | None
    hypotheses: str          # interprétation des termes vagues
    non_couvert: str         # parties non satisfaites par le schéma
    tronque: bool = field(default=False)  # résultat coupé à MAX_LIGNES


def decrire_schema(con: duckdb.DuckDBPyConnection) -> str:
    """Description textuelle des tables Gold (colonnes, types, valeurs
    catégorielles) — le « grounding » qui évite les libellés inventés."""
    colonnes = con.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_name LIKE 'gold%'
        ORDER BY table_name, ordinal_position
        """
    ).fetchall()

    par_table: dict[str, list[tuple[str, str]]] = {}
    for table, col, typ in colonnes:
        par_table.setdefault(table, []).append((col, typ))

    lignes: list[str] = []
    for table, cols in par_table.items():
        lignes.append(f"\nTable {table} :")
        for col, typ in cols:
            descr = f"  - {col} ({typ})"
            if typ.upper() in ("VARCHAR", "TEXT"):
                vals = con.execute(
                    f'SELECT DISTINCT "{col}" FROM {table} '
                    f'WHERE "{col}" IS NOT NULL LIMIT 15'
                ).fetchall()
                if len(vals) <= 12:
                    descr += " — valeurs : " + ", ".join(repr(v[0]) for v in vals)
            lignes.append(descr)
    return "\n".join(lignes)


def _systeme(schema: str) -> str:
    return (
        "Tu es un assistant expert SQL (dialecte DuckDB) pour un entrepôt de "
        "recherche sur le cancer du rein. Tu traduis la question d'un chercheur "
        "en une requête SQL en lecture seule.\n\n"
        "Tu réponds UNIQUEMENT par un objet JSON valide (sans balise markdown), "
        "avec exactement ces clés :\n"
        '- "sql" : la requête (SELECT ou WITH ... SELECT uniquement), ou null '
        "si la question est totalement impossible avec le schéma.\n"
        '- "hypotheses" : comment tu as interprété les termes vagues (ex. '
        '"vieux" -> tri par âge décroissant). Chaîne vide si rien à signaler.\n'
        '- "non_couvert" : les parties de la question qui ne correspondent à '
        "AUCUNE colonne du schéma et que tu n'as donc PAS traduites (ex. une "
        "localisation de récidive si cette colonne n'existe pas). Chaîne vide "
        "si tout est couvert.\n\n"
        "Règles strictes :\n"
        "- Utilise UNIQUEMENT les tables et colonnes du schéma.\n"
        "- Une seule instruction. Jamais d'INSERT/UPDATE/DELETE ni de DDL.\n"
        "- Respecte EXACTEMENT les valeurs catégorielles (accents inclus).\n"
        "- Ne devine JAMAIS une colonne absente : déclare-la dans non_couvert.\n\n"
        f"Schéma disponible :\n{schema}"
    )


def _extraire_json(reponse: str) -> dict:
    texte = reponse.strip()
    texte = re.sub(r"^```(?:json)?\s*", "", texte)
    texte = re.sub(r"\s*```$", "", texte)
    return json.loads(texte)


def valider_sql(sql: str) -> str:
    """Garde-fou : autorise une unique requête de lecture sur la couche Gold,
    sinon ValueError."""
    nettoye = sql.strip().rstrip(";").strip()
    if ";" in nettoye:
        raise ValueError("Plusieurs instructions SQL détectées (interdit).")
    if not re.match(r"^(select|with)\b", nettoye, re.IGNORECASE):
        raise ValueError("La requête doit être un SELECT en lecture seule.")
    if _INTERDITS.search(nettoye):
        raise ValueError("Mot-clé interdit détecté (mutation ou commande).")
    # Allowlist : toute référence FROM/JOIN (virgules comprises) doit être une
    # table Gold ou une CTE de la requête elle-même.
    ctes = {m.group(1).lower() for m in _NOM_CTE.finditer(nettoye)}
    for table in _tables_referencees(nettoye):
        if table not in ctes and not table.startswith("gold"):
            raise ValueError(
                f"Table non autorisée : « {table} » (couche Gold uniquement)."
            )
    return nettoye


# LIMIT final (éventuellement suivi d'un OFFSET) : sert à ne pas doubler la
# clause quand le modèle a déjà borné sa requête.
_LIMIT_FINAL = re.compile(r"\blimit\s+(\d+)(?:\s+offset\s+\d+)?\s*$", re.IGNORECASE)


def _borner(sql: str) -> str:
    """Applique la borne dure MAX_LIGNES + 1 SANS encapsuler dans une
    sous-requête : l'encapsulation faisait perdre le ORDER BY (DuckDB
    n'ordonne pas une sous-requête sans LIMIT interne). On ajoute donc un
    LIMIT en fin de requête, ou on plafonne celui que le modèle a déjà posé."""
    s = sql.strip().rstrip(";").strip()
    m = _LIMIT_FINAL.search(s)
    if m:
        if int(m.group(1)) <= MAX_LIGNES + 1:
            return s  # déjà borné sous le plafond : on respecte le ORDER BY/LIMIT
        return s[: m.start()].rstrip() + f"\nlimit {MAX_LIGNES + 1}"
    return f"{s}\nlimit {MAX_LIGNES + 1}"


def generer(
    question: str, schema: str, client: Anthropic, erreur: str | None = None
) -> dict:
    """Appelle Claude, retourne le dict {sql, hypotheses, non_couvert}."""
    contenu = question
    if erreur:
        contenu = (
            f"{question}\n\nLa requête précédente a échoué :\n{erreur}\n"
            "Corrige la requête (même format JSON)."
        )
    reponse = client.messages.create(
        model=MODELE,
        max_tokens=1000,
        temperature=0,
        system=_systeme(schema),
        messages=[{"role": "user", "content": contenu}],
    )
    return _extraire_json(reponse.content[0].text)


def repondre(question: str, max_essais: int = 3) -> Reponse:
    """Question -> Reponse. Boucle agentique : toute erreur rattrapable (JSON
    invalide, SQL refusé par le garde-fou, erreur d'exécution) est renvoyée au
    modèle pour qu'il se corrige, jusqu'à max_essais."""
    from anthropic import Anthropic  # extra optionnel : importé à l'usage

    client = Anthropic()
    con = duckdb.connect(BASE, read_only=True)  # rempart 1 : aucune écriture
    try:
        # Rempart 2 : le moteur ne peut plus toucher au système de fichiers
        # ni au réseau (read_csv, read_parquet, ATTACH…), et ce réglage est
        # verrouillé pour toute la durée de la connexion.
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")

        schema = decrire_schema(con)

        erreur: str | None = None
        for essai in range(1, max_essais + 1):
            dernier = essai == max_essais

            try:
                brut = generer(question, schema, client, erreur)
            except (json.JSONDecodeError, KeyError, IndexError) as exc:
                # Réponse illisible (JSON tronqué, clé absente…) : on redonne
                # sa chance au modèle au lieu de planter.
                if dernier:
                    raise ValueError(
                        f"Réponse du modèle illisible après {max_essais} "
                        f"essais : {exc}"
                    ) from exc
                erreur = (
                    f"Ta réponse précédente n'était pas le JSON attendu "
                    f"({exc}). Réponds UNIQUEMENT avec l'objet JSON demandé."
                )
                continue

            hypotheses = brut.get("hypotheses", "") or ""
            non_couvert = brut.get("non_couvert", "") or ""

            if not brut.get("sql"):  # question jugée inanswerable
                return Reponse(None, None, hypotheses, non_couvert)

            try:
                sql = valider_sql(brut["sql"])  # dans le try : refus => retry
                resultat = con.execute(_borner(sql)).pl()
            except (ValueError, duckdb.Error) as exc:
                if dernier:
                    raise
                erreur = str(exc)
                continue

            tronque = resultat.height > MAX_LIGNES
            if tronque:
                resultat = resultat.head(MAX_LIGNES)
            return Reponse(sql, resultat, hypotheses, non_couvert, tronque)

        raise RuntimeError("Échec inattendu de la boucle agentique.")
    finally:
        con.close()  # la connexion est toujours rendue, même sur erreur


def main() -> None:
    question = " ".join(sys.argv[1:]) or "Combien de patients métastatiques ?"
    rep = repondre(question)
    print(f"Question : {question}\n")
    if rep.hypotheses:
        print(f"⚙  Hypothèses : {rep.hypotheses}")
    if rep.non_couvert:
        print(f"⚠  Non couvert par les données : {rep.non_couvert}")
    if rep.sql is None:
        print("\nAucune requête : la question n'est pas satisfaisable.")
        return
    print(f"\nSQL généré :\n{rep.sql}\n")
    print(rep.resultat)
    if rep.tronque:
        print(f"⚠  Résultat tronqué aux {MAX_LIGNES} premières lignes.")


if __name__ == "__main__":
    main()