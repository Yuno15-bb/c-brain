#!/usr/bin/env python3
"""track_read — boucle de vérité (H3) : journalise quand une fiche du Brain est LUE.

Hook PostToolUse (Read). Si un Read cible une fiche du tronc, on l'enregistre dans
state/read_log.jsonl. Croisé avec recall_log.jsonl (ce qui a été remonté), ça donne
l'UTILITÉ réelle de chaque fiche : remontée souvent mais jamais lue = peu utile ;
jamais remontée ni lue depuis longtemps = poids mort (candidate archivage).

Signal fondé sur l'usage RÉEL, pas l'introspection. Sort toujours 0.
"""
import sys, os, json, time

BRAIN = os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))
LOG = os.path.join(BRAIN, "state", "read_log.jsonl")


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return
    ti = data.get("tool_input", {}) or {}
    fp = ti.get("file_path") or ti.get("path")
    if not fp:
        return
    real = os.path.realpath(fp)
    # uniquement les fiches du tronc (pas les hooks/capsule/etc.)
    if not real.startswith(BRAIN + os.sep) or not real.endswith(".md"):
        return
    rel = os.path.relpath(real, BRAIN)
    if rel == "MEMORY.md" or rel.split(os.sep)[0] not in ("projects", "lessons", "life", "meta"):
        return
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": int(time.time()),
                                "sid": data.get("session_id") or "",
                                "path": rel}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    refresh_live()


def refresh_live():
    """Rallume la fiche sur la planète TOUT DE SUITE (~0,15 s) : sans ça, l'activité « en direct »
    n'apparaîtrait qu'à la prochaine écriture de fiche ou à la fin de session — donc jamais en direct.
    Best-effort et silencieux : un échec ici ne doit rien casser du hook."""
    import subprocess
    for script in ("coactivation.py", "graph_export.py"):
        try:
            subprocess.run([sys.executable, os.path.join(BRAIN, "hooks", script)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
