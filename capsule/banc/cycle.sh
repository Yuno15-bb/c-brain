#!/bin/bash
# FULL CYCLE — walks the LIVE orb through every one of its states, in family
# order, so it can be watched on the real desktop.
#
# ⚠ THIS CYCLE FALSIFIES ITSELF IF YOU WORK DURING IT. Every tool call the agent
#   makes writes `status.json` back to "busy / working" via hooks/brain_battement.py:
#   the orb then shows WORKING instead of the cycle's state, and the
#   demonstration lies. Launch it DETACHED, then run nothing until it ends.
#
# ⚠ It drives an ALREADY RUNNING orb — it does not open one. Check first:
#     pgrep -f "c-brain/trunk/capsule" | wc -l      (0 = nothing to watch)
#
# Usage:  ./banc/cycle.sh [seconds per state]     (default 4)
set -u
PAUSE="${1:-4}"
STATUS="$HOME/.c-brain/trunk/hooks/brain_status.py"

# The order follows the FAMILIES, not the alphabet: you see each mechanic climb
# in intensity, then tip over into the next one. Alphabetical order would jump
# the colour at every step and the 1.4 s cross-fade would have nothing to tell.
ETATS=(
  mapping auditing architecting challenging      # Inspection     — swell
  filing archiving gardening correcting          # Organisation   — sweep
  working distilling synthesizing                # Transformation — vortex
  committing                                     # Validation     — shards
  idle                                           # Rest           — breath
)

echo "cycle: ${#ETATS[@]} states × ${PAUSE}s ≈ $(( ${#ETATS[@]} * PAUSE ))s"
for e in "${ETATS[@]}"; do
  if [ "$e" = "idle" ]; then python3 "$STATUS" idle >/dev/null
  else                       python3 "$STATUS" busy "$e" cycle >/dev/null; fi
  printf '%s ' "$e"
  sleep "$PAUSE"
done
echo
echo "cycle over — the orb is back at rest"
