#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# install.sh — installs C Brain. The SINGLE entry point.
#
# Three promises, kept by construction:
#   · IDEMPOTENT — re-running breaks nothing and duplicates nothing.
#   · NON-DESTRUCTIVE — anything already there is backed up before being touched.
#   · REVERSIBLE — every action is logged; ./uninstall.sh undoes them.
#
# Installed layout:
#   ~/.c-brain/engine  → link to THIS repo (the ENGINE: code, nothing else)
#   ~/.c-brain/trunk     → YOUR trunk (your notes). Never overwritten, never updated.
#
# Usage: ./install.sh [--no-launchd] [--no-capsule] [--no-shortcut] [--dry-run]
set -euo pipefail

ENGINE="$(cd "$(dirname "$0")" && pwd -P)"
TRUNK="$HOME/.c-brain/trunk"
CB="$HOME/.c-brain"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUPS="$CB/backups/$TS"
MANIFEST="$CB/manifest.txt"

DO_LAUNCHD=1; DO_CAPSULE=1; DO_SHORTCUT=1; DRY=0
for a in "$@"; do
  case "$a" in
    --no-launchd) DO_LAUNCHD=0 ;;
    --no-capsule) DO_CAPSULE=0 ;;
    --no-shortcut) DO_SHORTCUT=0 ;;
    --dry-run)    DRY=1 ;;
    *) echo "Unknown option: $a"; exit 1 ;;
  esac
done

say()  { echo "  $*"; }
step() { echo; echo "▸ $*"; }
warn() { echo "  ⚠️  $*"; }
die()  { echo; echo "❌ $*"; exit 1; }

# Logs what we create, so uninstall knows what to undo.
note() { [ "$DRY" = "1" ] || { mkdir -p "$CB"; echo "$1|$2" >> "$MANIFEST"; }; }

# Back up before overwriting. User content never disappears.
save() {
  [ -e "$1" ] || return 0
  [ "$DRY" = "1" ] && { say "(dry-run) would back up $1"; return 0; }
  mkdir -p "$BACKUPS"
  cp -R "$1" "$BACKUPS/$(basename "$1")" 2>/dev/null || true
  say "backed up: $1 → $BACKUPS/"
}

run() { [ "$DRY" = "1" ] && { say "(dry-run) $*"; return 0; }; "$@"; }

# Places a symlink idempotently: already correct → nothing is touched.
link() {  # link <target> <link>
  local target="$1" path="$2"
  if [ -L "$path" ] && [ "$(readlink "$path")" = "$target" ]; then
    say "= $path (already linked)"; return 0
  fi
  if [ -e "$path" ] || [ -L "$path" ]; then
    save "$path"
    run rm -rf "$path"
  fi
  run mkdir -p "$(dirname "$path")"
  run ln -s "$target" "$path"
  note link "$path"
  say "+ $path → $target"
}

echo "🧠 C Brain — installation"
echo "   engine : $ENGINE"
echo "   trunk  : $TRUNK"
[ "$DRY" = "1" ] && echo "   (DRY-RUN: nothing will be written)"

# ─── 0. Prerequisites ────────────────────────────────────────────────────────
step "Prerequisites"
[ "$(uname)" = "Darwin" ] || die "C Brain targets macOS (launchd, Electron, \`open\`)."
command -v python3 >/dev/null || die "python3 is required (it runs every hook)."
say "python3 $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"
command -v git >/dev/null || warn "git missing — \`brain update\` will not be able to pull updates."

HAS_CLAUDE_CODE=0
[ -d "$HOME/.claude" ] && HAS_CLAUDE_CODE=1
if [ "$HAS_CLAUDE_CODE" = "0" ]; then
  warn "~/.claude missing: Claude Code does not appear to be installed."
  warn "C Brain will still install, but WITHOUT the closed loop:"
  warn "the hooks (recall, archiving, maintenance) are specific to Claude Code."
  warn "You keep the \`brain\` CLI, the agents, the planet and the capsule."
fi

# ─── 1. C Brain root ────────────────────────────────────────────────────
step "C Brain root (~/.c-brain)"
run mkdir -p "$CB"
link "$ENGINE" "$CB/engine"
[ "$DRY" = "1" ] || { git -C "$ENGINE" describe --tags --always 2>/dev/null > "$CB/VERSION" || echo "untagged" > "$CB/VERSION"; }
say "version: $(cat "$CB/VERSION" 2>/dev/null || echo '?')"

