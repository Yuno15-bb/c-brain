#!/usr/bin/env python3
"""
Shared status of the trunk — writes state/status.json, which the capsule reads.
Best effort: never fails, never blocks a hook.

Possible activities (each mapped to an animation in the capsule):
  distilling   ⚗️  extraction de fiches (distillateur)
  gardening    🌱  rangement global de l'arbre (jardinier)
  filing       📁  classement d'une fiche
  correcting   ✏️  correction / masquage de secret
  mapping      🗺️  updating the map
  committing   💾  sauvegarde git
  challenging  🔴  putting knowledge to the test (challenger)
  archiving    🍂  tri du froid / archivage (archiviste)
  synthesizing 🕸️  cross-cutting weave (synthesizer)
  auditing     🔧  auditing/repairing the machine (mechanic)
  architecting 🏗️  global cohesion / cross-domain bridges (architect)
  idle             au repos (Tamagotchi qui dort)

Usage CLI :  python3 brain_status.py <state> [activity] [detail]
"""
import json, os, time, sys

STATE_DIR = os.path.expanduser("~/.c-brain/trunk/state")
STATUS = os.path.join(STATE_DIR, "status.json")

def write_status(state, activity=None, detail=None, source=None):
    if source is None:
        source = "agent" if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1" else "you"
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = STATUS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"state": state, "activity": activity, "detail": detail,
                       "source": source, "ts": time.time()}, f, ensure_ascii=False)
        os.replace(tmp, STATUS)  # atomic write
    except Exception:
        pass

def touch_status():
    """HEARTBEAT: refreshes only `ts` on the current status, without touching
    state/activity/detail. Called in a loop by auto_maintain during long
    passes d'agent (un `claude -p` dure des minutes) → la capsule reste « busy »
    throughout, instead of flickering to idle when its freshness window expires.
    No-op si le fichier n'existe pas / est illisible (best-effort, ne casse rien)."""
    try:
        with open(STATUS, "r", encoding="utf-8") as f:
            cur = json.load(f)
        cur["ts"] = time.time()
        tmp = STATUS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
        os.replace(tmp, STATUS)
    except Exception:
        pass

if __name__ == "__main__":
    a = sys.argv
    if len(a) > 1 and a[1] == "touch":
        touch_status()
    else:
        write_status(a[1] if len(a) > 1 else "idle",
                     a[2] if len(a) > 2 else None,
                     a[3] if len(a) > 3 else None)
