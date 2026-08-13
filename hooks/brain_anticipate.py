#!/usr/bin/env python3
"""brain_anticipate — proactif (Volet 2 · Horizon 4) : le cerveau devance le besoin.

Au lieu d'attendre qu'on l'interroge, il scanne les fiches pour les POINTS DE REPRISE
("RESUME HERE", "NEXT", "resume point"…) and surfaces, by recency, where you
left off and what the next step was — at session start (SessionStart hook)
ou via `brain next`.

Le cerveau qui tend la fiche AVANT qu'on la cherche. Sort toujours 0.
"""
import os, re, sys, glob

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
SKIP_PARTS = (".git", "node_modules", "capsule", "sessions/archive", "corpus", "audits")
# Strong markers (real resume points) then weak ones (generic todos).
# BILINGUAL on purpose: these patterns match what YOU wrote in your own notes,
# not the language of this codebase. Dropping the French forms would silently
# stop surfacing resume points for anyone writing in French.
# Add your own language here — it is a plain list of alternatives.
STRONG = re.compile(r"(RESUME HERE|RESUME POINT|PICK UP HERE|NEXT STEP|LEFT TO DO"
                    r"|REPRENDRE ICI|POINT DE REPRISE|À REPRENDRE|REPRENDRE"
                    r"|PROCHAINE ÉTAPE|RESTE À FAIRE)", re.I)
WEAK = re.compile(r"(TODO|NEXT\b|PROCHAIN[E]?\b|À FAIRE\b)", re.I)


def best_marker(text):
    """Prefer a STRONG marker; fall back to a weak one. Takes the LAST occurrence
    (resume points usually sit at the end of a note)."""
    hits = list(STRONG.finditer(text)) or list(WEAK.finditer(text))
    return hits[-1] if hits else None


def snippet(text, m):
    """~160 characters around the marker, on a single line."""
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    if end == -1:
        end = len(text)
    line = text[start:end].strip()
    return re.sub(r"\s+", " ", line)[:180]


def collect():
    out = []
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        # skip par SEGMENT de dossier (pas substring : sinon une fiche projet « capsule-… »
        # would be wrongly skipped, missing its resume point). Skip by path SEGMENT, not substring.
        if rel == "MEMORY.md" or any(part in rel.split(os.sep) for part in SKIP_PARTS):
            continue
        zone = rel.split(os.sep)[0]
        if zone not in ("projects",):     # les reprises vivent dans les fiches projet
            continue
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception:
            continue
        m = best_marker(txt)
        if m:
            name = re.search(r"^name:\s*(.+)$", txt, re.M)
            out.append({"path": rel, "mtime": os.path.getmtime(p),
                        "name": name.group(1).strip() if name else os.path.basename(rel)[:-3],
                        "reprise": snippet(txt, m)})
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def main():
    items = collect()[:4]
    if not items:
        return
    mode_hook = "--hook" in sys.argv
    if mode_hook:
        print("<brain-resume> Pending resume points (from your project notes, "
              "newest first) — offer to continue if relevant:")
    else:
        print("🧭 Pending resume points:\n")
    for it in items:
        if mode_hook:
            print(f"- {it['name']} ({it['path']}): {it['reprise']}")
        else:
            print(f"  • {it['name']}  ({it['path']})")
            print(f"      ↳ {it['reprise']}")
    if mode_hook:
        print("</brain-resume>")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