# ─── 2. The trunk ──────────────────────────────────────────────────────────
step "Trunk (~/.c-brain/trunk)"
if [ -d "$TRUNK" ]; then
  # A trunk exists. If it holds a REAL hooks/ folder (not a link), it is
  # a previous standalone install: we refuse to demolish it silently.
  if [ -d "$TRUNK/hooks" ] && [ ! -L "$TRUNK/hooks" ]; then
    die "$TRUNK/hooks is a REAL folder, not a link.
   There is already an old-style Brain installed here. I will not replace it on my own:
   its files might be yours. Back it up, then re-run:
     mv $TRUNK $TRUNK.before-c-brain && ./install.sh"
  fi
  say "= existing trunk kept (your notes are untouched)"
else
  run mkdir -p "$TRUNK"
  run cp -R "$ENGINE/skeleton/." "$TRUNK/"
  note dir "$TRUNK"
  say "+ trunk created from skeleton/ (empty, ready to grow)"
fi
run mkdir -p "$TRUNK/state" "$TRUNK/sessions/archive"

# ─── 3. The engine, linked into the trunk ────────────────────────────────────
step "Engine linked into the trunk"
for d in hooks agents capsule planet companion tests; do
  link "$CB/engine/$d" "$TRUNK/$d"
done

# ─── 4. The `brain` command ───────────────────────────────────────────────
step "The \`brain\` command"
link "$CB/engine/brain" "$HOME/.local/bin/brain"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) say "~/.local/bin is on PATH" ;;
  *) warn "~/.local/bin is NOT on your PATH. Add to your ~/.zshrc:"
     warn "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# ─── 5. Agents visible to Claude Code ───────────────────────────────────
# Trap #1: without this link the agents exist but Claude Code cannot see
# them. No error, just an autonomous loop spinning on nothing.
step "Agents visible to the CLI agent"
if [ "$HAS_CLAUDE_CODE" = "1" ]; then
  link "$TRUNK/agents" "$HOME/.claude/agents"
else
  say "(skipped — ~/.claude missing)"
fi

# ─── 6. Hooks + status line ────────────────────────────────────────────────
step "Wiring the hooks"
if [ "$HAS_CLAUDE_CODE" = "1" ]; then
  if [ "$DRY" = "1" ]; then say "(dry-run) would merge ~/.claude/settings.json"
  else
    # No `save` here: merge_settings.py backs up ONLY when it actually writes.
    # Backing up every pass would stack a useless copy on every re-run.
    python3 "$ENGINE/merge_settings.py" install
    note settings "$HOME/.claude/settings.json"
  fi
  if [ -f "$ENGINE/statusline.py" ]; then
    save "$HOME/.claude/statusline.py"
    run cp "$ENGINE/statusline.py" "$HOME/.claude/statusline.py"
    note file "$HOME/.claude/statusline.py"
    say "+ status line installed"
  fi
else
  say "(skipped — no Claude Code: C Brain will work on demand)"
fi

# ─── 7. Capsule ───────────────────────────────────────────────────────────
step "Capsule (Electron window)"
capsule_ok() {  # does Electron ACTUALLY respond?
  local bin="$ENGINE/capsule/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
  [ -x "$bin" ] && "$bin" --version >/dev/null 2>&1
}

if [ "$DO_CAPSULE" = "0" ]; then say "(skipped — --no-capsule)"
elif ! command -v npm >/dev/null; then warn "npm missing — capsule not installed (everything else works)."
elif [ "$DRY" = "1" ]; then say "(dry-run) would install the capsule dependencies"
elif capsule_ok; then say "= capsule already working"
else
  say "npm install (Electron, ~1 min)…"
  npm --prefix "$ENGINE/capsule" install --silent >/dev/null 2>&1 || true
  # `npm install` exits SUCCESSFULLY even when the Electron binary was never
  # extracted (archive truncated by @electron/get — a trap already hit). Trusting
  # the exit code would report a capsule as installed while it cannot start.
  # So we check the binary itself.
  if capsule_ok; then
    say "+ capsule working ($("$ENGINE/capsule/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" --version 2>/dev/null))"
  else
    warn "npm returned, but the Electron binary does not respond."
    warn "This is a known flaw in its downloader, not in C Brain. Remedy:"
    warn "  rm -rf $ENGINE/capsule/node_modules/electron && npm --prefix $ENGINE/capsule install"
    warn "Everything else in C Brain works without the capsule."
  fi
fi

# ─── 8. Scheduled jobs ─────────────────────────────────────────────────
step "Scheduled jobs (launchd)"
if [ "$DO_LAUNCHD" = "0" ]; then say "(skipped — --no-launchd)"
else
  run mkdir -p "$HOME/Library/LaunchAgents"
  for t in resume machiniste; do
    tpl="$ENGINE/hooks/com.claudebrain.$t.plist.template"
    [ -f "$tpl" ] || continue
    out="$HOME/Library/LaunchAgents/com.claudebrain.$t.plist"
    if [ "$DRY" = "1" ]; then say "(dry-run) would generate $out"; continue; fi
    # __HOME__ substituted here: a hardcoded path in a .plist is THE bug that
    # silently breaks an install on another machine.
    sed "s|__HOME__|$HOME|g" "$tpl" > "$out"
    note file "$out"
    launchctl unload "$out" 2>/dev/null || true
    launchctl load "$out" 2>/dev/null && say "+ com.claudebrain.$t loaded" \
      || warn "com.claudebrain.$t generated but not loaded (launchctl refused)"
  done
