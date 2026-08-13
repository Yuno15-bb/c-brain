#!/usr/bin/env python3
"""SessionEnd — marque la fin dans le flux et nettoie les pré-images + totaux.

Le flux `sessions/<sid>.jsonl` reste sur disque (purgé à 7 jours) : c'est l'archive
relisable de ce qui a été touché pendant la session.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


FEED_TTL_DAYS = 7


def prune_old_feeds():
    """Les flux de session sont l'archive relisable ; au-delà d'une semaine ils ne
    servent plus qu'à remplir le disque."""
    import time

    from companion_lib import SESSIONS

    cutoff = time.time() - FEED_TTL_DAYS * 86400
    try:
        names = os.listdir(SESSIONS)
    except OSError:
        return
    for name in names:
        p = os.path.join(SESSIONS, name)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                os.remove(p)
        except OSError:
            pass


def main():
    # ANTI-RÉCURSION (Phase 0 du RFC Brain V3, 2026-08-03) : un agent de
    # maintenance headless n'est pas une session de travail — il ne doit ni
    # clore un flux, ni purger les pré-images de la vraie session en cours.
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        return

    from companion_lib import AGG, SNAP, append_event, read_hook_input

    data = read_hook_input()
    sid = data.get("session_id")
    if not sid:
        return

    append_event(sid, {"type": "end", "reason": data.get("reason") or "fin de session"})

    shutil.rmtree(os.path.join(SNAP, sid), ignore_errors=True)
    try:
        os.remove(os.path.join(AGG, sid + ".json"))   # totaux : la session est finie
    except OSError:
        pass
    prune_old_feeds()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
