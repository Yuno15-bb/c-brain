#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""Mise à jour automatique, branchée sur SessionStart.

Le contrat, en quatre points :
  · JAMAIS bloquant — la mise à jour part DÉTACHÉE, en arrière-plan. Une session
    ne doit pas attendre le réseau pour démarrer, et surtout pas attendre un
    `git checkout` + un selftest.
  · À chaque démarrage de session. Pas de fenêtre de 24 h : c'était une
    temporisation utile quand le hook ne faisait qu'AFFICHER une ligne qu'on
    finissait par ne plus lire. Une mise à jour qui s'applique toute seule n'a
    aucune raison d'attendre le lendemain.
  · Un compte rendu DIFFÉRÉ. Ce qui s'affiche au démarrage est le résultat du
    passage PRÉCÉDENT : celui de maintenant vient à peine de partir et n'a rien
    à raconter. C'est la contrepartie du non-bloquant, et elle est honnête —
    mieux vaut une nouvelle avec une session de retard qu'une session qui attend.
  · Ça se coupe. `brain update --auto-off`, ou CBRAIN_NO_AUTO_UPDATE=1 : on
    retombe alors sur l'ancien comportement, signaler sans appliquer.

Sort TOUJOURS 0 : un hook ne casse jamais une session.
"""

import os
import subprocess
import sys

CB = os.path.expanduser("~/.c-brain")
STATE = os.path.join(CB, "state")
RESULTAT = os.path.join(STATE, "last-auto-update")
ARRET = os.path.join(STATE, "auto-update-off")


def rendre_compte():
    """Affiche le résultat du passage précédent, puis l'efface.

    L'effacement fait partie du contrat : le fichier est un MESSAGE, pas un
    état. Le garder ferait réafficher « mis à jour en v1.28.0 » à chaque
    session pendant des semaines, et on apprendrait à ne plus le lire —
    exactement le défaut qui a tué l'ancien avis.
    """
    try:
        with open(RESULTAT) as f:
            etat, _, tag = f.read().strip().partition("\t")
    except OSError:
        return
    try:
        os.remove(RESULTAT)
    except OSError:
        pass

    if etat == "ok":
        msg = (f"C Brain s'est mis à jour tout seul en {tag}. "
               f"Tes fiches n'ont pas été touchées.")
    elif etat == "retour-arriere":
        msg = (f"La mise à jour automatique vers {tag} a échoué au selftest : "
               f"C Brain est REVENU à la version d'avant, tout seul. "
               f"Journal : ~/.c-brain/state/auto-update.log")
    elif etat == "bloquee":
        msg = (f"Mise à jour {tag} disponible mais NON appliquée : le moteur a "
               f"des modifications locales non commitées. Range-les, ou lance "
               f"`brain update` pour voir le détail.")
    else:
        return
    print(f"<c-brain-update>{msg}</c-brain-update>")


def main():
    engine = os.path.join(CB, "engine")
    if not os.path.isdir(engine):
        return 0

    rendre_compte()

    if os.path.exists(ARRET) or os.environ.get("CBRAIN_NO_AUTO_UPDATE"):
        # Comportement d'avant, conservé mot pour mot pour qui a coupé
        # l'automatique : on regarde, on signale, on n'applique rien.
        try:
            r = subprocess.run(
                ["bash", os.path.join(engine, "cbrain", "update.sh"), "--check"],
                capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return 0            # hors ligne, git absent, lien lent : on se tait
        if r.returncode == 10:
            tag = ""
            for line in r.stdout.splitlines():
                if "nouvelle version disponible" in line:
                    tag = line.split(":")[-1].strip()
            print(f"<c-brain-update>Une nouvelle version de C Brain est disponible"
                  f"{' (' + tag + ')' if tag else ''}. "
                  f"Lance `brain update` quand ça t'arrange — tes fiches ne bougent pas."
                  f"</c-brain-update>")
        return 0

    # ─── Le lancement détaché ─────────────────────────────────────────────
    # `start_new_session=True` n'est PAS un détail de confort : sans lui, le
    # processus reste dans le groupe de la session Claude Code et meurt avec
    # elle. Or ce qu'il fait au milieu, c'est remplacer le moteur — être tué
    # entre le `checkout` et le `install.sh` laisse une installation à moitié
    # basculée. Le détachement est ce qui rend l'opération sûre à interrompre :
    # la session peut fermer, la mise à jour va au bout.
    #
    # Les flux vont vers /dev/null et non vers un tuyau : un tuyau que personne
    # ne lit finit par se remplir et FIGE l'écrivain. Le script écrit son propre
    # journal, il n'a besoin de rien d'autre.
    try:
        with open(os.devnull, "r+b") as vide:
            subprocess.Popen(
                ["bash", os.path.join(engine, "cbrain", "update.sh"), "--auto"],
                stdin=vide, stdout=vide, stderr=vide,
                start_new_session=True,
                cwd=engine,
            )
    except (OSError, subprocess.SubprocessError):
        pass                    # rien ne justifie de gêner un démarrage
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # un hook ne casse JAMAIS une session
