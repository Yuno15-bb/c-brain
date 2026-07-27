#!/usr/bin/env python3
"""Capsule animation test pass: walks through EVERY activity,
8 s per step, refreshing ts to stay 'busy' (idle threshold = 6 s)."""
import json, time, os

# Derived from $HOME, not __file__: it is the TRUNK's state we drive.
STATUS = os.path.join(os.path.expanduser('~'), 'claude-brain', 'state', 'status.json')

# pipeline order → covers the 11 activities index.html recognizes (idle excluded)
STEPS = [
    ("distilling",   "DISTILLATEUR — extraction des fiches"),
    ("gardening",    "JARDINIER — rangement & liens [[ ]]"),
    ("filing",       "JARDINIER — classement dans MEMORY.md"),
    ("correcting",   "JARDINIER — correction d'une fiche"),
    ("mapping",      "JARDINIER — cartographie de l'index"),
    ("architecting", "ARCHITECTE — ponts inter-domaines"),
    ("challenging",  "CHALLENGER — putting the knowledge to the test"),
    ("archiving",    "ARCHIVIST — pruning dead weight"),
    ("synthesizing", "SYNTHESIZER — cross-cutting essay"),
    ("auditing",     "MECHANIC — auditing the machine"),
    ("committing",   "SAUVEGARDE git — versionnage"),
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
print("■ Fin de la phase de test — retour en IDLE")
