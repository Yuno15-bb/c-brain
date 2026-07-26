#!/usr/bin/env python3
"""Phase de test de l'animation de la capsule : parcourt TOUTES les activités,
8 s par étape, en rafraîchissant le ts pour rester 'busy' (seuil idle = 6 s)."""
import json, time, os

# Dérivé de $HOME, pas de __file__ : c'est le state du TRONC qu'on pilote.
STATUS = os.path.join(os.path.expanduser('~'), 'claude-brain', 'state', 'status.json')

# ordre du pipeline → couvre les 11 activités reconnues par index.html (idle exclu)
STEPS = [
    ("distilling",   "DISTILLATEUR — extraction des fiches"),
    ("gardening",    "JARDINIER — rangement & liens [[ ]]"),
    ("filing",       "JARDINIER — classement dans MEMORY.md"),
    ("correcting",   "JARDINIER — correction d'une fiche"),
    ("mapping",      "JARDINIER — cartographie de l'index"),
    ("architecting", "ARCHITECTE — ponts inter-domaines"),
    ("challenging",  "CHALLENGER — mise à l'épreuve du savoir"),
    ("archiving",    "ARCHIVISTE — élagage du poids mort"),
    ("synthesizing", "SYNTHÉTISEUR — essai transverse"),
    ("auditing",     "MÉCANICIEN — audit de la machine"),
    ("committing",   "SAUVEGARDE git — versionnage"),
]

HOLD = 8.0       # secondes par étape
REFRESH = 2.5    # ré-écriture du ts pour ne pas retomber en idle (<6 s)

def write(state, activity=None, detail=None):
    with open(STATUS, 'w') as f:
        json.dump({"state": state, "activity": activity, "detail": detail,
                   "source": "test", "ts": time.time()}, f)

print(f"▶ Phase de test — {len(STEPS)} étapes × {HOLD:.0f}s")
for i, (act, detail) in enumerate(STEPS, 1):
    print(f"  [{i}/{len(STEPS)}] {act} — {detail}")
    t_end = time.time() + HOLD
    while time.time() < t_end:
        write("busy", act, detail)
        time.sleep(min(REFRESH, max(0.1, t_end - time.time())))
write("idle")
print("■ Fin de la phase de test — retour en IDLE")
