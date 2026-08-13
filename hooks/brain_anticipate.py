#!/usr/bin/env python3
"""brain_anticipate — proactif (Volet 2 · Horizon 4) : le cerveau devance le besoin.

Au lieu d'attendre qu'on l'interroge, il scanne les fiches pour les POINTS DE REPRISE
(« REPRENDRE ICI », « PROCHAIN », « point de reprise »…) et surface, par récence, là où
tu en étais et quelle était la prochaine étape — au démarrage de session (hook SessionStart)
ou via `brain next`.

Le cerveau qui tend la fiche AVANT qu'on la cherche. Sort toujours 0.
"""
import os, re, sys, glob

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
SKIP_PARTS = (".git", "node_modules", "capsule", "sessions/archive", "corpus", "audits")
# marqueurs forts (vrais points de reprise) puis faibles (todo génériques)
STRONG = re.compile(r"(REPRENDRE ICI|POINT DE REPRISE|À REPRENDRE|REPRENDRE"
                    r"|PROCHAINE ÉTAPE|RESTE À FAIRE)", re.I)
WEAK = re.compile(r"(PROCHAIN[E]?\b|À FAIRE\b|TODO|NEXT)", re.I)


def best_marker(text):
    """Privilégie un marqueur FORT ; à défaut un faible. Prend la DERNIÈRE occurrence
    (les points de reprise sont en général en fin de fiche)."""
    hits = list(STRONG.finditer(text)) or list(WEAK.finditer(text))
    return hits[-1] if hits else None


def snippet(text, m):
    """~160 caractères autour du marqueur, sur une ligne."""
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
        # serait sautée à tort, ratant son point de reprise). cf. [[scan-skip-par-segment-pas-substring]]
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
    mode_hook = "--hook" in sys.argv
    if not items:
        # En HOOK, ne rien dire : un tronc vide ne doit pas ajouter une ligne à
        # chaque prompt. En COMMANDE, le dire — `brain next` est une commande
        # d'affichage, et une commande d'affichage qui n'imprime rien ne se
        # distingue pas d'une commande cassée. C'est exactement ce silence que
        # le §8 du selftest sort en rouge sur un tronc neuf, où n'avoir aucun
        # point de reprise est l'état NORMAL.
        if not mode_hook:
            print("🧭 Aucun point de reprise en attente.")
        return
    if mode_hook:
        print("<brain-reprises> Points de reprise en attente (tes fiches projet, "
              "du plus récent au plus ancien) — propose de continuer si pertinent :")
    else:
        print("🧭 Reprises en attente :\n")
    for it in items:
        if mode_hook:
            print(f"- {it['name']} ({it['path']}) : {it['reprise']}")
        else:
            print(f"  • {it['name']}  ({it['path']})")
            print(f"      ↳ {it['reprise']}")
    if mode_hook:
        print("</brain-reprises>")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
