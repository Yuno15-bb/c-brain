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


def _tmp_path():
    """A temp file THIS process owns alone.

    No sweeper is needed: `os.replace` consumes the file on the happy path, and the
    `except Exception: pass` path leaves at most one small orphan per crashed process.
    """
    return f"{STATUS}.{os.getpid()}.tmp"

def write_status(state, activity=None, detail=None, source=None):
    if source is None:
        source = "agent" if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1" else "you"
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        # ⚠️ THE TEMP PATH MUST BE UNIQUE PER PROCESS. It used to be a single fixed
        # `status.json.tmp` shared by both writers of this file, and during a gardening
        # pass there are two BY DESIGN: the heartbeat calling `touch` every 5 s, and the
        # pipeline calling `busy <activity>` at each stage. `os.replace` is atomic for the
        # RENAME; it serialises nothing about the writes INTO the temp file. One writer
        # truncating with "w" while the other had written a longer payload leaves a splice
        # of both, and the reader gets `Extra data: line 1 column 120`. Observed on a real
        # install, 2026-08-16 (Maissane Lagsir):
        #     {"state": "busy", …, "ts": 1786874328.244719}79}
        # the trailing `79}` being the tail of the other writer's timestamp.
        # With one temp file per process, `os.replace` becomes the only contended
        # operation — which is the whole reason it was chosen.
        tmp = _tmp_path()
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
        tmp = _tmp_path()          # per-process, same reason as in write_status()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
        os.replace(tmp, STATUS)
    except Exception:
        pass

STATES = ("busy", "idle")   # the 1st argument is a STATE; the activity is the 2nd


def show_status():
    """SHOWS the current status. NEVER writes it.

    Exists since 2026-08-04. Before that: `brain status` called `brain_status.py show`,
    but this file was only a WRITER — so "show" was taken for a state and RECORDED in
    status.json. Result: the CLI's flagship command displayed nothing (empty output,
    exit 0, so the `||` fallbacks in the `brain` script never fired) and corrupted, in
    passing, the very state the capsule reads. Two faults in one line."""
    try:
        with open(STATUS, "r", encoding="utf-8") as f:
            s = json.load(f)
    except FileNotFoundError:
        print("(no status: state/status.json is missing)")
        return 0
    except Exception as e:
        print(f"(unreadable status: {e})")
        return 1
    age = time.time() - (s.get("ts") or 0)
    fresh = age < 120
    state = s.get("state") or "?"
    if state not in STATES:
        state += "  ⚠️ unknown state (status.json was corrupted by a faulty call)"
    print(f"state    : {state}")
    print(f"activity : {s.get('activity') or '—'}")
    print(f"detail   : {s.get('detail') or '—'}")
    print(f"source   : {s.get('source') or '—'}")
    when = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.get('ts') or 0))
    print(f"since    : {when}  ({int(age)} s — {'fresh' if fresh else 'STALE, the capsule reads it as idle'})")
    return 0


if __name__ == "__main__":
    a = sys.argv
    cmd = a[1] if len(a) > 1 else "idle"
    if cmd == "touch":
        touch_status()
    elif cmd in ("show", "status"):
        sys.exit(show_status())
    elif cmd in STATES:
        write_status(cmd, a[2] if len(a) > 2 else None, a[3] if len(a) > 3 else None)
    else:
        # REFUSE rather than record: any word at all was accepted as a state, so a typo
        # silently poisoned the very file the capsule reads.
        print(f"unknown state: {cmd!r} — expected {' | '.join(STATES)} (or touch / show).",
              file=sys.stderr)
        print("Usage: brain_status.py <busy|idle> [activity] [detail]  ·  ... touch  ·  ... show",
              file=sys.stderr)
        sys.exit(2)
