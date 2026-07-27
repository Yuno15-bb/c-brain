# 🥚 Capsule — le Tamagotchi du C Brain

Petite capsule flottante (Electron, toujours au premier plan) qui **anime en temps réel** ce que font les agents du Brain : distillation ⚗️, correction ✏️, rangement 📁, optimisation 🌿, mise à jour de la carte 🗺️.

L'animation reflète de **vraies** opérations : les hooks écrivent `state/status.json` à chaque action, la capsule le lit 2×/seconde.

## Lancer

```bash
cd ~/.c-brain/trunk/capsule
npm install      # la 1re fois (télécharge Electron)
npm start
```

- La pousse 🌱 **dort** (zzz) quand rien ne se passe.
- Elle **s'active** + halo vert dès que les agents travaillent (« 🤖 les agents travaillent »).
- `⌘⇧B` : montrer / cacher la capsule. Glisse-la où tu veux. Survol → bouton ×.

## Comment ça marche

```
hooks (on_fiche_write / auto_maintain) ──écrivent──▶ ~/.c-brain/trunk/state/status.json
                                                              │
                                          capsule (poll 400ms) ┘  ──▶ animation
```

`status.json` : `{ state:"busy"|"idle", activity, detail, source:"agent"|"you", ts }`.

## Tester l'animation à la main

```bash
python3 ~/.c-brain/trunk/hooks/brain_status.py busy distilling "extraction <projet>"
python3 ~/.c-brain/trunk/hooks/brain_status.py busy filing "rangement lessons/cache-pwa"
python3 ~/.c-brain/trunk/hooks/brain_status.py idle
```
