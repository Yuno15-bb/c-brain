#!/usr/bin/env python3
"""Capsule animation test pass: walks through EVERY activity,
8 s per step, refreshing ts to stay 'busy' (idle threshold = 6 s)."""
import json, time, os

# Derived from $HOME, not __file__: it is the TRUNK's state we drive.
STATUS = os.path.join(os.path.expanduser('~'), '.c-brain', 'trunk', 'state', 'status.json')

# pipeline order → covers the 11 activities index.html recognizes (idle excluded)
STEPS = [
    ("distilling",   "DISTILLER — extracting notes"),
    ("gardening",    "GARDENER — tidying & [[ ]] links"),
    ("filing",       "GARDENER — filing into MEMORY.md"),
    ("correcting",   "GARDENER — fixing a note"),
    ("mapping",      "GARDENER — mapping the index"),
    ("architecting", "ARCHITECT — cross-domain bridges"),
    ("challenging",  "CHALLENGER — putting the knowledge to the test"),
    ("archiving",    "ARCHIVIST — pruning dead weight"),
    ("synthesizing", "SYNTHESIZER — cross-cutting essay"),
    ("auditing",     "MECHANIC — auditing the machine"),
    ("committing",   "BACKUP git — versioning"),
]

HOLD = 8.0       # seconds per step
REFRESH = 2.5    # ts rewrite so it does not fall back to idle (<6 s)

def write(state, activity=None, detail=None):
    with open(STATUS, 'w') as f:
        json.dump({"state": state, "activity": activity, "detail": detail,
                   "source": "test", "ts": time.time()}, f)

print(f"▶ Test pass — {len(STEPS)} steps × {HOLD:.0f}s")
for i, (act, detail) in enumerate(STEPS, 1):
    print(f"  [{i}/{len(STEPS)}] {act} — {detail}")
    t_end = time.time() + HOLD
    while time.time() < t_end:
        write("busy", act, detail)
        time.sleep(min(REFRESH, max(0.1, t_end - time.time())))
write("idle")
print("■ End of test pass — back to IDLE")
