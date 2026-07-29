#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_tag_family.sh — the update path must never change the user's language.
#
# WHY THIS TEST EXISTS. Tags are not scoped to a branch, so `git tag -l 'v*'`
# returns the English and French families at once — and `sort -V` places
# `v1.18.0-fr` AFTER `v1.18.0`. Taking the global maximum moved an ENGLISH
# installation onto the FRENCH tree the moment the French branch caught up,
# with no error whatsoever: the tag exists, the checkout succeeds, and the user
# simply finds their tool speaking another language.
#
# It stayed invisible for as long as `fr` lagged behind. That is exactly the
# kind of bug a test has to hold down, because nothing else will report it.
#
# The test builds a throwaway repository with the real topology — two branches
# that diverge, each carrying its own tag family — and asserts that an install
# of each family is offered its OWN newest version.
#
# Run: bash tests/update_tag_family.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FAILS=0

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

git init -q -b main "$T/engine"
cd "$T/engine"
# NOT a plausible-looking address: leakcheck scans this repository for e-mail
# patterns, and a placeholder that matches one turns the guard red on a file
# that leaks nothing. git accepts any string here.
git config user.email cbrain-test
git config user.name cbrain-test

echo base > f && git add f && git commit -qm base
git checkout -q -b fr && echo fr1 > f && git commit -qam fr1 && git tag -a v1.17.0-fr -m x
git checkout -q main && echo en1 > f && git commit -qam en1 && git tag -a v1.17.0 -m x
echo en2 > f && git commit -qam en2 && git tag -a v1.18.0 -m x
git checkout -q fr && echo fr2 > f && git commit -qam fr2 && git tag -a v1.18.0-fr -m x

# The bug, demonstrated: the global maximum is the FRENCH tag.
naive="$(git tag -l 'v*' | sort -V | tail -1)"
[ "$naive" = "v1.18.0-fr" ] || {
  echo "⚠️  the premise no longer holds: global max is '$naive', not v1.18.0-fr"
}

# Load the real functions from update.sh rather than re-implementing them —
# a copy in the test would keep passing after the shipped code was broken.
ENGINE="$T/engine"
eval "$(sed -n '/^family() {/,/^}/p;/^latest_tag() {/,/^}/p' "$ROOT/cbrain/update.sh")"

check() {  # check <label> <checkout> <expected>
  git -C "$ENGINE" checkout -q "$2"
  local got; got="$(latest_tag)"
  if [ "$got" = "$3" ]; then
    echo "  ✅ $1 → $got"
  else
    echo "  ❌ $1 → got '$got', expected '$3'"
    FAILS=$((FAILS + 1))
  fi
}

echo "▸ each installation is offered its own family"
check "English install (on v1.17.0)"  v1.17.0     v1.18.0
check "French install (on v1.17.0-fr)" v1.17.0-fr v1.18.0-fr
check "fresh clone of branch fr"       fr         v1.18.0-fr
check "fresh clone of branch main"     main       v1.18.0

echo "▸ a repository with no tag at all does not crash"
git -C "$ENGINE" tag -d $(git -C "$ENGINE" tag) >/dev/null 2>&1
if out="$(latest_tag)" && [ -z "$out" ]; then
  echo "  ✅ empty result, exit 0"
else
  echo "  ❌ crashed or returned '$out' with no tags present"
  FAILS=$((FAILS + 1))
fi

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ the update path keeps every installation in its own language"
  exit 0
fi
echo "❌ $FAILS failure(s) — an update could switch a user's language"
exit 1
