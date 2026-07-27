#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert. Source-available, see LICENSE.
#   Running it is allowed. Redistributing or rebuilding from it is not.
"""C Brain — declarative generalization, run AFTER sync.sh has copied.

Why a script rather than hand edits: sync.sh re-copies the engine from the
living Brain on every pass. A manual fix would be silently overwritten, and the
leak would be back at the next commit. A rule replays.

Rules live in rules.json. Two families:
  · blocks       — rewriting a block of CODE (a table, a function).
  · replacements — text substitution (comments, labels, examples).

A counter dropping to 0 on an expected rule FAILS the script: it means the
source changed its wording and the rule no longer bites.

Exit 0 = generalized · Exit 1 = a rule stopped biting, or a block was not found.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RULES = ROOT / "rules.json"


def targets(patterns):
    """Repo files targeted by a list of globs, deduplicated and sorted."""
    seen = {}
    for g in patterns:
        for p in ROOT.glob(g):
            if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts:
                seen[p] = True
    return sorted(seen)


def validate(rules):
    """A malformed rule must produce a message, not a Python traceback.
    Already hit once: a substitution rule filed by mistake among the blocks —
    the script died on a KeyError, in the middle of a sync."""
    ok = True
    for r in rules.get("blocks", []):
        if "file" not in r or "pattern" not in r or "replace" not in r:
            print(f"  ⛔ block '{r.get('id', '?')}' — needs file + pattern + replace"
                  f"{' (a rule with `files` belongs in replacements)' if 'files' in r else ''}")
            ok = False
    for r in rules.get("replacements", []):
        if "files" not in r or "pattern" not in r or not ({"replace", "replace_map"} & set(r)):
            print(f"  ⛔ substitution '{r.get('id', '?')}' — needs files + pattern + replace|replace_map")
            ok = False
    return ok


def apply_blocks(rules, report):
    ok = True
    for rule in rules:
        path = ROOT / rule["file"]
        if not path.is_file():
            print(f"  ⛔ {rule['id']} — file missing: {rule['file']}")
            ok = False
            continue
        text = path.read_text(encoding="utf-8")
        new, n = re.subn(rule["pattern"], lambda _m: rule["replace"], text,
                         flags=re.S)
        if n == 0:
            print(f"  ⛔ {rule['id']} — block NOT FOUND in {rule['file']}")
            print(f"       the source changed shape; the rule must be updated")
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
                # Several phrasings around the same name: each gets its own
                # replacement, otherwise the sentence comes out lopsided.
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
            print(f"  ⛔ {rule['id']} — {total} occurrence(s), {expect} expected")
            print(f"       a falling counter = the source changed, NOT good news")
            ok = False
            continue
        report.append((rule["id"], total, ", ".join(touched), rule["why"]))
    return ok


def check_json_still_valid():
    """A rule removing a block from a .json can leave an orphan comma.
    The file is still "text" — the error only surfaces at the first `npm` or the
    first `json.load`, far from here. We check right away."""
    broken = []
    for path in ROOT.rglob("*.json"):
        if {".git", "node_modules"} & set(path.relative_to(ROOT).parts):
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            broken.append((path.relative_to(ROOT).as_posix(), e))
    for rel, e in broken:
        print(f"  ⛔ {rel} — invalid JSON after generalization: {e}")
    return not broken


def main():
    if not RULES.is_file():
        sys.exit(f"❌ rules.json not found ({RULES})")
    rules = json.loads(RULES.read_text(encoding="utf-8"))

    if not validate(rules):
        print("\n⛔ malformed rules.json — nothing was applied.")
        return 1

    report = []
    ok = apply_blocks(rules.get("blocks", []), report)
    ok = apply_replacements(rules.get("replacements", []), report) and ok
    ok = check_json_still_valid() and ok

    print(f"🧹 Generalization — {len(report)} rule(s) applied, "
          f"{sum(r[1] for r in report)} replacement(s)\n")
    for rid, n, where, _why in report:
        print(f"   {n:>4}×  {rid:<28} {where}")

    if not ok:
        print("\n⛔ FAILED — at least one rule stopped biting. Nothing may ship as is.")
        return 1

    print("\n✅ Generalized. Now check: python3 leakcheck.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
