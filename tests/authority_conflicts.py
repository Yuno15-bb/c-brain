#!/usr/bin/env python3
"""
authority_conflicts.py — l'étage 2 de l'ADR-0008 : la RÉSOLUTION.

CE QU'IL FAIT. Deux connaissances pertinentes se contredisent : laquelle fait autorité ?
Le résolveur répond par l'une de QUATRE sorties — A_WINS, B_WINS, COMPATIBLE, UNRESOLVED.

POURQUOI UNRESOLVED EST UNE SORTIE DE PLEIN DROIT, et pas un échec. Un résolveur qui
tranche toujours transforme l'incertitude en certitude : sur deux non-savoirs
(`unknown` contre `agent_inference`), élire un gagnant fabrique de l'autorité à partir de
rien. Le droit de répondre « je ne sais pas » est ce qui empêche cette machine de mentir.

CE QU'IL NE FAIT PAS. Détecter QU'IL Y A contradiction : c'est sémantique, et une règle
déterministe ne le fait pas. Le champ `contradiction` est posé par l'auteur du cas. Le
résolveur juge qui l'emporte quand contradiction il y a — c'est ce qui est mesuré ici.

INDÉPENDANT DU GOLDEN SET DE RÉCUPÉRATION, délibérément (ADR-0008) : tests/golden_recall.py
mesure « la bonne fiche remonte-t-elle ? », ce fichier mesure « laquelle fait foi ? ».
Mélanger les deux ferait qu'une amélioration de l'un masquerait une régression de l'autre.

Lancer :
  python3 tests/authority_conflicts.py
  python3 tests/authority_conflicts.py --check         # barrière
  python3 tests/authority_conflicts.py --scope-large   # SABOTAGE : tous les scopes élargis
  python3 tests/authority_conflicts.py --sans-scope    # SABOTAGE : le scope est ignoré
"""
import argparse
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(ICI, "fixtures_conflits.json")

# Seules classes portant de la NORMATIVITÉ (le droit de trancher un choix).
sys.path.insert(0, ICI)
from provenance_invariants import kind_effectif  # noqa: E402
# ⬆️ UNE seule écriture de I7. La copie locale qui vivait ici rendait
# `official_documentation` là où la propagation rendait `web` : la divergence annoncée
# avait déjà eu lieu. cf. [[un-detecteur-partage-par-concept]]

NORMATIFS = {"user_decision", "internal_experience"}

# Autorité FACTUELLE : qui décrit le mieux ce qui EST. `user_decision` en est absent, et
# c'est I6 : l'auteur décide de ses projets, pas de la réalité. `unknown` et `agent_inference`
# valent 0 — pas « peu », zéro : ils ne peuvent jamais l'emporter, même seuls face à rien.
POIDS_FACTUEL = {"internal_experience": 4, "official_documentation": 3,
                 "external_document": 2, "web": 1, "agent_inference": 0, "unknown": 0}
# Autorité NORMATIVE : qui a le droit de dicter une règle de travail.
POIDS_NORMATIF = {"user_decision": 4, "internal_experience": 2,
                  "official_documentation": 0, "external_document": 0,
                  "web": 0, "agent_inference": 0, "unknown": 0}


def s_applique(cote, question, mode_scope="strict"):
    """Ce côté a-t-il seulement le droit de se prononcer sur CETTE question ?

    C'est I6 rendu opérationnel : l'autorité est bornée par son domaine. Une décision prise
    pour le projet A ne dit rien du projet B, et une doc qui décrit le monde ne dit rien
    d'une convention interne.
    """
    if mode_scope == "sans":                     # sabotage : le scope ne compte plus
        return True
    dom_c, dom_q = cote.get("domaine"), question["domaine"]
    if mode_scope == "large":                    # sabotage : tout le monde voit tout
        return True
    if cote.get("scope") == "global":
        return question["nature"] == "normative"
    if dom_c == dom_q:
        return True
    return False


