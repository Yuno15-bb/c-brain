#!/usr/bin/env bash
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

echo "▸ Le paquet colle-t-il au Brain vivant ?"
if ! ./sync.sh --check >/dev/null 2>&1; then
  echo "❌ Le paquet a divergé. Lance ./sync.sh, relis le diff, puis recommence."
  exit 1
fi
echo "  ✅ à jour"

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

git tag -a "$TAG" -m "$MSG"
git push origin main "$TAG"
echo
echo "✅ $TAG publiée."
