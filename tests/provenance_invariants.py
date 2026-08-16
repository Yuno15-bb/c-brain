#!/usr/bin/env python3
"""
provenance_invariants.py — le contrôleur du protocole de provenance (ADR-0009).

CE QU'IL FAIT. Lit le bloc `provenance:` / `authority:` d'une fiche et dit s'il respecte
les invariants I1→I7. Il ne juge JAMAIS le contenu de la fiche, seulement la forme et les
transitions autorisées : une machine ne peut pas savoir si une information est vraie, elle
peut savoir si son origine est déclarée et si quelqu'un s'est promu tout seul.

CE QU'IL NE FAIT PAS, DÉLIBÉRÉMENT.
  • Il ne touche à aucune fiche du tronc. Les 469 fiches restent `unknown` de fait, et
    c'est le comportement voulu : pas d'autorité, pertinence intacte (ADR-0009).
  • Il n'écrit rien. Il répond.

ZÉRO DÉPENDANCE, ET C'EST UN CHOIX. PyYAML est installé sur cette machine, et n'est pas
utilisé : ce contrôleur a vocation à migrer dans `hooks/`, où la règle est zéro dépendance
(cf. meta/decisions/adr-0001-bm25-reste-le-moteur-de-rappel.md). Le sous-ensemble de YAML
décrit par l'ADR-0009 est petit et fermé ; on le lit avec le même outillage que le reste
du dépôt, qui parse déjà son frontmatter à la main.

POURQUOI LES FIXTURES CONTIENNENT DES CAS FAUX. Un jeu qui ne contient que des cas valides
ne peut pas faire rougir le contrôleur : il passerait au vert même si toutes les règles
étaient désactivées. Chaque invariant a donc au moins une violation qui DOIT être refusée.
cf. lessons/test-d-equivalence-vert-aussi-quand-le-code-est-inerte.md

Lancer :
  python3 tests/provenance_invariants.py           # rapport lisible
  python3 tests/provenance_invariants.py --check   # barrière : sort 1 si un cas diverge
"""
import argparse
import json
import os
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(ICI, "fixtures_provenance.json")

# ── le vocabulaire, fermé. Une valeur inventée est refusée, jamais tolérée : c'est ce qui
#    empêche le champ de dériver en texte libre, où plus aucun contrôle n'est possible.
KINDS = {"user_decision", "internal_experience", "official_documentation",
         "external_document", "web", "agent_inference", "unknown"}
SCOPES = {"repository", "project", "global", "world"}
ROLES = {"basis", "evidence", "illustration"}

# Les seules classes qui portent de la NORMATIVITÉ (le droit d'instruire le Brain).
# `official_documentation` n'y est pas, et c'est le cœur de l'affaire : une doc peut être
# très fiable pour décrire une API et n'avoir aucun droit de dicter la façon de travailler.
# TRUST ≠ NORMATIVITY.
NORMATIFS = {"user_decision", "internal_experience"}

# ── ORDRE DE FORCE — la source unique, du plus faible au plus fort ────────────────────
# UNE LISTE ORDONNÉE, PAS UN DICTIONNAIRE DE POIDS. Les deux consommateurs de
# `kind_effectif` en avaient chacun leur version, et elles DIVERGEAIENT déjà : sur des
# bases {official_documentation, web}, le résolveur rendait `official_documentation` et la
# propagation rendait `web`. Pire, le dictionnaire du résolveur mettait cinq classes à
# égalité 0 — `min` sur un ensemble dépend alors de l'ordre d'itération, qui varie d'un
# processus à l'autre. Ce n'était pas qu'une dette de style : rendre `official_documentation`
# pour une fiche fondée sur le web est exactement le blanchiment que I7 interdit.
# Une liste est un ordre TOTAL : pas d'égalité possible, donc pas de non-déterminisme.
# cf. [[un-detecteur-partage-par-concept]]
FORCE = ["unknown", "agent_inference", "web", "external_document",
         "official_documentation", "internal_experience", "user_decision"]