fi

# ─── 9. Planet launcher ─────────────────────────────────────────────
step "Planet launcher (Desktop)"
CMD="$HOME/Desktop/Planete-C-Brain.command"
if [ "$DRY" = "1" ]; then say "(dry-run) would create $CMD"
elif [ -d "$HOME/Desktop" ]; then
  printf '#!/bin/bash\nexport PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"\nexec "%s/planet/launch.sh"\n' "$TRUNK" > "$CMD"
  chmod +x "$CMD"
  note file "$CMD"
  say "+ $CMD (double-click → globe on localhost:8765)"
else
  warn "~/Desktop not found — launcher not created. The planet stays reachable at:"
  warn "  $TRUNK/planet/launch.sh"
fi

# ─── 10. Making the trunk findable ────────────────────────────────────────
# The trunk lives at ~/.c-brain/trunk. The leading dot keeps the plumbing out
# of the way — and hides the one part of this that is YOURS. A new user gets a
# memory they cannot see, in a folder Finder refuses to show. So we put a
# visible door on it.
#
# NOT the Finder sidebar: it is stored in a binary .sfl4 plist with no
# supported API, and the only way in is a third-party binary. Adding a
# dependency to place an icon is not a trade worth making — dragging the folder
# into Favourites takes the user two seconds, and we say so below.
step "Making your memory findable"
SHORTCUT="$HOME/C Brain"
if [ "$DO_SHORTCUT" = "0" ]; then say "(skipped — --no-shortcut)"
elif [ "$DRY" = "1" ]; then say "(dry-run) would create $SHORTCUT and tag the trunk"
else
  if [ -L "$SHORTCUT" ] && [ "$(readlink "$SHORTCUT")" = "$TRUNK" ]; then
    say "= $SHORTCUT (already there)"
  elif [ -e "$SHORTCUT" ]; then
    warn "$SHORTCUT exists and is not our shortcut — left alone"
  else
    ln -s "$TRUNK" "$SHORTCUT"
    note shortcut "$SHORTCUT"
    say "+ $SHORTCUT → your notes, visible in Finder"
  fi
  # A Finder tag, so the folder is recognisable at a glance among thirty others.
  python3 - "$TRUNK" <<'PY' 2>/dev/null || true
import plistlib, subprocess, sys
blob = plistlib.dumps(["C Brain\n6"], fmt=plistlib.FMT_BINARY)   # 6 = red
subprocess.run(["xattr", "-w", "-x", "com.apple.metadata:_kMDItemUserTags",
                blob.hex(), sys.argv[1]], check=True)
PY
  say "  Tip: drag it into the Finder sidebar once — it stays there."
fi

# ─── 11. Verification ─────────────────────────────────────────────────────
step "Verification"
if [ "$DRY" = "1" ]; then say "(dry-run) would run the selftest"
else
  if bash "$TRUNK/hooks/selftest.sh" >/tmp/c-brain-selftest.log 2>&1; then
    say "✅ selftest OK — every hook healthy"
  else
    warn "selftest failed — details: /tmp/c-brain-selftest.log"
    tail -5 /tmp/c-brain-selftest.log | sed 's/^/     /'
  fi
  python3 "$TRUNK/hooks/brain_doctor.py" --quiet >/dev/null 2>&1 \
    && say "✅ doctor — tree consistent" || say "ℹ️  doctor flags a few things to look at (\`brain doctor\`)"
fi

echo
echo "✅ C Brain installed."
echo
# Offered FIRST, not as a footnote: an empty trunk on first launch shows nothing
# of what the tool can do. That is the screen where people give up.
echo "   ▸ Your trunk is empty. To see it working:"
echo "       brain demo                place 3 example notes"
echo "       brain recall cache        what recall finds"
echo "       brain demo --remove       take them away, leaving no trace"
echo
echo "   brain status     where the trunk stands"
echo "   brain recall <q> search your memory"
echo "   brain doctor     tree health"
echo "   brain selftest   re-check the installation"
echo
[ "$HAS_CLAUDE_CODE" = "1" ] \
  && echo "   Restart your CLI session for the hooks to take effect." \
  || echo "   Without Claude Code: no closed loop, but the whole CLI is there."
echo "   Uninstall: $ENGINE/uninstall.sh"
