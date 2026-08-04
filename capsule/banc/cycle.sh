#!/bin/bash
# CYCLE COMPLET — fait passer l'orbe VIVANTE par tous ses états, dans l'ordre
# des familles, pour la regarder sur le vrai bureau.
#
# ⚠ CE CYCLE SE FAUSSE TOUT SEUL SI ON TRAVAILLE PENDANT. Chaque appel d'outil
#   de Claude repose `status.json` en « busy / working » via hooks/brain_battement.py :
#   l'orbe affiche alors WORKING au lieu de l'état du cycle, et la démonstration
#   ment. Le lancer DÉTACHÉ, puis ne plus rien exécuter jusqu'à la fin.
#
# ⚠ Il pilote l'orbe DÉJÀ LANCÉE — il n'en ouvre pas une. Vérifier avant :
#     pgrep -f "claude-brain/capsule" | wc -l     (0 = rien à regarder)
#
# Usage :  ./banc/cycle.sh [secondes par état]     (défaut 4)
set -u
PAUSE="${1:-4}"
STATUS="$HOME/claude-brain/hooks/brain_status.py"

# L'ordre suit les FAMILLES, pas l'alphabet : on voit chaque mécanique monter en
# intensité, puis basculer dans la suivante. Un ordre alphabétique ferait sauter
# la couleur à chaque pas et le fondu de 1,4 s n'aurait plus rien à raconter.
ETATS=(
  mapping auditing architecting challenging      # Inspection   — houle
  filing archiving gardening correcting          # Organisation — balayage
  working distilling synthesizing                # Transformation — vortex
  committing                                     # Validation   — eclats
  idle                                           # Repos        — respiration
)

echo "cycle : ${#ETATS[@]} états × ${PAUSE}s ≈ $(( ${#ETATS[@]} * PAUSE ))s"
for e in "${ETATS[@]}"; do
  if [ "$e" = "idle" ]; then python3 "$STATUS" idle >/dev/null
  else                       python3 "$STATUS" busy "$e" cycle >/dev/null; fi
  printf '%s ' "$e"
  sleep "$PAUSE"
done
echo
echo "fin du cycle — l'orbe est revenue au repos"
