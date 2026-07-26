# Installing C Brain

## The short way: ask your agent

Paste this into your CLI (Claude Code or another command-line agent):

```
Install C Brain: clone https://github.com/Yuno15-bb/c-brain into ~/dev/c-brain, read its INSTALL.md,
then run ./install.sh and show me the final verification output.
```

That's it. The agent clones, installs, and hands you back the selftest result.

## The manual way

```bash
git clone https://github.com/Yuno15-bb/c-brain ~/dev/c-brain
cd ~/dev/c-brain
./install.sh
```

Options: `--dry-run` (writes nothing, shows what would happen) ·
`--no-launchd` (no scheduled jobs) · `--no-capsule` (no Electron).

---

## What the install does — and does not do

Two locations, and keeping them apart is the heart of the system:

```
~/.c-brain/engine  → link to this repo. CODE only. Updates.
~/claude-brain     → YOUR trunk. Your notes. Never overwritten, never updated.
```

The installer:

- creates your **empty** trunk if none exists (and touches nothing if one does);
- links the engine into the trunk with symlinks;
- puts the `brain` command in `~/.local/bin`;
- makes the agents visible to your CLI;
- **adds** its hooks to `~/.claude/settings.json` without touching the rest —
  your model, your theme, your own hooks are preserved, and a backup is written
  before any modification;
- installs the capsule and the scheduled jobs, unless you decline them;
- drops a planet launcher on your Desktop;
- **checks its own work** (`selftest` + `doctor`) and shows you the result.

It deletes nothing, sends nothing over the network, and reads none of your data.

## Prerequisites

| Required | For |
|---|---|
| macOS | launchd, Electron, `open` |
| `python3` | every hook and the CLI |
| `git` | updates |
| `npm` *(optional)* | the Electron capsule — everything else works without it |

## If you don't use Claude Code

C Brain still installs, and gives you the trunk, the agents, the `brain` CLI, the
planet and the capsule.

**What you won't get**: the closed loop. Recall at the start of a session,
archiving at the end, autonomous maintenance — all go through the hooks in
`~/.claude/settings.json`, which are specific to Claude Code. Elsewhere, C Brain
works **on demand**: `brain recall`, `brain status`, agents invoked explicitly.
The installer detects this and tells you — it does not pretend.

## First steps

```bash
brain status          where the trunk stands
brain recall <word>   search your memory
brain doctor          tree health
brain selftest        verify the installation
```

Then open `~/claude-brain/MEMORY.md`: it is the index loaded at the start of every
session, and it explains the note format. Your tree starts empty — it grows with
the work, not before.

## Uninstalling

```bash
~/dev/c-brain/uninstall.sh
```

**Your trunk and your notes are never deleted.** Removed: the C Brain hooks (the
rest of `settings.json` untouched), the engine symlinks, the `brain` command, the
Desktop launcher, the scheduled jobs. Backups stay in `~/.c-brain/backups/`.
