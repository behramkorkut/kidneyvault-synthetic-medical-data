"""Agent requêteur : traduit une question en langage naturel en SQL (lecture
seule) sur la couche Gold, via l'API Claude.

Garde-fous (défense en profondeur) :
1. connexion DuckDB en lecture seule (aucune écriture possible) ;
2. validation du SQL généré (un seul SELECT, mots-clés dangereux interdits) ;
3. sortie structurée : le modèle déclare ses hypothèses d'interprétation et les
   parties de la question qu'il n'a PAS pu satisfaire (anti-dérapage sémantique) ;
4. transparence : le SQL exécuté est toujours retourné à l'utilisateur.

⚠️ Démonstration sur données 100 % synthétiques. En production santé, le modèle
serait auto-hébergé sur infrastructure HDS (aucune sortie de donnée patient).

Prérequis : variable d'environnement ANTHROPIC_API_KEY, extra « agent » installé.
Usage : uv run python -m kidneyvault.agent_requeteur "ta question"
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass

import duckdb
import polars as pl

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import Anthropic



BASE = "data/kidneyvault.duckdb"
MODELE = "claude-sonnet-4-6"

_INTERDITS = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma|"
    r"install|load|export|import|truncate|replace|grant|revoke)\b",
    re.IGNORECASE,
)


@dataclass
class Reponse:
    """Résultat de l'agent : SQL, données, et ce que le modèle déclare."""

    sql: str | None          # None si la question est inanswerable
    resultat: pl.DataFrame | None
    hypotheses: str          # interprétation des termes vagues
    non_couvert: str         # parties non satisfaites par le schéma


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
    """Garde-fou : autorise une unique requête de lecture, sinon ValueError."""
    nettoye = sql.strip().rstrip(";").strip()
    if ";" in nettoye:
        raise ValueError("Plusieurs instructions SQL détectées (interdit).")
    if not re.match(r"^(select|with)\b", nettoye, re.IGNORECASE):
        raise ValueError("La requête doit être un SELECT en lecture seule.")
    if _INTERDITS.search(nettoye):
        raise ValueError("Mot-clé interdit détecté (mutation ou commande).")
    return nettoye


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


def repondre(question: str, max_essais: int = 2) -> Reponse:
    """Question -> Reponse. Boucle agentique : en cas d'erreur d'exécution,
    on renvoie l'erreur au modèle pour qu'il se corrige."""
    from anthropic import Anthropic  # extra optionnel : importé à l'usage 
    
    client = Anthropic()
    con = duckdb.connect(BASE, read_only=True)  # rempart dur : aucune écriture
    schema = decrire_schema(con)

    erreur: str | None = None
    for essai in range(1, max_essais + 1):
        brut = generer(question, schema, client, erreur)
        hypotheses = brut.get("hypotheses", "") or ""
        non_couvert = brut.get("non_couvert", "") or ""

        if not brut.get("sql"):  # question jugée inanswerable
            return Reponse(None, None, hypotheses, non_couvert)

        sql = valider_sql(brut["sql"])
        try:
            resultat = con.execute(sql).pl()
            return Reponse(sql, resultat, hypotheses, non_couvert)
        except duckdb.Error as exc:
            erreur = str(exc)
            if essai == max_essais:
                raise
    raise RuntimeError("Échec inattendu de la boucle agentique.")


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


if __name__ == "__main__":
    main()