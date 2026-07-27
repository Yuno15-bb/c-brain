#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# update.sh — updates the ENGINE. Never touches the TRUNK.
#
# What it does:
#   1. fetches the published tags,
#   2. switches to the newest one (never to `main`: a working branch has no
#      business installing itself on someone's machine),
#   3. runs migrations that have not been applied yet,
#   4. replays install.sh (idempotent) to propagate what is new,
#   5. verifies, and offers a rollback if it breaks.
#
# What it does NOT do: read, modify or send a single one of your notes.
#
# Usage: brain update [--check] [--rollback] [--force]
set -euo pipefail

CB="$HOME/.c-brain"
ENGINE="$(cd "$CB/engine" 2>/dev/null && pwd -P)" || { echo "❌ Engine not found ($CB/engine)."; exit 1; }
STATE="$CB/state"
APPLIED="$STATE/applied-migrations.txt"
PREVIOUS="$STATE/previous-version"
mkdir -p "$STATE"

MODE="update"
for a in "$@"; do
  case "$a" in
    --check) MODE="check" ;;
    --rollback) MODE="rollback" ;;
    --force) MODE="force" ;;
    *) echo "Usage: brain update [--check] [--rollback] [--force]"; exit 1 ;;
  esac
done

say()  { echo "  $*"; }
warn() { echo "  ⚠️  $*"; }

command -v git >/dev/null || { echo "❌ git is required for updates."; exit 1; }
git -C "$ENGINE" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "❌ The engine is not a git repo — it was copied, not cloned."
  echo "   Re-clone it to receive updates."
  exit 1; }

current() { git -C "$ENGINE" describe --tags --exact-match 2>/dev/null || git -C "$ENGINE" rev-parse --short HEAD; }

# The newest tag by version order, not alphabetical order:
# without `-V`, v10 would sort before v9.
latest_tag() { git -C "$ENGINE" tag -l 'v*' | sort -V | tail -1; }

# ─── Rollback ───────────────────────────────────────────────────────
if [ "$MODE" = "rollback" ]; then
  [ -f "$PREVIOUS" ] || { echo "❌ No previous version on record."; exit 1; }
  target="$(cat "$PREVIOUS")"
  echo "⏪ Rolling back to $target"
  git -C "$ENGINE" checkout -q "$target"
  bash "$ENGINE/install.sh" >/dev/null 2>&1 || warn "install.sh reported a problem"
  echo "✅ Back on $target. Your notes did not move."
  exit 0
fi

# ─── Remote state ─────────────────────────────────────────────────────────
CUR="$(current)"
echo "🔄 C Brain — installed version: $CUR"

# --force: the remote is authoritative on tags. The user never creates any —
# without this, a single tag republished by the author makes the fetch fail
# ("would clobber existing tag") and BLOCKS every subsequent update, while
# reporting "no network". A silent, permanent failure.
if ! FETCH_ERR="$(git -C "$ENGINE" fetch --tags --force 2>&1)"; then
  # Offline, unreachable repo, moved remote tag… none of it is blocking, but
  # we do not claim "no network" when the cause is something else: a wrong
  # diagnosis costs more than a slightly longer message.
  say "could not reach the remote versions — will retry later."
  [ -n "$FETCH_ERR" ] && printf '%s\n' "$FETCH_ERR" | head -3 | sed 's/^/     /'
  exit 0
fi

NEW="$(latest_tag)"
[ -n "$NEW" ] || { say "no version published yet."; exit 0; }

if [ "$CUR" = "$NEW" ] && [ "$MODE" != "force" ]; then
  say "already up to date ($NEW)."
  exit 0
fi

echo "  new version available: $NEW"
if [ "$MODE" = "check" ]; then
  echo "  → \`brain update\` to install it."
  exit 10   # 10 = "an update exists", readable by a script
fi

# ─── Applying ──────────────────────────────────────────────────────────
# A hand-edited engine is somebody's work. We do not overwrite it.
if ! git -C "$ENGINE" diff --quiet || ! git -C "$ENGINE" diff --cached --quiet; then
  echo "❌ The engine has uncommitted local changes."
  echo "   Put them away (git stash / git commit) before updating."
  exit 1
fi

echo "$CUR" > "$PREVIOUS"
git -C "$ENGINE" checkout -q "$NEW"
say "engine now on $NEW"

# ─── Migrations ───────────────────────────────────────────────────────────
# Numbered, run exactly once, never destructive to content.
touch "$APPLIED"
for m in "$ENGINE"/cbrain/migrations/*.sh; do
  [ -e "$m" ] || continue
  name="$(basename "$m")"
  grep -qxF "$name" "$APPLIED" && continue
  # ${name} with braces, mandatory: glued to a UTF-8 character, bash on macOS
  # swallows it into the variable NAME ("name… : unbound variable") and kills
  # the update mid-flight, right after the checkout.
  say "migration ${name}…"
  if bash "$m"; then
    echo "$name" >> "$APPLIED"
  else
    warn "migration $name failed — stopping. \`brain update --rollback\` to go back."
    exit 1
  fi
done

# ─── Reinstall + verification ────────────────────────────────────────
say "reinstalling (idempotent)…"
bash "$ENGINE/install.sh" >/tmp/c-brain-update.log 2>&1 || warn "install.sh reported a problem (/tmp/c-brain-update.log)"

if bash "$HOME/.c-brain/trunk/hooks/selftest.sh" >/tmp/c-brain-update-selftest.log 2>&1; then
  echo
  echo "✅ Updated to $NEW — selftest green. Your notes were not touched."
else
  echo
  warn "selftest FAILED after update (/tmp/c-brain-update-selftest.log)"
  warn "Rollback advised:  brain update --rollback"
  exit 1
fi