def kind_effectif(prov):
    """I7 — le kind d'une connaissance est celui de ce qui la FONDE, au plus faible.

    Une fiche bâtie sur le web qui cite une décision de l'auteur en illustration reste une
    fiche web : la citation n'est pas un blanchiment. On prend donc la source `basis` la
    PLUS FAIBLE — si quoi que ce soit de faible fonde la connaissance, elle est faible.

    ⚠️ Écrite ICI et nulle part ailleurs. Le résolveur d'autorité et la propagation
    l'importent. Deux détecteurs indépendants du même concept divergent toujours, et la
    divergence ne se voit pas — celle-ci avait déjà commencé.
    """
    if prov.get("sources"):
        bases = [s["kind"] for s in prov["sources"] if s.get("role") == "basis"]
        if not bases:
            return "unknown"
        return min(bases, key=lambda k: FORCE.index(k) if k in FORCE else 0)
    return prov.get("kind", "unknown")


# ---------------------------------------------------------------- lecture du frontmatter
def _lire_bloc(txt, nom):
    """Extrait le sous-arbre `nom:` d'un frontmatter indenté à 2 espaces.

    Volontairement limité au sous-ensemble décrit par l'ADR-0009 : clés simples, listes de
    scalaires, et listes de mappings pour `sources` / `corrections`. Tout ce qui sort de ce
    cadre n'est pas silencieusement ignoré — il ne peut simplement pas être écrit.
    """
    m = re.search(rf"^{nom}:\s*$(.*?)(?=^\S|\Z)", txt, re.M | re.S)
    if not m:
        return None
    corps = m.group(1)
    bloc, liste_courante, cle_liste = {}, None, None
    for ligne in corps.split("\n"):
        if not ligne.strip():
            continue
        indent = len(ligne) - len(ligne.lstrip())
        s = ligne.strip()
        if s.startswith("- "):                      # élément de liste de mappings
            liste_courante = {}
            bloc.setdefault(cle_liste, []).append(liste_courante)
            s = s[2:].strip()
            if ":" in s:
                k, v = s.split(":", 1)
                liste_courante[k.strip()] = _scalaire(v)
            continue
        if ":" in s:
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip()
            if indent >= 4 and liste_courante is not None:
                liste_courante[k] = _scalaire(v)
            elif v == "":                            # une clé qui ouvre une liste
                cle_liste, liste_courante = k, None
            else:
                bloc[k] = _scalaire(v)
                liste_courante = None
    return bloc


