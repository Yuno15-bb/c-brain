#!/usr/bin/env python3
"""Vérification discrète des mises à jour, branchée sur SessionStart.

Trois règles non négociables :
  · JAMAIS bloquant — au pire il ne dit rien. Une session ne doit pas attendre
    le réseau pour démarrer.
  · Au plus une vérification par 24 h (horodatage sur disque).
  · Il ne met RIEN à jour tout seul. Il signale, l'utilisateur décide.

C'est volontaire : du code qui s'installe sans qu'on l'ait demandé est un canal
d'exécution chez quelqu'un d'autre. Le signalement, lui, ne coûte rien.

Sortie toujours 0.
"""

import os
import subprocess
import sys
import time

CB = os.path.expanduser("~/.c-brain")
STAMP = os.path.join(CB, "state", "dernier-check-update")
INTERVAL = 24 * 3600


def main():
    engine = os.path.join(CB, "engine")
    if not os.path.isdir(engine):
        return 0

    # Throttle : un fichier d'horodatage, pas un verrou. Si le check plante,
    # l'horodatage est quand même posé — on ne veut pas d'une boucle qui
    # réessaie à chaque session.
    now = time.time()
    try:
        if now - os.path.getmtime(STAMP) < INTERVAL:
            return 0
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(STAMP), exist_ok=True)
        open(STAMP, "w").write(str(now))
    except OSError:
        return 0

    try:
        r = subprocess.run(["bash", os.path.join(engine, "cbrain", "update.sh"), "--check"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return 0   # hors ligne, git absent, lenteur : on se tait

    if r.returncode == 10:      # convention de update.sh : une version existe
        tag = ""
        for line in r.stdout.splitlines():
            if "nouvelle version disponible" in line:
                tag = line.split(":")[-1].strip()
        print(f"<c-brain-update>Une nouvelle version de C Brain est disponible"
              f"{' (' + tag + ')' if tag else ''}. "
              f"Lance `brain update` quand ça t'arrange — tes fiches ne seront pas touchées."
              f"</c-brain-update>")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # un hook ne casse JAMAIS une session
