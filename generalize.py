#!/usr/bin/env python3
"""C Brain — généralisation déclarative, jouée APRÈS la copie de sync.sh.

Pourquoi un script et pas des corrections à la main : sync.sh recopie le moteur
depuis le Brain vivant à chaque passe. Une correction manuelle serait écrasée en
silence, et la fuite reviendrait au commit suivant. Une règle se rejoue.

Règles dans rules.json. Deux familles :
  · blocks       — réécriture d'un bloc de CODE (une table, une fonction).
  · replacements — substitution de texte (commentaires, libellés, exemples).

Un compteur tombé à 0 sur une règle attendue fait ÉCHOUER le script : ça veut
dire que la source a changé de formulation et que la règle ne mord plus.

Sortie 0 = généralisé · Sortie 1 = une règle ne mord plus, ou un bloc introuvable.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RULES = ROOT / "rules.json"


def targets(patterns):
    """Fichiers du dépôt visés par une liste de globs, dédupliqués et triés."""
    seen = {}
    for g in patterns:
        for p in ROOT.glob(g):
            if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts:
                seen[p] = True
    return sorted(seen)


def validate(rules):
    """Une règle mal formée doit produire un message, pas une trace Python.
    Cas déjà rencontré : une règle de substitution rangée par erreur parmi les
    blocs — le script mourait sur un KeyError, en plein milieu d'un sync."""
    ok = True
    for r in rules.get("blocks", []):
        if "file" not in r or "pattern" not in r or "replace" not in r:
            print(f"  ⛔ bloc « {r.get('id', '?')} » — il faut file + pattern + replace"
                  f"{' (une règle avec `files` va dans replacements)' if 'files' in r else ''}")
            ok = False
    for r in rules.get("replacements", []):
        if "files" not in r or "pattern" not in r or not ({"replace", "replace_map"} & set(r)):
            print(f"  ⛔ substitution « {r.get('id', '?')} » — il faut files + pattern + replace|replace_map")
            ok = False
    return ok


def apply_blocks(rules, report):
    ok = True
    for rule in rules:
        path = ROOT / rule["file"]
        if not path.is_file():
            print(f"  ⛔ {rule['id']} — fichier absent : {rule['file']}")
            ok = False
            continue
        text = path.read_text(encoding="utf-8")
        new, n = re.subn(rule["pattern"], lambda _m: rule["replace"], text,
                         flags=re.S)
        if n == 0:
            print(f"  ⛔ {rule['id']} — bloc INTROUVABLE dans {rule['file']}")
            print(f"       la source a changé de forme ; la règle doit être remise à jour")
            ok = False
            continue
        path.write_text(new, encoding="utf-8")
        report.append((rule["id"], n, rule["file"], rule["why"]))
    return ok


def apply_replacements(rules, report):
    ok = True
    for rule in rules:
        total = 0
        touched = []
        rx = re.compile(rule["pattern"])
        for path in targets(rule["files"]):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "replace_map" in rule:
                # Plusieurs formulations autour du même nom : chacune a sa
                # tournure de remplacement, sinon la phrase devient bancale.
                def sub(m):
                    return rule["replace_map"].get(m.group(0), m.group(0))
                new, n = rx.subn(sub, text)
            else:
                new, n = rx.subn(rule["replace"], text)
            if n:
                path.write_text(new, encoding="utf-8")
                total += n
                touched.append(path.relative_to(ROOT).as_posix())
        expect = rule.get("expect", 1)
        if total < expect:
            print(f"  ⛔ {rule['id']} — {total} occurrence(s), {expect} attendue(s)")
            print(f"       un compteur qui baisse = la source a changé, PAS une bonne nouvelle")
            ok = False
            continue
        report.append((rule["id"], total, ", ".join(touched), rule["why"]))
    return ok


def check_json_still_valid():
    """Une règle qui retire un bloc d'un .json peut laisser une virgule orpheline.
    Le fichier reste « du texte » — l'erreur ne se voit qu'au premier `npm` ou au
    premier `json.load`, loin d'ici. On vérifie tout de suite."""
    broken = []
    for path in ROOT.rglob("*.json"):
        if {".git", "node_modules"} & set(path.relative_to(ROOT).parts):
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            broken.append((path.relative_to(ROOT).as_posix(), e))
    for rel, e in broken:
        print(f"  ⛔ {rel} — JSON invalide après généralisation : {e}")
    return not broken


def main():
    if not RULES.is_file():
        sys.exit(f"❌ rules.json introuvable ({RULES})")
    rules = json.loads(RULES.read_text(encoding="utf-8"))

    if not validate(rules):
        print("\n⛔ rules.json mal formé — rien n'a été appliqué.")
        return 1

    report = []
    ok = apply_blocks(rules.get("blocks", []), report)
    ok = apply_replacements(rules.get("replacements", []), report) and ok
    ok = check_json_still_valid() and ok

    print(f"🧹 Généralisation — {len(report)} règle(s) appliquée(s), "
          f"{sum(r[1] for r in report)} remplacement(s)\n")
    for rid, n, where, _why in report:
        print(f"   {n:>4}×  {rid:<28} {where}")

    if not ok:
        print("\n⛔ ÉCHEC — au moins une règle ne mord plus. Rien ne doit sortir en l'état.")
        return 1

    print("\n✅ Généralisé. Contrôle maintenant : python3 leakcheck.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
