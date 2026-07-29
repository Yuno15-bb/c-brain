#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# publish.sh — publier une version. Le SEUL chemin autorisé vers un `git push`.
#
# Pourquoi ce script existe : le contrôle de fuite a été lancé une fois en fin
# de pipe (`leakcheck.py | tail -1 && git push`). `tail` réussit toujours — le
# `&&` testait donc le mauvais code de retour, et la publication est partie
# alors que le contrôle était ROUGE. Le garde-fou existait, il était juste
# court-circuité par la façon de l'appeler.
#
# Ici, aucun pipe, aucun `&&` : le contrôle est un `if` explicite, et son échec
# arrête tout.
#
# Usage : ./publish.sh v1.2.3 "message du tag"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd -P)"
cd "$ROOT"

TAG="${1:-}"
MSG="${2:-}"
[ -n "$TAG" ] || { echo "Usage : ./publish.sh v1.2.3 \"message du tag\""; exit 1; }
# Le suffixe `-fr` est la convention de tag de la branche française (cf docs/translation.md).
# Sans lui dans le motif, la branche fr ne pouvait tout simplement pas être publiée.
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-z]+)?$ ]] || { echo "❌ Tag attendu au format vX.Y.Z (suffixe -fr accepté)"; exit 1; }
[ -n "$MSG" ] || { echo "❌ Un message de tag est requis."; exit 1; }

BRANCH="$(git rev-parse --abbrev-ref HEAD)"

echo "▸ Le paquet colle-t-il au Brain vivant ?"
if [ "$BRANCH" = "fr" ]; then
  if ! ./sync.sh --check >/dev/null 2>&1; then
    echo "❌ Le paquet a divergé. Lance ./sync.sh, relis le diff, puis recommence."
    exit 1
  fi
  echo "  ✅ à jour"
else
  # Seule `fr` est synchronisée depuis le Brain vivant ; `main` en est la
  # traduction. Lancer le contrôle de divergence ici comparerait des fichiers
  # anglais à une source française et échouerait toujours.
  echo "  ⤳ sauté sur \`$BRANCH\` (seule \`fr\` se synchronise depuis le Brain)"
fi

echo "▸ Arbre de travail propre ?"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "❌ Modifications non commitées. Commite d'abord."
  exit 1
fi
echo "  ✅ propre"

echo "▸ Contrôle de fuite (historique compris)"
if ! python3 leakcheck.py --history; then
  echo
  echo "⛔ FUITE — rien n'est publié."
  exit 1
fi

echo "▸ Tag déjà utilisé ?"
if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "❌ $TAG existe déjà. Prends le numéro suivant."
  echo "   Ne déplace JAMAIS un tag publié : chez les utilisateurs encore sur"
  echo "   une ancienne version, le fetch échoue et les mises à jour se bloquent."
  exit 1
fi

# Le manifeste du plugin porte une version explicite, et Claude Code ne propose
# AUCUNE mise à jour tant que cette chaîne ne change pas — pousser des commits
# ne fait rien du tout. Laisser ce geste à un humain, c'est la même classe de
# geste que traduire à la main, et on sait comment ça finit. Donc c'est le tag
# qui l'écrit, ici, une fois.
PLUGIN_MANIFEST=".claude-plugin/plugin.json"
if [ -f "$PLUGIN_MANIFEST" ]; then
  python3 - "$PLUGIN_MANIFEST" "${TAG#v}" <<'PYEOF'
import json, re, sys
path, version = sys.argv[1], sys.argv[2].removesuffix("-fr")
raw = open(path, encoding="utf-8").read()
# Substitution ciblée, pas un re-dump : json.dump reformaterait tout le fichier
# et transformerait chaque version en un diff que personne ne peut relire.
new = re.sub(r'("version"\s*:\s*)"[^"]*"', lambda m: m.group(1) + '"%s"' % version, raw, count=1)
if new != raw:
    open(path, "w", encoding="utf-8").write(new)
    print("  version de plugin.json → %s" % version)
else:
    print("  plugin.json déjà en %s" % version)
PYEOF
  if ! git diff --quiet -- "$PLUGIN_MANIFEST"; then
    git add "$PLUGIN_MANIFEST"
    git commit -q -m "Manifeste du plugin : version $TAG"
    echo "  bump de version committé"
  fi
fi

# La branche COURANTE, jamais `main` en dur — BRANCH est déjà résolu en tête de
# ce script. Avec `main` codé en dur, une publication depuis `fr` poussait le
# tag et… la branche main (déjà à jour) : les commits français ne partaient
# jamais. Le tag masquait le trou, puisqu'il porte les objets — `brain update`
# marchait, mais la branche `fr` distante restait figée.
git tag -a "$TAG" -m "$MSG"
git push origin "$BRANCH" "$TAG"
echo
echo "✅ $TAG publiée sur $BRANCH."
