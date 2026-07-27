#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert. Source-available, see LICENSE.
#   Running it is allowed. Redistributing or rebuilding from it is not.
# uninstall.sh — undoes what install.sh did, and NOTHING else.
#
# Absolute rule: **your trunk is never deleted**. Your notes are your work, not a
# dependency of C Brain. The trunk loses its links to the engine; it keeps all of
# its content.
#
# Usage: ./uninstall.sh [--yes] [--purge-engine]
set -euo pipefail

TRUNK="$HOME/claude-brain"
CB="$HOME/.c-brain"
MANIFEST="$CB/manifest.txt"

ASSUME_YES=0; PURGE_ENGINE=0
for a in "$@"; do
  case "$a" in
    --yes) ASSUME_YES=1 ;;
    --purge-engine) PURGE_ENGINE=1 ;;
    *) echo "Unknown option: $a"; exit 1 ;;
  esac
done

say() { echo "  $*"; }

echo "🧠 C Brain — uninstall"
echo
echo "  Will be removed:"
echo "    · the C Brain hooks from ~/.claude/settings.json (the rest untouched)"
echo "    · the engine links inside $TRUNK (hooks, agents, capsule, planet, companion, tests)"
echo "    · ~/.local/bin/brain, the Desktop launcher, the launchd jobs"
echo
echo "  Will be KEPT:"
echo "    · $TRUNK and ALL your notes"
echo "    · the backups in $CB/backups/"
echo

if [ "$ASSUME_YES" = "0" ]; then
  printf "  Continue? [y/N] "
  read -r ans
  case "$ans" in y|Y|o|O) ;; *) echo "  Cancelled."; exit 0 ;; esac
fi

# ─── 1. Hooks ─────────────────────────────────────────────────────────────
echo
echo "▸ Hooks"
if [ -f "$HOME/.claude/settings.json" ] && [ -f "$CB/engine/merge_settings.py" ]; then
  python3 "$CB/engine/merge_settings.py" remove
else
  say "(settings.json or merge_settings.py missing — nothing to do)"
fi

# ─── 2. Scheduled jobs ────────────────────────────────────────────────────
echo
echo "▸ Scheduled jobs"
for t in resume machiniste; do
  p="$HOME/Library/LaunchAgents/com.claudebrain.$t.plist"
  if [ -f "$p" ]; then
    launchctl unload "$p" 2>/dev/null || true
    rm -f "$p"
    say "- com.claudebrain.$t"
  fi
done

# ─── 3. Links ─────────────────────────────────────────────────────────────
# We delete symlinks ONLY. If something has become a real folder, that is
# content — we leave it alone.
echo
echo "▸ Engine links"
for d in hooks agents capsule planet companion tests; do
  p="$TRUNK/$d"
  if [ -L "$p" ]; then rm -f "$p"; say "- $p"
  elif [ -e "$p" ]; then say "! $p is not a link — left in place (that is content)"; fi
done
for p in "$HOME/.claude/agents" "$HOME/.local/bin/brain"; do
  if [ -L "$p" ]; then rm -f "$p"; say "- $p"; fi
done

# ─── 4. Odds and ends ─────────────────────────────────────────────────────
echo
echo "▸ Odds and ends"
[ -f "$HOME/Desktop/Planete-C-Brain.command" ] && { rm -f "$HOME/Desktop/Planete-C-Brain.command"; say "- Desktop launcher"; }

# Deterministic rule: if the file is IDENTICAL to the engine's, it is ours →
# remove it. If it differs, it is the user's (pre-existing or since edited) →
# do not touch it.
SL="$HOME/.claude/statusline.py"
if [ -f "$SL" ]; then
  if [ -f "$CB/engine/statusline.py" ] && cmp -s "$SL" "$CB/engine/statusline.py"; then
    rm -f "$SL"; say "- ~/.claude/statusline.py (ours, byte for byte)"
  else
    say "! ~/.claude/statusline.py differs from ours — left in place (it is yours)"
  fi
fi

# ─── 5. Engine ────────────────────────────────────────────────────────────
echo
echo "▸ Engine"
if [ "$PURGE_ENGINE" = "1" ]; then
  rm -f "$CB/engine" "$MANIFEST" "$CB/VERSION"
  say "- engine references removed (the cloned repo itself stays on disk)"
else
  say "= $CB kept (backups + version). Use --purge-engine to wipe it."
fi

echo
echo "✅ Uninstalled. $TRUNK and your notes are intact."
echo "   Backups: $CB/backups/"
