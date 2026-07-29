#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# changelog.sh — réécrit CHANGELOG.md depuis les tags annotés.
#
# POURQUOI IL EST GÉNÉRÉ. Un changelog écrit à la main est un DEUXIÈME endroit
# qui dit ce qu'une version a fait, et le deuxième endroit est celui qui
# pourrit : le message de tag, lui, est ce que `publish.sh` exige et ce que la
# release GitHub affiche, donc il est toujours écrit. Dériver le fichier des
# tags fait qu'il ne peut pas diverger de ce qu'il décrit — au pire il est en
# retard, jamais faux.
#
# La FAMILLE de tags suit la branche : sur `fr` on liste les tags `-fr`, la
# version française de ces mêmes versions ; ailleurs, les tags nus. Lister les
# deux doublerait chaque ligne sans lecteur pour ça.
#
# Usage : ./cbrain/changelog.sh        (écrit CHANGELOG.md à la racine du dépôt)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$ROOT"
OUT="CHANGELOG.md"

BRANCHE="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
if [ "$BRANCHE" = "fr" ]; then FILTRE="grep -- '-fr|'"; else FILTRE="grep -v -- '-fr|'"; fi

{
  echo "# Journal des versions"
  echo
  echo "Généré depuis les tags git annotés par \`cbrain/changelog.sh\` — ne pas éditer à la main."
  echo "Chaque entrée est le message attaché au tag au moment de la publication."
  echo
  if [ "$BRANCHE" = "fr" ]; then
    echo "Ceci est le journal de la branche française (tags \`-fr\`). La branche \`main\` publie les mêmes versions en anglais."
  else
    echo "La branche française publie les mêmes versions sous des tags \`-fr\` ; ils ne sont pas listés ici."
  fi
  echo

  git tag --sort=-creatordate --format='%(refname:short)|%(creatordate:short)|%(contents:subject)' \
  | eval "$FILTRE" \
  | while IFS='|' read -r tag date sujet; do
      [ -n "$tag" ] || continue
      # Les vieux tags portaient leur propre numéro dans le sujet ; on le retire
      # pour ne pas obtenir « ## v1.2.0 — v1.2.0 — … ».
      sujet="${sujet#"$tag" — }"
      echo "## $tag — $date"
      echo
      echo "$sujet"
      echo
    done
} > "$OUT"

echo "✅ $OUT réécrit — $(grep -c '^## ' "$OUT") versions"
