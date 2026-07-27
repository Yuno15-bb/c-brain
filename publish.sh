#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert. Source-available, see LICENSE.
#   Running it is allowed. Redistributing or rebuilding from it is not.
# publish.sh — publish a version. The ONLY sanctioned path to a `git push`.
#
# Why this script exists: the leak check was once run at the end of a pipe
# (`leakcheck.py | tail -1 && git push`). `tail` always succeeds — so the `&&`
# tested the wrong exit code, and a push went out while the check was RED. The
# guard existed; it was simply short-circuited by how it was called.
#
# Here there is no pipe and no `&&`: the check is an explicit `if`, and its
# failure stops everything.
#
# Usage: ./publish.sh v1.2.3 "tag message"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd -P)"
cd "$ROOT"

TAG="${1:-}"
MSG="${2:-}"
[ -n "$TAG" ] || { echo "Usage: ./publish.sh v1.2.3 \"tag message\""; exit 1; }
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-z]+)?$ ]] || { echo "❌ Expected a vX.Y.Z tag"; exit 1; }
[ -n "$MSG" ] || { echo "❌ A tag message is required."; exit 1; }

BRANCH="$(git rev-parse --abbrev-ref HEAD)"

echo "▸ Does the package still match the living Brain?"
if [ "$BRANCH" = "fr" ]; then
  if ! ./sync.sh --check >/dev/null 2>&1; then
    echo "❌ The package has drifted. Run ./sync.sh, read the diff, then retry."
    exit 1
  fi
  echo "  ✅ up to date"
else
  # Only `fr` is synced from the living Brain; `main` is translated from `fr`.
  # Running the drift check here would compare English files against a French
  # source and always fail.
  echo "  ⤳ skipped on \`$BRANCH\` (only \`fr\` syncs from the Brain)"
fi

echo "▸ Is the working tree clean?"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "❌ Uncommitted changes. Commit first."
  exit 1
fi
echo "  ✅ clean"

echo "▸ Leak check (history included)"
if ! python3 leakcheck.py --history; then
  echo
  echo "⛔ LEAK — nothing is published."
  exit 1
fi

echo "▸ Is the tag already taken?"
if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "❌ $TAG already exists. Take the next number."
  echo "   NEVER move a published tag: for users still on an older version the"
  echo "   fetch fails and updates lock up for good."
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git tag -a "$TAG" -m "$MSG"
git push origin "$BRANCH" "$TAG"
echo
echo "✅ $TAG published on $BRANCH."
