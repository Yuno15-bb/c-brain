#!/usr/bin/env python3
"""
propagation_provenance.py — la règle de propagation du distillateur (ADR-0009, I7).

CE QU'ELLE FAIT, ET RIEN D'AUTRE. Quand une connaissance est distillée, synthétisée ou
réécrite, la fiche produite hérite de la provenance de sa source. La règle est
volontairement BÊTE :

    entrée : web / basis        →  sortie : web / basis
    entrée : agent_inference    →  sortie : agent_inference

Reformuler n'est pas observer. Le distillateur n'est PAS le résolveur d'autorité : il
transporte, il ne juge pas. Toute intelligence ajoutée ici serait une porte de promotion.

LES TROIS RÈGLES :
  1. le `kind` effectif ne monte JAMAIS — il est repris tel quel ;
  2. `validated` retombe TOUJOURS à false — une preuve ne se reconduit pas par copie,
     c'est à l'écrivain de la rétablir sur la fiche nouvelle ;
  3. la chaîne `derived_from` n'est jamais coupée — c'est elle qui permet de remonter à
     l'origine après trois transformations, et c'est le vrai test de I7.

POURQUOI LA CHAÎNE PLUTÔT QU'UN CHAMP « racine_externe » RECOPIÉ. Recopier la racine à
chaque saut crée une seconde source de vérité, qui dérive dès qu'un maillon est corrigé.
On marche la chaîne. C'est plus lent et ça ne ment pas.

Lancer :
  python3 tests/propagation_provenance.py
  python3 tests/propagation_provenance.py --check
  python3 tests/propagation_provenance.py --sans-propagation   # SABOTAGE
"""
import argparse
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(ICI, "fixtures_propagation.json")
sys.path.insert(0, ICI)
from provenance_invariants import KINDS, kind_effectif  # noqa: E402



def propager(source, transformation, propager_vraiment=True):
    """La provenance de la fiche produite à partir de `source`.

    `propager_vraiment=False` est le SABOTAGE : la transformation repart d'une provenance
    neuve, comme le ferait un distillateur qui « range » sans conserver. C'est exactement
    le blanchiment que I7 interdit, et le banc doit le voir.
    """
    if not propager_vraiment:
        return {"id": f"{source['id']}+{transformation}", "kind": "internal_experience",
                "ref": "réécrit et rangé dans le tronc", "validated": False}
    sortie = {
        "id": f"{source['id']}+{transformation}",
        "kind": kind_effectif(source),
        "validated": False,               # règle 2 : jamais de reconduction de preuve
        "derived_from": source["id"],     # règle 3 : la chaîne n'est pas coupée
        "transformation": transformation,
    }
    if source.get("sources"):
        # Toutes les sources survivent, avec leur rôle. L'illustration web ne disparaît
        # pas — et ne contamine pas la base, puisque le kind se lit sur les `basis`.
        sortie["sources"] = [dict(s) for s in source["sources"]]
    if source.get("ref"):
        sortie["ref"] = source["ref"]
    return sortie


def remonter_origine(maillon, par_id):
    """Marche `derived_from` jusqu'à la racine et rend sa référence."""
    vu = set()
    while maillon.get("derived_from") and maillon["derived_from"] not in vu:
        vu.add(maillon["derived_from"])
        maillon = par_id[maillon["derived_from"]]
    if maillon.get("ref"):
        return maillon["ref"]
    for s in maillon.get("sources") or ():          # fiche mixte : la base fait référence
        if s.get("role") == "basis":
            return s.get("ref")
    return None


def jouer(chaine, propager_vraiment=True):
    racine = chaine["racine"]
    par_id = {racine["id"]: racine}
    courant = racine
    for t in chaine["etapes"]:
        courant = propager(courant, t, propager_vraiment)
        par_id[courant["id"]] = courant
    profondeur = 0
    m = courant
    while m.get("derived_from"):
        profondeur += 1
        m = par_id[m["derived_from"]]
    return courant, remonter_origine(courant, par_id), profondeur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sans-propagation", action="store_true",
                    help="SABOTAGE : la transformation ne conserve rien")
    a = ap.parse_args()
    vrai = not a.sans_propagation

    chaines = json.load(open(FIXTURES, encoding="utf-8"))["chaines"]
    titre = "" if vrai else "   ⚠️ SABOTAGE : propagation coupée"
    print(f"Propagation de provenance — {len(chaines)} chaînes{titre}\n")

    echecs = 0
    for ch in chaines:
        final, origine, prof = jouer(ch, vrai)
        att = ch["attendu"]
        fautes = []
        if final["kind"] != att["kind_final"]:
            fautes.append(f"kind {final['kind']} ≠ {att['kind_final']}")
        if final["validated"] is not att["validated_final"]:
            fautes.append(f"validated {final['validated']}")
        if "origine_externe" in att and origine != att["origine_externe"]:
            fautes.append(f"origine perdue : {origine!r}")
        if prof != att["profondeur"]:
            fautes.append(f"profondeur {prof} ≠ {att['profondeur']}")
        if att.get("sources_conservees") is not None:
            n = len(final.get("sources") or [])
            if n != att["sources_conservees"]:
                fautes.append(f"{n} source(s) conservée(s) sur {att['sources_conservees']}")
        if att.get("web_toujours_present"):
            if not any(s["kind"] == "web" for s in final.get("sources") or []):
                fautes.append("l'illustration web a disparu de la provenance")
        if final["kind"] not in KINDS:
            fautes.append(f"kind hors vocabulaire : {final['kind']}")

        echecs += bool(fautes)
        print(f"  {'✅' if not fautes else '❌'} {ch['id']:52} "
              f"{' → '.join(ch['etapes'])}")
        if fautes:
            for f in fautes:
                print(f"        ↳ {f}")

    print(f"\n  {len(chaines) - echecs}/{len(chaines)} chaînes conformes")
    if a.check and echecs:
        print("\n❌ la propagation ne conserve pas ce qu'elle doit conserver")
        return 1
    if a.check:
        print("\n✅ I7 tenu à travers les transformations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
