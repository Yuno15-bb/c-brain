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
# Usage: brain update [--check] [--rollback] [--force] [--auto]
set -euo pipefail

CB="$HOME/.c-brain"
ENGINE="$(cd "$CB/engine" 2>/dev/null && pwd -P)" || { echo "❌ Engine not found ($CB/engine)."; exit 1; }
STATE="$CB/state"
APPLIED="$STATE/applied-migrations.txt"
PREVIOUS="$STATE/previous-version"
mkdir -p "$STATE"

# ─── Automatic updates ────────────────────────────────────────────────────
# State files shared with `cbrain/check_update.py`, which triggers `--auto` at
# session start.
AUTO=0
LOCK="$STATE/auto-update.lock"            # a directory: `mkdir` is atomic
JOURNAL="$STATE/auto-update.log"
RESULT="$STATE/last-auto-update"          # read, shown, then deleted by the hook
AUTO_OFF="$STATE/auto-update-off"

MODE="update"
for a in "$@"; do
  case "$a" in
    --check) MODE="check" ;;
    --rollback) MODE="rollback" ;;
    --force) MODE="force" ;;
    --auto) AUTO=1; MODE="update" ;;
    --auto-off) MODE="auto-off" ;;
    --auto-on)  MODE="auto-on" ;;
    *) echo "Usage: brain update [--check] [--rollback] [--force] [--auto|--auto-off|--auto-on]"; exit 1 ;;
  esac
done

# ─── The switch ───────────────────────────────────────────────────────────
# It comes BEFORE everything else, on purpose: turning automatic updates off
# must not depend on the network, on the state of the repo, or on anything that
# can fail. It is the one command in this file that has to work when nothing
# else does.
if [ "$MODE" = "auto-off" ]; then
  mkdir -p "$STATE"; : > "$AUTO_OFF"
  echo "✅ Automatic updates are OFF."
  echo "   Session start will report new versions without installing them."
  echo "   To turn them back on:  brain update --auto-on"
  exit 0
fi
if [ "$MODE" = "auto-on" ]; then
  rm -f "$AUTO_OFF"
  echo "✅ Automatic updates are back ON."
  echo "   Every session start will install the latest published version."
  exit 0
fi

# ─── Automatic mode preamble ──────────────────────────────────────────────
# WHY THIS MODE EXISTS. Updating used to be a gesture: the hook reported, the
# user typed `brain update`. Nobody typed it. The published engine stayed weeks
# behind the author's, and the only sign was a line at session start that people
# learn to stop reading.
#
# What it costs, said plainly: code from the remote repo now installs itself
# WITHOUT being asked. That is an execution channel. Three counterweights, none
# of them optional:
#   · `$AUTO_OFF` (or CBRAIN_NO_AUTO_UPDATE=1) restores the previous behaviour —
#     report, do not apply. The way out exists before the way in.
#   · the selftest decides. In automatic mode nobody is watching the screen: an
#     update that breaks the tool and LEAVES it broken would be worse than no
#     update at all. So red means roll back, immediately, by the script itself.
#   · nothing ever blocks a session — the hook is what detaches; here we only
#     work quietly into a log.
if [ "$AUTO" = "1" ]; then
  if [ -e "$AUTO_OFF" ] || [ -n "${CBRAIN_NO_AUTO_UPDATE:-}" ]; then exit 0; fi

  # A lock, because several sessions start at the same time. `mkdir` fails when
  # the directory exists: that is the shell's atomic test-and-set, where
  # `[ -f ] && touch` leaves a window between the two.
  # Stale lock: a machine that goes to sleep or a session killed mid-run would
  # leave the directory behind forever, and automatic updates would die in
  # silence — exactly the mute failure this is meant to avoid.
  if ! mkdir "$LOCK" 2>/dev/null; then
    if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
      rm -rf "$LOCK"; mkdir "$LOCK" 2>/dev/null || exit 0
    else
      exit 0                      # another session is already on it
    fi
  fi
  trap 'rm -rf "$LOCK"' EXIT INT TERM

  # Everything this script says goes to the log: in automatic mode there is no
  # screen. The log is overwritten on each pass — we want the last failure
  # readable, not a file that grows while nobody ever goes back to it.
  exec >"$JOURNAL" 2>&1
  echo "=== auto-update $(date '+%Y-%m-%d %H:%M:%S') ==="
fi

