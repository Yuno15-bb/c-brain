#!/usr/bin/env python3
"""fraicheur_fiches — ferme la boucle temps → fraîcheur.

LE PROBLÈME. Rien n'invalide une fiche périmée. Le `challenger` peut contester un fait,
mais c'est un agent qu'on lance à la main : aucune fiche ne porte de trace de la dernière
fois où quelqu'un a vérifié qu'elle est encore vraie. Une erreur écrite un jour peut donc
rester vraie pour toujours aux yeux du système.

CE QUE ÇA FAIT. Calcule, pour chaque fiche, la date de dernière VALIDATION :
  • le champ `last_validated: AAAA-MM-JJ` du frontmatter s'il existe ;
  • sinon la date du dernier COMMIT qui a touché le fichier ;
  • en tout dernier recours seulement, le mtime du fichier.

⚠️ POURQUOI PAS LE MTIME EN PREMIER. C'était le plan, et il est faux ici : la restauration
machine du 2026-07-22 a réécrit tous les fichiers du tronc. Mesuré, le fichier le plus
ancien du disque a **20 jours** alors que des fiches datent de mai — le mtime affirmait
que tout était frais et la file de revue sortait vide. L'historique git, lui, survit à une
restauration.

Au-delà de SEUIL_JOURS sans validation, la fiche entre dans une file de revue
**basse priorité** : `state/a-revalider.json`. C'est une liste qu'on consulte, jamais une
alerte qui bloque — l'objectif est de ne pas transformer la maintenance en corvée.

POURQUOI LE CHAMP N'EST PAS ÉCRIT EN MASSE. La migration « mettre le mtime dans les 312
fiches » ferait un diff énorme pour zéro information nouvelle : le mtime est déjà sur le
disque. Le champ n'apparaît donc que le jour où quelqu'un valide vraiment la fiche.

QUI ÉCRIT LE CHAMP. Le **jardinier**, jamais le challenger : le challenger consigne ses
verdicts dans `state/`, il ne touche à aucune fiche (séparation des pouvoirs, cf.
[[separation-pouvoirs-agent-teams]]). Le jardinier lit `state/revues.json` et estampille.

Usage :
  fraicheur_fiches.py            recalcule state/a-revalider.json
  fraicheur_fiches.py --rapport  recalcule et imprime la file
"""
import os, re, sys, json, time, glob, subprocess

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))
SORTIE = os.path.join(BRAIN, "state", "a-revalider.json")
DOSSIERS = ("projects", "lessons", "meta", "life")

# Réglable par l'environnement — sinon le seuil de 90 jours rend le mécanisme
# INVÉRIFIABLE tant que le tronc est jeune : il sort 0 fiche, et un calcul qui ne
# renvoie jamais rien ne prouve rien. `SEUIL_JOURS=30 fraicheur_fiches.py --rapport`
# doit lister des fiches ; si ça reste vide, c'est le calcul qui est cassé.
SEUIL_JOURS = int(os.environ.get("SEUIL_JOURS", "90"))   # ~3 mois, cf. jardinage-regles §5
FM_VALID = re.compile(r"^\s*last_validated:\s*\"?(\d{4}-\d{2}-\d{2})\"?\s*$", re.M)
FM_NAME = re.compile(r"^\s*name:\s*[\"']?([^\"'\n]+)[\"']?\s*$", re.M)


def _frontmatter(texte):
    if not texte.startswith("---"):
        return ""
    fin = texte.find("\n---", 3)
    return texte[3:fin] if fin != -1 else ""


def dates_git():
    """{chemin relatif: horodatage du dernier commit}. Un seul parcours de l'historique —
    314 appels `git log` séparés prendraient des secondes à chaque hook."""
    try:
        sortie = subprocess.run(
            ["git", "-C", BRAIN, "log", "--name-only", "--format=@%at", "--no-renames"],
            capture_output=True, text=True, timeout=25).stdout
    except Exception:
        return {}
    dates, ts = {}, None
    for ligne in sortie.splitlines():
        if ligne.startswith("@"):
            try: ts = int(ligne[1:])
            except ValueError: ts = None
        elif ligne and ts and ligne.endswith(".md"):
            dates.setdefault(ligne, ts)      # 1er vu = le plus récent (log antéchronologique)
    return dates


def analyser():
    maintenant = time.time()
    git = dates_git()
    fiches = []
    for dossier in DOSSIERS:
        for chemin in glob.glob(os.path.join(BRAIN, dossier, "**", "*.md"), recursive=True):
            rel = os.path.relpath(chemin, BRAIN)
            try:
                texte = open(chemin, encoding="utf-8").read()
                mtime = os.path.getmtime(chemin)
            except Exception:
                continue
            fm = _frontmatter(texte)
            nom = FM_NAME.search(fm)
            m = FM_VALID.search(fm)
            if m:
                try:
                    ts = time.mktime(time.strptime(m.group(1), "%Y-%m-%d"))
                    source = "validée"
                except Exception:
                    ts, source = git.get(rel, mtime), "commit"   # date illisible → repli git
            elif rel in git:
                ts, source = git[rel], "commit"
            else:
                ts, source = mtime, "fichier"
            fiches.append({
                "path": rel,
                "name": nom.group(1).strip() if nom else os.path.basename(rel)[:-3],
                "jours": int((maintenant - ts) / 86400),
                "source": source,
            })
    return fiches


def main():
    fiches = analyser()
    a_revalider = sorted((f for f in fiches if f["jours"] > SEUIL_JOURS),
                         key=lambda f: -f["jours"])
    os.makedirs(os.path.dirname(SORTIE), exist_ok=True)
    tmp = f"{SORTIE}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"seuil_jours": SEUIL_JOURS, "calcule_le": time.strftime("%Y-%m-%d"),
                   "total_fiches": len(fiches), "fiches": a_revalider},
                  f, ensure_ascii=False)
    os.replace(tmp, SORTIE)

    if "--rapport" not in sys.argv:
        return 0
    jamais = sum(1 for f in fiches if f["source"] != "validée")
    print(f"{len(fiches)} fiches · {jamais} n'ont jamais été validées explicitement")
    print(f"au-delà de {SEUIL_JOURS} jours : {len(a_revalider)} fiches en file de revue "
          f"(basse priorité, aucune alerte)")
    for f in a_revalider[:12]:
        print(f"  {f['jours']:4d} j  ({f['source']})  {f['path']}")
    if len(a_revalider) > 12:
        print(f"  … et {len(a_revalider) - 12} autres — voir {os.path.relpath(SORTIE, BRAIN)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