def _scalaire(v):
    v = v.strip().strip('"').strip("'")
    if v in ("true", "false"):
        return v == "true"
    if v.startswith("[") and v.endswith("]"):
        return [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
    return v


# ---------------------------------------------------------------- les invariants
def controler(frontmatter, parent_kind=None):
    """Retourne la liste des violations. Liste vide = la fiche respecte le protocole."""
    fautes = []
    prov = _lire_bloc(frontmatter, "provenance") or {}
    auth = _lire_bloc(frontmatter, "authority") or {}
    valid = _lire_bloc(frontmatter, "validation") or {}

    kind = prov.get("kind")
    sources = prov.get("sources") or []
    validated = auth.get("validated") is True

    # — vocabulaire fermé
    if kind not in KINDS:
        fautes.append(f"vocabulaire : kind='{kind}' hors liste")
    if auth.get("scope") and auth["scope"] not in SCOPES:
        fautes.append(f"vocabulaire : scope='{auth['scope']}' hors liste")

    # — l'observable doit être nommé. Sans `ref`, la provenance est une affirmation, pas
    #   une trace. `unknown` en est exempt : il n'a justement rien à montrer (I2).
    if kind and kind != "unknown" and not prov.get("ref") and not sources:
        fautes.append("observable : `ref` absent alors que kind != unknown")

    # — I6 : l'autorité est bornée par son domaine. Traduction mécanique : l'auteur décide de
    #   ses projets, pas de la réalité extérieure.
    if kind == "user_decision" and auth.get("scope") == "world":
        fautes.append("I6 : un user_decision ne peut pas porter scope: world")

    # — I2 : absence d'information = absence d'autorité.
    if kind == "unknown" and validated:
        fautes.append("I2 : `unknown` ne peut pas être validated")

    if validated:
        # — I1 + I3 : une source externe ne se promeut jamais, quelle que soit la preuve
        #   invoquée. C'est la promotion silencieuse que I3 interdit.
        if kind in (KINDS - NORMATIFS) and kind != "unknown":
            fautes.append(f"I1/I3 : une source '{kind}' ne devient jamais validated")
        # — I1 : validated exige une PREUVE, pas une conviction.
        #
        #   ⚠️ ASYMÉTRIE VOULUE, ET C'EST LE BANC QUI L'A RÉVÉLÉE. La première version
        #   exigeait un bloc `validation` de TOUT le monde, et refusait donc F1 — une
        #   décision explicite de l'auteur. C'était faux : `user_decision` est l'une des trois
        #   sources autorisées de l'ADR-0009, elle ne se fait pas valider par une autre,
        #   elle EST la validation. Sa preuve est la citation elle-même, dans `ref`.
        #   Une `internal_experience`, elle, doit montrer son rejeu ou la règle qui la fonde.
        #   Corrigé dans le CONTRÔLEUR, pas dans la fixture : réécrire le critère après
        #   avoir lu le résultat, c'est fabriquer le résultat.
        if kind == "user_decision":
            if not prov.get("ref"):
                fautes.append("I1 : user_decision validated sans citation dans `ref`")
        elif not valid and not auth.get("basis_ref"):
            fautes.append("I1 : validated sans bloc `validation` ni `basis_ref`")
        # — une commande qui n'est pas nommée ne peut pas être rejouée par un tiers ;
        #   une validation qu'on ne peut pas rejouer n'est pas une validation.
        if valid.get("method") == "deterministic_replay":
            if not valid.get("command"):
                fautes.append("I1 : rejeu déterministe sans `command`")
            if valid.get("result") != "pass":
                fautes.append("I1 : rejeu déterministe dont le résultat n'est pas `pass`")

    # — I4 : une correction sans qui/quand/pourquoi est indiscernable d'une falsification.
    for c in prov.get("corrections") or []:
        manquants = [k for k in ("from", "to", "at", "by", "why") if not c.get(k)]
        if manquants:
            fautes.append(f"I4 : correction incomplète, manque {', '.join(manquants)}")

    # — I5 : multi-source accepté, mais la normativité se calcule sur les sources `basis`,
    #   jamais sur les citations décoratives. Sans cette règle, citer proprement une source
    #   externe affaiblirait une règle interne — l'effet pervers exact qu'on veut éviter.
    if sources:
        for s in sources:
            if s.get("kind") not in KINDS:
                fautes.append(f"I5 : source de kind='{s.get('kind')}' hors liste")
            if s.get("role") not in ROLES:
                fautes.append(f"I5 : source de role='{s.get('role')}' hors liste")
        bases = {s.get("kind") for s in sources if s.get("role") == "basis"}
        if not bases:
            fautes.append("I5 : aucune source `basis` — rien ne fonde cette connaissance")
        elif kind in NORMATIFS and not (bases & NORMATIFS):
            fautes.append(f"I5/I7 : kind='{kind}' alors qu'aucune source `basis` ne l'est "
                          f"(bases : {', '.join(sorted(bases)) or '—'})")

    # — I7 : une transformation ne blanchit jamais une origine. Une fiche descendue d'une
    #   fiche externe ne devient pas interne parce qu'elle a été réécrite ici.
    if prov.get("derived_from") and parent_kind:
        if parent_kind not in NORMATIFS and kind in NORMATIFS:
            fautes.append(f"I7 : descend d'une fiche '{parent_kind}' et se déclare "
                          f"'{kind}' — blanchiment par transformation")

    return fautes


# ---------------------------------------------------------------- banc
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="barrière : sort 1 si un cas ne rend pas le verdict attendu")
    args = ap.parse_args()

    blob = json.load(open(FIXTURES, encoding="utf-8"))
    cas = blob["cas"]
    divergences = []

    print(f"Invariants de provenance (ADR-0009) — {len(cas)} fixtures, aucune vraie fiche\n")
    for c in cas:
        fautes = controler(c["frontmatter"], c.get("parent_kind"))
        verdict = "refuse" if fautes else "valide"
        ok = verdict == c["attendu"]
        if not ok:
            divergences.append((c, verdict, fautes))
        mark = "✅" if ok else "❌"
        inv = f" [{c['invariant']}]" if c.get("invariant") else ""
        print(f"  {mark} {c['id']:32} attendu {c['attendu']:6} → {verdict}{inv}")
        if fautes and c["attendu"] == "refuse":
            print(f"        ↳ {fautes[0]}")
        if not ok:
            print(f"        ⚠️  {'aucune faute détectée' if verdict == 'valide' else fautes}")

    valides = sum(1 for c in cas if c["attendu"] == "valide")
    print(f"\n  {valides} cas représentatifs · {len(cas) - valides} violations attendues")

    if divergences:
        print(f"\n❌ {len(divergences)} cas divergent du verdict attendu")
        return 1
    print("\n✅ les 7 invariants se comportent comme l'ADR-0009 les décrit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
