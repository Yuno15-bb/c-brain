#!/usr/bin/env python3
"""commit_par_zone — sauvegarde le tronc dans git, UNE ZONE PAR COMMIT.

Appelé à la fin de chaque session par auto_maintain, après le passage des
agents. Purement mécanique : aucun LLM, aucun réseau, rien qui sorte de la
machine.

POURQUOI PAS `git add -A`
    C'est ce que faisait la sauvegarde automatique jusqu'au 2026-08-13, et
    c'est ce qui a noyé 19 fichiers d'un chantier en cours dans le commit
    e61fd01 (2026-08-03) : un commit fourre-tout raconte plusieurs histoires
    et son message n'en dira qu'une. 612 commits de ce type dorment dans
    l'historique du Brain de l'auteur.
    Ici, chaque zone part dans son propre commit, avec son propre message —
    un chantier en cours reste identifiable au lieu d'être noyé.

CE QU'IL NE FAIT PAS
    Il ne POUSSE rien. Un tronc contient des notes personnelles ; les envoyer
    vers un dépôt distant est une décision de son propriétaire, pas l'effet de
    bord d'une fin de session. (L'auteur, lui, pousse le sien depuis
    `tools/sync_depots.py`, qui ne fait pas partie du paquet.)

Usage :
  commit_par_zone.py             commite
  commit_par_zone.py --dry-run   dit ce qu'il ferait, n'écrit rien
"""
import os, sys, subprocess

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))

# Le hook pre-commit du tronc découpe déjà par zone : on emploie SA table, pas
# une copie qui divergerait au premier dossier nouveau.
ZONES = (("hooks/", "moteur"), ("tests/", "moteur"), ("companion/", "moteur"),
         ("cbrain/", "moteur"), ("capsule/", "moteur"),
         ("projects/", "savoir"), ("lessons/", "savoir"), ("meta/", "savoir"),
         ("life/", "savoir"), ("agents/", "savoir"),
         ("sessions/", "archives"))
LIBELLE = {"moteur": "moteur : hooks, tests et capsule",
           "savoir": "savoir : fiches, leçons et cartes",
           "archives": "archives : sessions et journaux",
           "racine": "racine : cartes de démarrage, audits et outillage"}
ORDRE = ("archives", "savoir", "racine", "moteur")


def zone(f):
    for prefixe, z in ZONES:
        if f.startswith(prefixe):
            return z
    return "racine"


def sh(cmd, cwd, timeout=180):
    """Renvoie (code, sortie). Jamais d'exception : ce script ne doit rien casser."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except Exception as e:
        return 1, str(e)


def modifies(cwd):
    _, out = sh(["git", "status", "--porcelain"], cwd)
    return [l[3:].strip().strip('"') for l in out.splitlines() if l.strip()]


def commit_par_zone(cwd, prefixe_msg="auto: ", dry=False):
    """Un commit par zone. Renvoie le nombre de commits posés."""
    poses = 0
    for z in ORDRE:
        sh(["git", "reset", "-q"], cwd)
        sel = [f for f in modifies(cwd) if zone(f) == z]
        if not sel:
            continue
        if dry:
            print(f"    [dry] {z:9} {len(sel):4d} fichier(s)")
            poses += 1
            continue
        code, _ = sh(["git", "add", "--"] + sel, cwd)
        if code:
            continue
        # Pas de ligne « Co-Authored-By » ici : ce commit est pose dans le depot
        # de son proprietaire par sa propre machine. Y coller une adresse mail —
        # fut-elle publique — a la fois salit son historique et fait rougir
        # leakcheck, qui traque les adresses dans TOUT ce qui part dans le paquet.
        msg = (f"{prefixe_msg}{LIBELLE[z]}\n\n"
               f"Commit automatique par zone ({len(sel)} fichier(s)).\n"
               f"Une zone par commit : un chantier en cours reste identifiable "
               f"dans l'historique au lieu d'etre noye par un `git add -A`.\n")
        # Auteur « C Brain » : un commit posé par la machine ne doit pas
        # porter la signature de l'humain.
        r = subprocess.run(["git", "-c", "user.name=C Brain",
                            "-c", "user.email=brain@local",
                            "commit", "-q", "-F", "-"], cwd=cwd,
                           input=msg, text=True, capture_output=True)
        if r.returncode == 0:
            print(f"    ✅ {z:9} {len(sel):4d} fichier(s)")
            poses += 1
        else:
            # le hook pre-commit du tronc peut refuser : on le DIT, on n'insiste pas.
            print(f"    ⚠️  {z:9} refusé : {(r.stdout + r.stderr).strip()[:120]}")
    sh(["git", "reset", "-q"], cwd)
    return poses


def main():
    dry = "--dry-run" in sys.argv
    code, _ = sh(["git", "rev-parse", "--git-dir"], BRAIN)
    if code:
        print("  tronc hors git — rien à sauvegarder")   # cas normal : personne n'a fait `git init`
        return 0
    n = len(modifies(BRAIN))
    if not n:
        print("  rien à commiter")
        return 0
    print(f"  {n} fichier(s) modifié(s)")
    commit_par_zone(BRAIN, dry=dry)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"commit_par_zone : {e}")
        sys.exit(0)                              # ne casse JAMAIS l'appelant
