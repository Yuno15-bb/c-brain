#!/usr/bin/env python3
"""brain_doctor — healthcheck d'intégrité du C Brain.

Vérifie, sans rien modifier :
  1. liens [[x]] morts (en EXCLUANT les exemples de doc et les blocs de code),
  2. fiches orphelines (jamais ciblées par un lien),
  3. frontmatter complet (name / description / metadata.type) et name == nom de fichier,
  4. convention de nom kebab-case,
  5. présence dans la carte MEMORY.md + lessons/INDEX.md,
  6. taille de MEMORY.md sous le seuil de chargement sûr,
  7. drift git (modifs non commitées).

Usage :
  brain_doctor.py            → rapport lisible + exit 0 (sain) / 1 (anomalies)
  brain_doctor.py --json     → écrit state/doctor.json (pour les hooks) + exit code
  brain_doctor.py --quiet    → exit code seulement
"""
import os, re, sys, json, subprocess, glob

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
LESSONS_INDEX = os.path.join(BRAIN, "lessons", "INDEX.md")
MEMORY_WARN_BYTES = 20_000
STRUCTURAL_MAPS = {os.path.join("lessons", "INDEX.md")}
LINKED_DIRS = ("projects", "lessons", "life", "meta")           # zones tissées
# skip cohérent avec brain_recall/brain_embed : segments de DOSSIER (set) + préfixes (startswith).
# L'ancien `"sessions/archive" in parts` (token multi-segment vs segment unique) ne matchait JAMAIS
# → les ~130 notes d'archive + TIMELINE étaient comptées comme « fiches », polluant le compteur et
# la courbe metrics.jsonl. cf. [[scan-skip-par-segment-pas-substring]]
SKIP_DIRS = {".git", "node_modules", "capsule", "corpus", "audits", "state",
             # `archive/` = couche froide : ses journaux ne sont pas des fiches et
             # leurs [[liens]] gelés ne doivent pas polluer le compteur ni les liens morts.
             "archive"}
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


def _familles():
    """Le registre des familles, et POURQUOI il est vide s'il l'est.

    Un `except: return set()` nu confond deux états très différents : « le
    registre est là et ne contient rien » et « le registre est ABSENT ». Le
    second arrive pour de bon — meta/familles.json est resté hors de la liste
    blanche de sync.sh jusqu'au 2026-08-15, donc le paquet public embarquait
    les trois programmes qui le lisent sans le registre lui-même.

    Sans cette distinction, brain_doctor rougissait quand même, mais en
    disant 223 fois « famille inconnue ['controle-qui-ment'] » — un message
    qui accuse les FICHES alors que c'est la PIÈCE MAÎTRESSE qui manque.
    Cf. nommer-le-manque-ne-suffit-pas-nommer-l-etape-suivante.
    """
    p = os.path.join(BRAIN, "meta", "familles.json")
    try:
        with open(p, encoding="utf-8") as f:
            return set(json.load(f).get("familles", {})), None
    except FileNotFoundError:
        return set(), (f"meta/familles.json ABSENT ({p}) — le registre des familles "
                       "thématiques ne suit pas le code qui le lit ; le rappel perd son "
                       "pont de vocabulaire, sans autre signe. → restaure-le : "
                       "`git checkout meta/familles.json` dans le tronc, ou relance "
                       "./install.sh (le paquet le livre dans skeleton/meta/).")
    except Exception as e:
        return set(), (f"meta/familles.json illisible ({p}) : {e} — le registre est là "
                       "mais ne se charge pas ; répare le JSON avant de juger les tags.")


FAMILLES, FAMILLES_ERREUR = _familles()


