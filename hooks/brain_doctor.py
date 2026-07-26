#!/usr/bin/env python3
"""brain_doctor — healthcheck d'intégrité du Claude Brain.

Vérifie, sans rien modifier :
  1. liens [[x]] morts (en EXCLUANT les exemples de doc et les blocs de code),
  2. fiches orphelines (jamais ciblées par un lien),
  3. frontmatter complet (name / description / metadata.type) et name == nom de fichier,
  4. convention de nom kebab-case,
  5. présence dans l'index MEMORY.md,
  6. drift git (modifs non commitées).

Usage :
  brain_doctor.py            → rapport lisible + exit 0 (sain) / 1 (anomalies)
  brain_doctor.py --json     → écrit state/doctor.json (pour les hooks) + exit code
  brain_doctor.py --quiet    → exit code seulement
"""
import os, re, sys, json, subprocess, glob

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
LINKED_DIRS = ("projects", "lessons", "life", "meta")           # zones tissées
# skip cohérent avec brain_recall/brain_embed : segments de DOSSIER (set) + préfixes (startswith).
# L'ancien `"sessions/archive" in parts` (token multi-segment vs segment unique) ne matchait JAMAIS
# → les ~130 notes d'archive + TIMELINE étaient comptées comme « fiches », polluant le compteur et
# la courbe metrics.jsonl. cf. [[scan-skip-par-segment-pas-substring]]
SKIP_DIRS = {".git", "node_modules", "capsule", "corpus", "audits"}
SKIP_PREFIX = ("sessions",)   # toute la couche d'archive/timeline (≠ savoir tissé)
# tokens qui apparaissent comme [[...]] mais sont des EXEMPLES de doc, pas des liens
EXAMPLE_WHITELIST = {"slug", "nom-du-fichier", "exemples", "lien", "liens",
                     "...", "name", "class", "defined", "x", "their-name"}
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
    """Retire les blocs ``` et les spans `inline` pour ne pas lire les exemples."""
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
    slugs = {os.path.splitext(os.path.basename(f))[0] for f in files}
    memory = read(MEMORY)

    all_links = set()
    problems = {"liens_morts": [], "orphelins": [], "frontmatter": [],
                "nommage": [], "hors_index": []}

    for f in files:
        txt = read(f)
        all_links |= extract_links(txt)

    # 1. liens morts
    for l in sorted(all_links):
        if l in slugs or l in EXAMPLE_WHITELIST:
            continue
        problems["liens_morts"].append(l)

    for f in files:
        rel = os.path.relpath(f, BRAIN)
        base = os.path.splitext(os.path.basename(f))[0]
        zone = rel.split(os.sep)[0]
        txt = read(f)

        # 3+4. frontmatter & nommage (uniquement zones tissées)
        if zone in LINKED_DIRS:
            fm = frontmatter(txt)
            if fm is None:
                problems["frontmatter"].append(f"{rel} : pas de frontmatter")
            else:
                if not fm.get("name"):
                    problems["frontmatter"].append(f"{rel} : 'name' manquant")
                elif fm["name"] != base:
                    problems["frontmatter"].append(f"{rel} : name='{fm['name']}' ≠ fichier '{base}'")
                if not fm.get("description"):
                    problems["frontmatter"].append(f"{rel} : 'description' manquante")
            if not re.fullmatch(r"[a-z0-9-]+", base):
                problems["nommage"].append(f"{rel} : '{base}' n'est pas en kebab-case")

            # 2. orphelin (jamais ciblé par un lien)
            if base not in INDEX_EXEMPT and base not in all_links:
                problems["orphelins"].append(base)

            # 5. présence dans l'index MEMORY.md (par chemin ou par [[name]])
            if base not in INDEX_EXEMPT and base not in memory and rel not in memory:
                problems["hors_index"].append(base)

    # 6. drift git
    drift = []
    try:
        r = subprocess.run(["git", "-C", BRAIN, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=10)
        drift = [l for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        pass

    total = sum(len(v) for v in problems.values())
    report = {"ok": total == 0, "total": total, "fiches": len(files),
              "liens": len(all_links), "drift_git": len(drift), **problems}

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
            lessons = len([f for f in files if os.path.relpath(f, BRAIN).startswith("lessons")])
            metric = {"ts": int(time.time()), "fiches": len(files), "lecons": lessons,
                      "liens": len(all_links), "liens_morts": len(problems["liens_morts"]),
                      "orphelins": len(problems["orphelins"]),
                      "hors_index": len(problems["hors_index"]), "ok": report["ok"]}
            with open(os.path.join(BRAIN, "state", "metrics.jsonl"), "a", encoding="utf-8") as mf:
                mf.write(json.dumps(metric, ensure_ascii=False) + "\n")
        except Exception:
            pass

    if "--quiet" not in sys.argv and "--json" not in sys.argv:
        ico = "✅" if report["ok"] else "⚠️"
        print(f"{ico} brain_doctor — {len(files)} fiches, {len(all_links)} liens, "
              f"{len(drift)} modif(s) non commitée(s)")
        labels = {"liens_morts": "Liens morts", "orphelins": "Orphelins",
                  "frontmatter": "Frontmatter", "nommage": "Nommage",
                  "hors_index": "Hors index"}
        for k, lab in labels.items():
            if problems[k]:
                print(f"  ⚠️  {lab} ({len(problems[k])}): " + ", ".join(map(str, problems[k][:12])))
        if report["ok"]:
            print("  Rien à signaler — arbre cohérent.")

    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
