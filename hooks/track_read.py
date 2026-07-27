#!/usr/bin/env python3
"""track_read — the truth loop: logs when a note in the trunk is actually READ.

Hook PostToolUse (Read). Si un Read cible une fiche du tronc, on l'enregistre dans
state/read_log.jsonl. Cross-referenced with recall_log.jsonl (what was surfaced), it gives
the real USEFULNESS of each note: surfaced often but never read = of little use;
never surfaced nor read for a long time = dead weight (an archiving candidate).

A signal grounded in REAL usage, not introspection. Always exits 0.
"""
import sys, os, json, time

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