def resoudre(cas, mode_scope="strict"):
    if not cas.get("contradiction", True):
        return "COMPATIBLE"

    q = cas["question"]
    poids = POIDS_NORMATIF if q["nature"] == "normative" else POIDS_FACTUEL
    cotes = {}
    for nom in ("A", "B"):
        c = cas[nom]
        if not s_applique(c, q, mode_scope):
            continue                              # hors de son domaine : il ne concourt pas
        k = kind_effectif(c)
        p = poids.get(k, 0)
        # Une connaissance validée pèse plus — mais seulement si sa classe pèse déjà
        # quelque chose. Valider ne crée pas d'autorité là où il n'y en a aucune (I1).
        if c.get("validated") and p > 0:
            p += 1
        if c.get("superseded"):                   # remplacée : elle ne fait plus foi
            p = 0
        cotes[nom] = p

    if not cotes:
        return "UNRESOLVED"                       # les deux hors scope
    if len(cotes) == 1:
        seul = next(iter(cotes))
        # Seul en lice, mais sans la moindre autorité : on ne le déclare pas vainqueur.
        return f"{seul}_WINS" if cotes[seul] > 0 else "UNRESOLVED"
    if cotes["A"] == cotes["B"]:
        return "UNRESOLVED"                       # rien ne départage : on ne bricole pas
    gagnant = max(cotes, key=cotes.get)
    return f"{gagnant}_WINS" if cotes[gagnant] > 0 else "UNRESOLVED"


def mesurer(cas_tous, mode_scope="strict"):
    res = [(c, resoudre(c, mode_scope)) for c in cas_tous]
    n = len(res)
    justes = sum(1 for c, v in res if v == c["attendu"])

    tranchables = [(c, v) for c, v in res if c["attendu"] in ("A_WINS", "B_WINS")]
    sel = (sum(1 for c, v in tranchables if v == c["attendu"]) / len(tranchables)
           if tranchables else 0.0)

    dits_unres = [(c, v) for c, v in res if v == "UNRESOLVED"]
    unres_prec = (sum(1 for c, _ in dits_unres if c["attendu"] == "UNRESOLVED")
                  / len(dits_unres) if dits_unres else 1.0)

    # A-t-on laissé gagner un côté qui n'avait pas le droit de se prononcer ?
    viol = 0
    for c, v in res:
        if v in ("A_WINS", "B_WINS"):
            cote = c[v[0]]
            if not s_applique(cote, c["question"], "strict"):
                viol += 1
    return {"res": res, "n": n, "justes": justes,
            "conflict_resolution_accuracy": justes / n,
            "authority_selection_accuracy": sel,
            "unresolved_precision": unres_prec,
            "scope_violation_rate": viol / n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--scope-large", action="store_true", help="SABOTAGE : scope élargi")
    ap.add_argument("--sans-scope", action="store_true", help="SABOTAGE : scope ignoré")
    a = ap.parse_args()
    mode = "large" if a.scope_large else ("sans" if a.sans_scope else "strict")

    cas_tous = json.load(open(FIXTURES, encoding="utf-8"))["cas"]
    m = mesurer(cas_tous, mode)

    titre = {"strict": "", "large": "  ⚠️ SABOTAGE : scopes élargis",
             "sans": "  ⚠️ SABOTAGE : scope ignoré"}[mode]
    print(f"Conflits d'autorité — {m['n']} cas{titre}\n")
    for c, v in m["res"]:
        ok = v == c["attendu"]
        print(f"  {'✅' if ok else '❌'} {c['id']:48} {c['attendu']:11} → {v}")

    print(f"\n  conflict_resolution_accuracy  {m['conflict_resolution_accuracy']:.2f}")
    print(f"  authority_selection_accuracy  {m['authority_selection_accuracy']:.2f}")
    print(f"  unresolved_precision          {m['unresolved_precision']:.2f}"
          "   (quand il refuse de trancher, avait-il raison ?)")
    print(f"  scope_violation_rate          {m['scope_violation_rate']:.2f}"
          "   (a-t-on laissé gagner un hors-scope ?)")

    if a.check:
        if m["justes"] != m["n"]:
            print(f"\n❌ {m['n'] - m['justes']} cas divergent")
            return 1
        if m["scope_violation_rate"] > 0:
            print("\n❌ un côté hors de son domaine a été déclaré vainqueur")
            return 1
        print("\n✅ résolution conforme à l'ADR-0008")
    return 0


if __name__ == "__main__":
    sys.exit(main())