# Writes the report the hook will show at the NEXT session. One line, two
# fields: the outcome, then the version it concerns.
result() { [ "$AUTO" = "1" ] && printf '%s\t%s\n' "$1" "$2" > "$RESULT"; return 0; }

say()  { echo "  $*"; }
warn() { echo "  ⚠️  $*"; }

command -v git >/dev/null || { echo "❌ git is required for updates."; exit 1; }
git -C "$ENGINE" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "❌ The engine is not a git repo — it was copied, not cloned."
  echo "   Re-clone it to receive updates."
  exit 1; }

current() { git -C "$ENGINE" describe --tags --exact-match 2>/dev/null || git -C "$ENGINE" rev-parse --short HEAD; }

# Which FAMILY of tags this installation belongs to — English (`v1.2.3`) or
# French (`v1.2.3-fr`).
#
# ⚠ This is not decoration, it is a language-switch bug waiting to happen.
# Tags are not scoped to a branch, so `git tag -l 'v*'` hands back both
# families at once — and `sort -V` places `v1.18.0-fr` AFTER `v1.18.0`.
# Taking the global maximum therefore moved an ENGLISH installation onto the
# FRENCH tree the moment the French branch caught up, with no error at all:
# the tag exists, the checkout succeeds, and the user simply finds their tool
# speaking another language. It stayed hidden only while `fr` lagged behind.
#
# So: read the family off what is installed, and never leave it.
#
# The one case this cannot resolve is a bare tag and an `-fr` tag on the SAME
# commit, where `--exact-match` picks one arbitrarily. That cannot happen here:
# the two branches diverge by construction, `main` being a translation of `fr`.
# If they ever converge, this needs a recorded family instead of a derived one.
# ⚠ RECORDED FAMILY — added on 2026-08-13 together with the end of the `-fr`
# family. The derivation below reads the family off the INSTALLED tag, so it
# cannot remember a choice: a French installation that switched to English
# would fall back to `-fr` at the first doubt. The file settles it, and it only
# exists if somebody wrote it — nobody switches on their own. This is the
# "recorded family instead of a derived one" the note above already called for.
FAMILY_FILE="$STATE/tag-family"

family() {
  local tag branch
  if [ -f "$FAMILY_FILE" ]; then cat "$FAMILY_FILE"; return; fi
  tag="$(git -C "$ENGINE" describe --tags --exact-match 2>/dev/null || true)"
  case "$tag" in
    *-fr) echo "-fr"; return ;;
    v*)   echo "";    return ;;
  esac
  # Not sitting on a tag (a fresh clone, or a detached checkout): fall back to
  # the branch the clone tracks.
  branch="$(git -C "$ENGINE" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [ "$branch" = "fr" ] && echo "-fr" || echo ""
}

# The newest tag of THIS installation's family, by version order rather than
# alphabetical order: without `-V`, v10 would sort before v9.
latest_tag() {
  local suffix rx
  suffix="$(family)"
  if [ -n "$suffix" ]; then rx='^v[0-9]+\.[0-9]+\.[0-9]+-fr$'
  else                      rx='^v[0-9]+\.[0-9]+\.[0-9]+$'; fi
  # `|| true`: with no matching tag `grep` exits 1, and under `set -e` +
  # `pipefail` that would kill the script one line before the empty-result
  # check that already handles it properly.
  git -C "$ENGINE" tag -l 'v*' | grep -E "$rx" | sort -V | tail -1 || true
}

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

# WHERE THE CODE COMES FROM. An update replaces the engine — it runs code on
# this machine at the next session. Naming a version is not naming a source: a
# remote can be changed by anyone who can write to the engine's git config, and
# a tag can be moved. So the origin URL and the exact commit are shown BEFORE
# anything is applied, because that is what a person would need to check.
#
# This is disclosure, not verification. Tags are unsigned (see SECURITY.md);
# what follows lets you look, not the machine refuse.
REMOTE_URL="$(git -C "$ENGINE" remote get-url origin 2>/dev/null || echo "unknown")"
TARGET_SHA="$(git -C "$ENGINE" rev-parse --short "$NEW" 2>/dev/null || echo "unknown")"
echo "  from:   $REMOTE_URL"
echo "  commit: $TARGET_SHA"

if [ "$MODE" = "check" ]; then
  echo "  → \`brain update\` to install it."
  exit 10   # 10 = "an update exists", readable by a script
fi

