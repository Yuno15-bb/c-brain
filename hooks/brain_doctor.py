#!/usr/bin/env python3
"""brain_doctor — integrity healthcheck of the trunk.

Checks, without modifying anything:
  1. dead [[x]] links (EXCLUDING doc examples and code blocks),
  2. orphan notes (never targeted by a link),
  3. frontmatter complet (name / description / metadata.type) et name == nom de fichier,
  4. convention de nom kebab-case,
  5. presence in the map: MEMORY.md + lessons/INDEX.md,
  6. MEMORY.md size under the safe-loading threshold,
  7. git drift (uncommitted changes).

Usage :
  brain_doctor.py            → rapport lisible + exit 0 (sain) / 1 (anomalies)
  brain_doctor.py --json     → writes state/doctor.json (for the hooks) + exit code
  brain_doctor.py --quiet    → exit code seulement
"""
import os, re, sys, json, subprocess, glob

BRAIN = os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
LESSONS_INDEX = os.path.join(BRAIN, "lessons", "INDEX.md")
MEMORY_WARN_BYTES = 20_000
STRUCTURAL_MAPS = {os.path.join("lessons", "INDEX.md")}
LINKED_DIRS = ("projects", "lessons", "life", "meta")           # the woven areas
# skip logic consistent with brain_recall/brain_embed: FOLDER segments (set) + prefixes (startswith).
# L'ancien `"sessions/archive" in parts` (token multi-segment vs segment unique) ne matchait JAMAIS
# → the archive notes + TIMELINE were being counted as "notes", polluting the counter and
# la courbe metrics.jsonl. cf. [[scan-skip-par-segment-pas-substring]]
SKIP_DIRS = {".git", "node_modules", "capsule", "corpus", "audits", "state"}
SKIP_PREFIX = ("sessions",)   # the whole archive/timeline layer (not woven knowledge)
# tokens that appear as [[...]] but are doc EXAMPLES, not links
# Bilingual on purpose: these are placeholder link names used in documentation,
# and users write their notes in their own language.
EXAMPLE_WHITELIST = {"slug", "name", "link", "links", "another-note", "examples",
                     "nom-du-fichier", "exemples", "lien", "liens",
                     "...", "class", "defined", "x", "their-name"}
INDEX_EXEMPT = {"MEMORY", "README", "TIMELINE"}


def md_files():
    out = []
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        if any(rel.startswith(pre) for pre in SKIP_PREFIX):
            continue
        parts = rel.split(os.sep)[:-1]          # segments de DOSSIER (hors nom de fichier)
        if any(d in parts for d in SKIP_DIRS):
            continue
        out.append(p)
    return out


def strip_code(text):
    """Strips ``` blocks and `inline` spans so documentation examples are not read as links."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    return text


def extract_links(text):
    return set(re.findall(r"\[\[([^\]|]+)", strip_code(text)))


def read(p):
    try:
        return open(p, encoding="utf-8").read()
    except Exception:
        return ""


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^(\w[\w.]*?):\s*(.*)$", line.strip())
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"')
    return fm


def main():
    files = md_files()
    checked_files = [
        f for f in files if os.path.relpath(f, BRAIN) not in STRUCTURAL_MAPS
    ]
    slugs = {os.path.splitext(os.path.basename(f))[0] for f in files}
    memory = read(MEMORY) + "\n" + read(LESSONS_INDEX)

    all_links = set()
    problems = {"dead_links": [], "orphans": [], "frontmatter": [],
                "naming": [], "off_index": [], "memory_too_heavy": []}

    # Structural maps contribute the links they carry, without themselves becoming
    # notes subject to the frontmatter/naming invariants.
    for f in files:
        txt = read(f)
        all_links |= extract_links(txt)

    # 1. dead links
    for l in sorted(all_links):
        if l in slugs or l in EXAMPLE_WHITELIST:
            continue
        problems["dead_links"].append(l)

    for f in checked_files:
        rel = os.path.relpath(f, BRAIN)
        base = os.path.splitext(os.path.basename(f))[0]
        zone = rel.split(os.sep)[0]
        txt = read(f)

        # 3+4. front matter & naming (woven areas only)
        if zone in LINKED_DIRS:
            fm = frontmatter(txt)
            if fm is None:
                problems["frontmatter"].append(f"{rel}: no front matter")
            else:
                if not fm.get("name"):
                    problems["frontmatter"].append(f"{rel} : 'name' manquant")
                elif fm["name"] != base:
                    problems["frontmatter"].append(f"{rel} : name='{fm['name']}' ≠ fichier '{base}'")
                if not fm.get("description"):
                    problems["frontmatter"].append(f"{rel} : 'description' manquante")
            if not re.fullmatch(r"[a-z0-9-]+", base):
                problems["naming"].append(f"{rel}: '{base}' is not kebab-case")

            # 2. orphan (never targeted by a link)
            if base not in INDEX_EXEMPT and base not in all_links:
                problems["orphans"].append(base)

            # 5. presence in the map (MEMORY.md + lessons/INDEX.md)
            if base not in INDEX_EXEMPT and base not in memory and rel not in memory:
                problems["off_index"].append(base)

    # 6. loading guard: warn before the effective limit (~24.4 kB).
    try:
        memory_bytes = os.path.getsize(MEMORY)
    except OSError:
        memory_bytes = 0
    if memory_bytes > MEMORY_WARN_BYTES:
        problems["memory_too_heavy"].append(
            f"MEMORY.md: {memory_bytes} bytes > {MEMORY_WARN_BYTES}"
        )

    # 7. drift git
    drift = []
    try:
        r = subprocess.run(["git", "-C", BRAIN, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        drift = [l for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        pass

    total = sum(len(v) for v in problems.values())
    report = {"ok": total == 0, "total": total, "notes": len(checked_files),
              "links": len(all_links), "memory_bytes": memory_bytes,
              "drift_git": len(drift), **problems}

    if "--json" in sys.argv:
        try:
            os.makedirs(os.path.join(BRAIN, "state"), exist_ok=True)
            json.dump(report, open(os.path.join(BRAIN, "state", "doctor.json"), "w"),
                      ensure_ascii=False, indent=2)
        except Exception:
            pass
        # historisation : une ligne compacte par run → tendance lisible dans le temps
        try:
            import time
            lessons = len([f for f in checked_files if os.path.relpath(f, BRAIN).startswith("lessons")])
            metric = {"ts": int(time.time()), "notes": len(checked_files), "lecons": lessons,
                      "links": len(all_links), "dead_links": len(problems["dead_links"]),
                      "orphans": len(problems["orphans"]),
                      "off_index": len(problems["off_index"]), "ok": report["ok"]}
            with open(os.path.join(BRAIN, "state", "metrics.jsonl"), "a", encoding="utf-8") as mf:
                mf.write(json.dumps(metric, ensure_ascii=False) + "\n")
        except Exception:
            pass

    if "--quiet" not in sys.argv and "--json" not in sys.argv:
        ico = "✅" if report["ok"] else "⚠️"
        print(f"{ico} brain_doctor — {len(files)} notes, {len(all_links)} links, "
              f"{len(drift)} uncommitted change(s)")
        labels = {"dead_links": "Dead links", "orphans": "Orphans",
                  "frontmatter": "Front matter", "naming": "Naming",
                  "off_index": "Off-map",
                  "memory_too_heavy": "MEMORY.md too heavy"}
        for k, lab in labels.items():
            if problems[k]:
                print(f"  ⚠️  {lab} ({len(problems[k])}): " + ", ".join(map(str, problems[k][:12])))
        if report["ok"]:
            print("  Nothing to report — the tree is consistent.")

    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