def main():
    files = md_files()
    checked_files = [
        f for f in files if os.path.relpath(f, BRAIN) not in STRUCTURAL_MAPS
    ]
    slugs = {os.path.splitext(os.path.basename(f))[0] for f in files}
    memory = read(MEMORY) + "\n" + read(LESSONS_INDEX)

    all_links = set()
    problems = {"liens_morts": [], "orphelins": [], "frontmatter": [],
                "nommage": [], "hors_index": [], "memory_trop_lourd": [],
                # axe thématique (2026-08-14) : une leçon sans famille est invisible pour
                # le pont de vocabulaire du rappel — et la prochaine fiche écrite sortira
                # sans tag si RIEN ne l'exige, cf. le-premier-fichier-d-un-type-nouveau…
                "lecons_sans_famille": [], "index_derive": [],
                # la PIÈCE elle-même, avant les fiches qui s'y réfèrent
                "registre_familles": []}
    if FAMILLES_ERREUR:
        problems["registre_familles"].append(FAMILLES_ERREUR)

    # Les cartes structurelles contribuent les liens qu'elles portent, sans devenir
    # elles-mêmes des fiches soumises aux invariants de frontmatter/nommage.
    for f in files:
        txt = read(f)
        all_links |= extract_links(txt)

    # 1. liens morts
    # INDEX dérivé : la carte des leçons est GÉNÉRÉE depuis les tags. Si elle diffère de ce
    # que le générateur produirait, quelqu'un l'a éditée à la main — et sa correction sera
    # écrasée au prochain passage sans prévenir.
    try:
        import subprocess as _sp
        r = _sp.run([sys.executable, os.path.join(BRAIN, "hooks", "index_lecons.py"), "--verifie"],
                    capture_output=True, text=True)
        if r.returncode != 0:
            problems["index_derive"].append("lessons/INDEX.md a été édité à la main — régénérer")
    except Exception:
        pass

    for l in sorted(all_links):
        if l in slugs or l in EXAMPLE_WHITELIST:
            continue
        problems["liens_morts"].append(l)

    for f in checked_files:
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

            # 5. présence dans la carte (MEMORY.md + lessons/INDEX.md)
            if base not in INDEX_EXEMPT and base not in memory and rel not in memory:
                problems["hors_index"].append(base)

            # 6. toute leçon porte une famille thématique (1 principale + 1 secondaire max)
            if zone == "lessons" and base not in INDEX_EXEMPT:
                t = re.search(r"^tags:\s*\[(.*?)\]", txt, re.M)
                noms = [x.strip() for x in t.group(1).split(",") if x.strip()] if t else []
                if not noms:
                    problems["lecons_sans_famille"].append(f"{base} : aucun tag")
                elif len(noms) > 2:
                    problems["lecons_sans_famille"].append(f"{base} : {len(noms)} tags (plafond 2)")
                elif not FAMILLES_ERREUR:
                    # Muet SI le registre est absent : sans lui, chacune des 223 leçons
                    # sortirait « famille inconnue », et le vrai défaut (une pièce
                    # manquante) serait noyé sous 223 accusations de fiches saines.
                    inconnus = [n for n in noms if n not in FAMILLES]
                    if inconnus:
                        problems["lecons_sans_famille"].append(f"{base} : famille inconnue {inconnus}")

    # 6. garde-fou de chargement : alerte avant la limite effective (~24,4 ko).
    try:
        memory_bytes = os.path.getsize(MEMORY)
    except OSError:
        memory_bytes = 0
    if memory_bytes > MEMORY_WARN_BYTES:
        problems["memory_trop_lourd"].append(
            f"MEMORY.md : {memory_bytes} octets > {MEMORY_WARN_BYTES}"
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
    report = {"ok": total == 0, "total": total, "fiches": len(checked_files),
              "liens": len(all_links), "memory_bytes": memory_bytes,
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
            metric = {"ts": int(time.time()), "fiches": len(checked_files), "lecons": lessons,
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
        # ⚠️ TOUTE CLÉ DE `problems` DOIT AVOIR SON LIBELLÉ. Cette table était écrite en dur :
        # deux contrôles ajoutés le 2026-08-14 (famille manquante, INDEX dérivé) remplissaient
        # bien `problems`, comptaient dans le total et faisaient sortir en 1 — mais n'imprimaient
        # RIEN. Un contrôle qui détecte sans le dire est un contrôle muet. L'assertion en dessous
        # empêche la prochaine addition de retomber dedans.
        labels = {"registre_familles": "Registre des familles",
                  "liens_morts": "Liens morts", "orphelins": "Orphelins",
                  "frontmatter": "Frontmatter", "nommage": "Nommage",
                  "hors_index": "Hors carte",
                  "memory_trop_lourd": "MEMORY.md trop lourd",
                  "lecons_sans_famille": "Leçons sans famille thématique",
                  "index_derive": "lessons/INDEX.md édité à la main"}
        muets = [k for k in problems if k not in labels]
        if muets:
            print(f"  ⚠️  contrôles SANS libellé, donc invisibles : {muets}")
        for k, lab in labels.items():
            if problems[k]:
                print(f"  ⚠️  {lab} ({len(problems[k])}): " + ", ".join(map(str, problems[k][:12])))
        if report["ok"]:
            print("  Rien à signaler — arbre cohérent.")

    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
