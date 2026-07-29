#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# sync.sh — ~/claude-brain (the author's living Brain, source of truth) → C Brain repo.
#
# PRINCIPLE: allowlist. What is not listed here does not ship, full stop.
# A denylist would let things through by default; one omission = a PII leak.
#
# ONE WAY: this script READS ~/claude-brain and never writes to it.
#
# Usage:
#   ./sync.sh            actual copy
#   ./sync.sh --check    writes nothing, reports drift (exit 1 if drifted)
set -euo pipefail

SRC="${CBRAIN_SRC:-$HOME/claude-brain}"
DEST="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="${CBRAIN_CLAUDE_DIR:-$HOME/.claude}"

MODE="copy"
[ "${1:-}" = "--check" ] && MODE="check"

# --itemize-changes in BOTH modes: the report must say what moved,
# not only what would have moved.
RSYNC_FLAGS=(-a --delete --itemize-changes)
[ "$MODE" = "check" ] && RSYNC_FLAGS+=(--dry-run)

[ -d "$SRC" ] || { echo "❌ Source not found: $SRC"; exit 1; }
[ "$SRC" = "$DEST" ] && { echo "❌ Source and destination are the same."; exit 1; }

# The source Brain is in French. Syncing straight onto the English branch would
# silently overwrite every translated file with its French original — and the
# damage would only surface for readers, never for any test.
# `fr` is the sync branch; `main` is derived from it. See docs/translation.md.
BRANCH="$(git -C "$DEST" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
if [ "$BRANCH" = "main" ] && [ "${CBRAIN_ALLOW_SYNC_ON_MAIN:-0}" != "1" ]; then
  echo "❌ ./sync.sh runs on the \`fr\` branch, not on \`main\`."
  echo "   main holds the English translation; a sync would overwrite it with French."
  echo "   Workflow:  git checkout fr && ./sync.sh   then port the diff onto main."
  echo "   (CBRAIN_ALLOW_SYNC_ON_MAIN=1 forces it, if you know why.)"
  exit 1
fi

# --- SOURCE FINGERPRINT ------------------------------------------------
# `--check` CANNOT compare the package to the source: generalize.py rewrites
# the files right after the copy, so they differ by construction and the
# comparison would be red forever.
#
# The right question is "has the SOURCE moved since the last copy?".
# We answer it with a fingerprint of the source files taken at sync time.
MANIFEST="$DEST/.sync-manifest"

source_fingerprint() {
  {
    shasum -a 256 "$SRC/brain" "$CLAUDE_DIR/statusline.py" 2>/dev/null
    find "$SRC/hooks" "$SRC/agents" "$SRC/capsule" "$SRC/planet" \
         "$SRC/companion" "$SRC/tests" -type f \
         ! -path "*/node_modules/*" ! -name "*.pyc" ! -name ".DS_Store" \
         ! -name "graph.json" ! -name "desktop_sync.py" \
         ! -name "com.dylan.desktop-sync.plist.template" \
         ! -name "com.claudebrain.resume.plist" \
         ! -path "*/capsule/assets/*" 2>/dev/null \
      | sort | xargs shasum -a 256 2>/dev/null
  } | sed "s|$SRC/||; s|$CLAUDE_DIR/||" | sort -k2
}

if [ "$MODE" = "check" ]; then
  echo "🔄 C Brain — has the living Brain moved since the last copy?"
  if [ ! -f "$MANIFEST" ]; then
    echo "  ⚠️  no fingerprint on record — run ./sync.sh once."
    exit 1
  fi
  DIFF="$(diff <(cat "$MANIFEST") <(source_fingerprint) || true)"
  if [ -z "$DIFF" ]; then
    echo "  ✅ unchanged — the package is up to date."
    exit 0
  fi
  echo "  ⚠️  the source has changed:"
  printf '%s\n' "$DIFF" | grep -E '^[<>]' | awk '{print "      " $1 " " $3}' | sort -u | head -20
  echo
  echo "  → ./sync.sh to carry the changes over, then read the git diff."
  exit 1
fi

DIVERGED=0
report() {  # report <label> <rsync output>
  if [ -n "$2" ]; then
    DIVERGED=1
    echo "  ~ $1"
    printf '%s\n' "$2" | sed 's/^/      /'
  else
    echo "  = $1"
  fi
}

