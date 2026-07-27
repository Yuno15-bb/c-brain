#!/usr/bin/env python3
"""Ajoute un session_id à sessions/.distilled.json — appelé par le wrapper
UNIQUEMENT si l'agent de distillation a réussi (claude exit 0). Évite de marquer
'distillée' une session qui a échoué (ex. limite de quota atteinte)."""
import json, os, sys

DISTILLED = os.path.expanduser("~/.c-brain/trunk/sessions/.distilled.json")

def main():
    if len(sys.argv) < 2:
        return
    sid = sys.argv[1]
    try:
        cur = set(json.load(open(DISTILLED, encoding="utf-8")))
    except Exception:
        cur = set()
    cur.add(sid)
    try:
        json.dump(sorted(cur), open(DISTILLED, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass

if __name__ == "__main__":
    main()