# ─── Applying ──────────────────────────────────────────────────────────
# A hand-edited engine is somebody's work. We do not overwrite it.
#
# EXCEPT when the "work" is the gardening agents editing their own briefs. Those
# directories are mounted inside the trunk as symlinks, so an agent weaving
# `[[...]]` links across the trunk reaches them and dirties the ENGINE repo. That
# used to close a loop: every pass dirtied the engine, the next update refused,
# and the user fell behind for ever, silently. Reported 2026-08-16 by Maissane
# Lagsir on an install stranded exactly this way.
#
# Tolerating it costs nothing: the block further down already runs
# `git checkout -- .` after a successful update, so these edits were always going
# to be discarded. The only thing the refusal protected was the user's ability to
# update — which is what it was destroying.
#
# ⚠️ The refusal STAYS for anything outside those paths: a genuinely hand-edited
# engine is still somebody's work, and still blocks.
ENGINE_PATHS=$(grep -vE '^\s*(#|$)' "$ENGINE/cbrain/engine-paths.txt" 2>/dev/null \
               || echo "hooks agents capsule planet companion tests")
SALE=$(git -C "$ENGINE" status --porcelain --untracked-files=no | awk '{print $NF}')
HORS_MOTEUR=""
for f in $SALE; do
  garde=1
  for d in $ENGINE_PATHS; do
    case "$f" in "$d"/*) garde=0; break ;; esac
  done
  [ "$garde" = "1" ] && HORS_MOTEUR="$HORS_MOTEUR $f"
done
if [ -n "$SALE" ] && [ -z "$HORS_MOTEUR" ]; then
  say "engine dirty only under agent-owned paths — the gardening pass did that, not you"
  say "restoring them before updating (they are discarded after the update anyway)"
  git -C "$ENGINE" checkout -- . 2>/dev/null || true
fi

if [ -n "$HORS_MOTEUR" ] && { ! git -C "$ENGINE" diff --quiet || ! git -C "$ENGINE" diff --cached --quiet; }; then
  echo "❌ The engine has uncommitted local changes."
  echo "   Put them away (git stash / git commit) before updating."
  echo "   Files:$HORS_MOTEUR"
  # In automatic mode this is not a failure: it is a deliberate refusal to
  # overwrite somebody's work. But it has to be SEEN, otherwise the install
  # falls behind version after version while session start stays silent.
  result "blocked" "$NEW"
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

# ⚠ PUT THE ENGINE BACK CLEAN — without this, `brain update` works ONCE.
#
# Measured on 2026-08-16: `install.sh` runs `npm install` in the capsule, and npm
# REWRITES `capsule/package-lock.json`. The engine ends up with an uncommitted
# change… which the check above refuses. So the second update answered
# "❌ local changes" and so did every one after it. A permanent failure, on a
# machine where nobody suspects having touched anything. The root cause (a lock
# inconsistent with package.json) is fixed in rules.json; this line is the net,
# for the next generated file we do not see coming.
#
# Restoring is SAFE here, and the check above is what guarantees it: it demanded
# a clean tree BEFORE starting. Anything dirty at this point was therefore
# produced by the installer itself, never by the user. `checkout -- .` only
# touches TRACKED files: `node_modules/` and the rest of the untracked tree stay.
if ! git -C "$ENGINE" diff --quiet; then
  say "the installer modified engine files — restoring them to $NEW"
  git -C "$ENGINE" checkout -- . 2>/dev/null || warn "engine only partially restored"
fi

if bash "$HOME/.c-brain/trunk/hooks/selftest.sh" >/tmp/c-brain-update-selftest.log 2>&1; then
  echo
  echo "✅ Updated to $NEW — selftest green. Your notes were not touched."
  result "ok" "$NEW"
else
  echo
  warn "selftest FAILED after update (/tmp/c-brain-update-selftest.log)"
  if [ "$AUTO" = "1" ]; then
    # ⚠ THE DIFFERENCE BETWEEN THE TWO MODES IS HERE, and it is the only one
    # that matters. By hand, advising a rollback is enough: somebody reads the
    # screen. In automatic mode that advice would be read by nobody — the tool
    # would stay broken until the user noticed on their own, with no way to know
    # that an update they never asked for is what broke it. So we go back, right
    # away, and we SAY so at the next session.
    warn "automatic mode: rolling back to $CUR"
    git -C "$ENGINE" checkout -q "$CUR" || true
    bash "$ENGINE/install.sh" >/dev/null 2>&1 || warn "install.sh reported a problem while rolling back"
    result "rolled-back" "$NEW"
  else
    warn "Rollback advised:  brain update --rollback"
  fi
  exit 1
fi