sync_dir() {  # sync_dir <subpath> <exclusions...>
  local rel="$1"; shift
  local excludes=()
  for e in "$@"; do excludes+=(--exclude "$e"); done
  mkdir -p "$DEST/$rel"
  local out
  # ${a[@]+"${a[@]}"}: bash 3.2 (the macOS one) treats an empty array as an
  # unset variable under `set -u`. This form guards against that.
  out="$(rsync "${RSYNC_FLAGS[@]}" ${excludes[@]+"${excludes[@]}"} \
        "$SRC/$rel/" "$DEST/$rel/" 2>/dev/null || true)"
  report "$rel/" "$out"
}

sync_file() {  # sync_file <absolute source> <relative destination>
  # NO rsync here. macOS 27 ships openrsync, which on a SINGLE file under
  # --dry-run always reports a transfer, even on identical content → a
  # permanent false drift in --check mode. `cmp` is deterministic.
  local src="$1" dst="$DEST/$2"
  if [ ! -f "$src" ]; then
    DIVERGED=1; echo "  ! $2 — source missing ($src)"; return
  fi
  if cmp -s "$src" "$dst" 2>/dev/null; then
    report "$2" ""
  else
    report "$2" ">f  content differs"
    # `[ … ] && { … }` as the LAST statement returns 1 when the test is false:
    # under `set -e` that killed the script on the 1st drifting file in --check
    # mode, with NO message — the rest looked up to date while nothing was scanned.
    # The explicit `if/fi` + `return 0` closes the hole.
    if [ "$MODE" = "copy" ]; then
      mkdir -p "$(dirname "$dst")"
      cp -p "$src" "$dst"
    fi
  fi
  return 0
}

echo "🔄 C Brain — syncing from $SRC"
[ "$MODE" = "check" ] && echo "   (--check mode: nothing is written)"
echo

# --- 1. CLI ---------------------------------------------------------------
sync_file "$SRC/brain" "brain"

# --- 2. Hooks -------------------------------------------------------------
# EXCLUDED: desktop_sync.py + its plist (backs up the author's Desktop to THEIR
# own GitHub — personal, and destructive on someone else's machine), and the
# non-template .plist carrying a hardcoded home (only the .template ships).
#
# ALSO EXCLUDED: hooks.json. It exists ONLY in the package — it is the Claude
# Code plugin's hook manifest, not a file of the living Brain. rsync runs with
# --delete: without this exclusion the very next sync would erase it, and the
# plugin would stop recording ANYTHING without a single error.
sync_dir hooks \
  'desktop_sync.py' \
  'com.dylan.desktop-sync.plist.template' \
  'com.claudebrain.resume.plist' \
  'hooks.json' \
  '__pycache__' '*.pyc'

# --- 3. Agents ------------------------------------------------------------
sync_dir agents

# --- 4. Capsule -----------------------------------------------------------
# EXCLUDED: node_modules (282 MB, reinstalled by install.sh) and assets/ (7.4 MB
# of DEAD weight — verified 2026-07-26: the sprite is inline in index.html,
# no file under assets/ is referenced by the code).
sync_dir capsule 'node_modules' 'assets'

# --- 5. Planet -----------------------------------------------------------
# EXCLUDED: graph.json — 1.4 MB holding the FULL TEXT of the notes, client
# names included. Regenerated on every launch by graph_export.py.
sync_dir planet 'graph.json'

# --- 6. Companion ---------------------------------------------------------
sync_dir companion '__pycache__' '*.pyc'

# --- 7. Tests --------------------------------------------------------------
# EXCLUDED: the tests that belong to the PACKAGE (plugin manifests, English
# only). They have no counterpart in the living Brain; --delete would take them.
sync_dir tests 'plugin_manifest.py' 'english_only.py' '__pycache__' '*.pyc'

# --- 8. Status line (lives in ~/.claude, not in the trunk) ----------------
sync_file "$CLAUDE_DIR/statusline.py" "statusline.py"

echo
# --- 9. Generalization ----------------------------------------------------
# CHAINED, never optional: the copy that just happened REINTRODUCED the
# author's name, their clients and their projects. A sync without
# generalization leaves the package leaking, and nothing would flag it
# before the leak check.
echo "───"
python3 "$DEST/generalize.py"

# Fingerprint written AFTER generalization: it attests "this is the state of the
# source this package reflects". Writing it earlier would make the package look
# up to date when generalization had just failed.
source_fingerprint > "$MANIFEST"

echo
echo "✅ Synced and generalized. Final check: python3 leakcheck.py"
