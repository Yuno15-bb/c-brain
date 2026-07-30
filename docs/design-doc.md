# Design doc — C Brain (an installable, self-updating knowledge trunk)

**TL;DR** — Extract, from a living `~/claude-brain`, a package called **C Brain**
that installs in one command on another macOS machine, behaves **identically** to
the original with everything around it (hooks, agents, capsule, planet,
companion, status line, CLI, launchd), and **updates itself** on each user's
machine.

**Why this doc is sized the way it is**: publishing is irreversible (revoking
access does not un-clone what is already cloned), the source of the package is a
system holding **real personal data about third parties**, and automatic updates
add a second serious risk: **code that installs itself on somebody else's
machine**.

---

## Who it is for, and why

**Audience**: users of a command-line agent — Claude Code first, but any model
running in a CLI — who want **more memory, more context, and a knowledge tree
that grows with time and with the volume of work** accumulated alongside their
agent.

This is not one more tool: it is what stops a session starting from zero, and
keeps what was understood once findable from any other project.

**Installation**: the user does not follow a procedure. They give **one command
to the agent already running in their CLI**, and the agent installs it. That is
the shortest possible manual, and it matches how this audience already works.

**An honest constraint, not to be dressed up**: the trunk, the agents, the CLI,
the planet and the capsule are portable everywhere. The **automatic wiring**
(`SessionStart` / `SessionEnd` / `PostToolUse` hooks, the status line) goes
through `~/.claude/settings.json` and exists only in Claude Code. On another CLI,
C Brain works **on demand** (`brain recall`, `brain status`, agents invoked
explicitly) but **not as a closed loop**. The installer detects this and says so;
it never lets anyone believe in an autonomy that is not there.

## Problem (the need, not the solution)

The trunk worked on **one** machine only, and its installation was not an
artefact: it was a sequence of manual gestures reconstructed from memory.

- A machine migration proved it: the `~/.claude/agents` symlink was never
  recreated → **the agents were invisible and the autonomous loop spun on nothing
  for 24 hours**, with no visible error at all.
- The resume `.plist` carried a hardcoded home path → the scheduler died silently.
- Nobody else could run the system, so it was neither showable nor transmissible.
- And once installed somewhere, **it freezes**: fixes made here never reach it. A
  frozen system on somebody else's machine is worse than none — it carries the
  bugs that have already been repaired.

The need: **that another person gets the same system running, that it can be
proven, and that it stays current without them doing anything.**

## Measurable success

In an isolated `HOME` first, then on a third-party machine:

| Criterion | Threshold |
|---|---|
| Installation | `git clone && ./install.sh` — **zero manual steps** beyond an admin password, under 10 minutes |
| Health | `brain selftest` **green**, `brain doctor` without error |
| Hooks live | a test session triggers recall + archiving (proven by `state/`, not by the docs) |
| Agents resolved | the 8 agents listed by the CLI (the symlink trap is detected by the installer) |
| Capsule | an Electron window animating on a change to `state/status.json` |
| Planet | double-clicking the `.command` → a globe served on `localhost:8765` |
| Status line | visible in the CLI, same rendering as on the source machine |
| Idempotence | a second `install.sh` run does zero damage, `settings.json` untouched |
| **Updates** | a fix published here reaches the user **at their next session start**, without intervention, **without touching a single one of their notes** |
| **User rollback** | `brain update --rollback` restores the previous version in one command |
| Leaks | `leakcheck`: **zero marker** of personal data or secrets in the repo, git history included |

## Non-goals (explicit boundaries)

- **No note content whatsoever.** The package ships an **empty** trunk. Nobody clones somebody else's brain.
- **No skills** (`~/.claude/skills`) — too personal. Measured: **20 out of 20** contained personal markers (client, people, personal context). None was transferable. What ships instead: an **empty** `skills/` plus `skills/README.md`, the documentation of the **house standard** (nine requirements, forge-on-block, the skill/agent boundary, a template). We pass on the method that makes the skill, not the skill.
- **No `desktop_sync.py`** and no matching plist: it backs up the author's Desktop to *their* GitHub — strictly personal, and destructive on somebody else's machine (`--delete` on an unknown destination).
- **macOS only** (launchd, Electron, `open`). No Linux or Windows.
- **No telemetry.** An update is a `git pull`; it reports **nothing** back.
- **No forced migration of the source machine** to the new layout (see "Impact").
- **Neither the cold corpus nor the embeddings venv**: optional, BM25 is enough by default.

## Approach

### 1. The structural decision: separate the ENGINE from the TRUNK

This is what makes automatic updates possible **with no risk to the data**.

A single `~/claude-brain` mixes code (hooks, agents, capsule, planet) and content
(notes). A `git pull` on a repo where the user also commits their own notes ends
in conflict — or in loss.

```
~/.c-brain/engine/     ← a clone of C Brain. Code ONLY. git pull cannot conflict.
~/.c-brain/trunk/        ← the user's trunk. Their notes, their own git. NEVER touched.
    hooks/  → symlink to ~/.c-brain/engine/hooks
    agents/ → symlink to ~/.c-brain/engine/agents
    capsule/ planet/ companion/ → symlinks
    lessons/ projects/ meta/ life/ sessions/ state/ → REAL, the user's own
```

The paths become `~/.c-brain/trunk/hooks/...`: **no hook, no agent and no path
changes shape**. Behaviour is identical; only where the files come from changes.

### 2. Automatic updates

- `brain update`: `git pull` inside `~/.c-brain/engine`, then **replays `install.sh`** (idempotent by construction — it already knows not to overwrite anything). The symlinks make propagation immediate.
- **Automatic trigger**: a `SessionStart` hook checks at most **once every 24 h** (throttled by a timestamp file) whether a newer tag exists. The check runs in the background, never blocks, and fails silently offline.
- **Tagged versions, never `main`**: users follow `vX.Y.Z` tags, not the working branch. A draft commit reaches nobody.
- **Migrations**: a numbered `migrations/` folder, each script idempotent and **never destructive** to `lessons|projects|meta|life|sessions`. The log lives in `~/.c-brain/state`.
- **Rollback**: `brain update --rollback` checks out the previous tag and re-runs `install.sh`.

### 3. Generalization is declarative, not manual

`sync.sh` re-copies the engine from the living trunk on every pass: **a fix made
by hand would be overwritten**, and the leak would be back at the next commit
with nothing to flag it. Hence `rules.json` + `generalize.py`, **chained
automatically after every copy**, with a guard: a rule finding fewer occurrences
than expected makes the script **fail** — a falling counter means the source
changed its wording, not that the problem went away.

### What the engine/trunk split broke (found by running, not by reading)

The same trap twice: code deriving its paths from `__file__` instead of `$HOME`.
Under a symlink it then points into the **engine** instead of the **trunk**.

- `tests/invariants_brain.py` was writing `state/coherence.json` **into the installed repo** → three tests in error. Fixed by a rule: two distinct roots, `CODE` (follows the file) and `BRAIN` (derives from `$HOME`). The 22 other uses of `__file__` locate neighbouring **code** — those are correct and stay.
- `capsule/main.js` watched `status.json` through `__dirname` while `index.html` derived it from `homedir()`. The capsule would have animated but **never re-shown itself** when an agent woke up. Two halves of the same component disagreeing.
- `planet/graph.json` is regenerated **inside the engine**. Tolerated: it is gitignored and rebuilt on every launch. Never to be extended to user data.

### Two silent failures the installer work caught

- **A status line installed and invisible**: the file was copied into `~/.claude` but the `statusLine` key was never written into `settings.json`. Nothing would have flagged it — just a missing line. Fixed, and set **only** when the user has none of their own.
- **`brain update` announced but non-existent**: the installation summary listed it before the command existed. Removed from the message rather than promised empty.

### Rejected alternatives

| Alternative | Why not |
|---|---|
| **One repo for code and content, `git pull` on it** | The user commits their notes into the same repo → guaranteed conflict on the first update, lost notes at worst. That is the heart of the problem, not a detail. |
| **Reusing the previous extraction repo** | Its history had carried personal content; `git log -p` brings it back even after cleaning. → a new repo, and the old one deleted once C Brain was verified. |
| **Publishing the trunk itself behind a `.gitignore`** | A denylist lets things through by default. One forgotten file is a personal-data leak. An allowlist refuses by default. |
| **Copying files instead of symlinking** | Every update would have to re-copy and guess what the user changed locally. The symlink makes the code/content boundary **physical**, which is non-negotiable. |
| **Silent updates from `main`** | Unreviewed code would install on somebody else's machine. Tags force an explicit decision to publish. |
| **A Python or Makefile installer** | The entry point must run on a fresh Mac **before** anything is installed; `bash` is guaranteed, a Python venv is not. |
| **Copying by hand on every update** | Guaranteed drift between the living trunk and the package, with no signal. Hence `sync.sh --check`, which fails when the package has fallen behind. |

## Contract (what everything else rests on)

```
c-brain/
  install.sh          # the single entry point, idempotent, backs up before overwriting
  uninstall.sh        # back to the previous state, in one command
  publish.sh          # the only sanctioned path to a git push
  sync.sh             # living trunk → repo, allowlist; --check = drift report only
  generalize.py       # applies rules.json AFTER the copy (chained by sync.sh)
  rules.json          # declarative rules: code blocks + text substitutions
  leakcheck.py        # zero marker, otherwise exit 1 (blocks the commit)
  brain               # CLI (status|doctor|audit|review|recall|next|selftest|update|push…)
  hooks/              # the hooks + .plist.template  (desktop-sync EXCLUDED)
  agents/             # 8 agent definitions, generalized (no client or project names)
  capsule/            # Electron, without node_modules, without dead assets
  planet/             # index.html, launch.sh, media/  (graph.json EXCLUDED)
  companion/          # live change tracking
  statusline.py       # the CLI status line
  cbrain/             # update.sh, check_update.py, migrations/ — C Brain specific
  skeleton/           # the EMPTY trunk created on the user's machine
  skills/             # EMPTY + README.md = the house standard (no skill shipped)
  docs/               # this design doc, the install guide, the verification recipe
```

**Contract invariants** (checked by `selftest`, not by re-reading):

- no absolute `/Users/<somebody>` path in an executed file — everything derives from `$HOME`;
- `state/`, `planet/graph.json`, `capsule/node_modules/`, `corpus/`, `.venv/` are never committed;
- `install.sh` run twice yields the same state;
- **no engine script writes into `lessons|projects|meta|life`** — except the agents, the only legitimate write path, and they go through the user's trunk.

## Impact & risks

- **Risk #1 — leaking third parties' personal data.** `planet/graph.json` holds the **full text of the notes**, real names included, and is regenerated on every launch. Excluded by the allowlist *and* by `.gitignore` *and* caught by leakcheck. Three nets.
- **Risk #2 — auto-update is a code-execution channel into somebody else's machine.** Mitigations: tags only, never `main`; migrations non-destructive by construction; rollback in one command; the hook never blocks a session when it fails.
- **Risk #3 — the engine still named its author and their clients.** Measured after the first pass: **50 occurrences across 16 files**, and not confined to the agents. That was the real content of the generalization work.
- **The source machine stays the source of truth** and does **not** migrate to the engine/trunk layout for now: it runs in production with ten active hooks, and it is not refactored just to ship. `sync.sh` pushes its state into C Brain. A migration can follow once C Brain is proven elsewhere.
- **Confirmed dead weight**: `capsule/assets/` (7.4 MB) is **entirely dead** — the creature sprite is inline in `index.html` (the `BODY` grid), and no file under `assets/` is referenced by the code. Excluded by the allowlist.
- **Tooling trap**: macOS 27 ships **openrsync**, not GNU rsync. On a *single* file, `--dry-run --itemize-changes` always reports a transfer → a permanent false drift. `sync.sh` compares standalone files with `cmp`, never with rsync.
- **macOS TCC**: anything going through launchd and reading `~/Desktop` is refused without Full Disk Access — a GUI action that cannot be scripted, so it belongs in the install procedure.
- **Cost**: none. No server; an update is a `git pull`.

## Reversibility / kill switch

- **Before the first push**: everything is local, `rm -rf` is enough.
- **After publishing**: making the repo private again **does not un-clone** what is already out → the real kill switch is the leak check **before** the push, not after.
- **A bad update**: `brain update --rollback` (previous tag + reinstall). Removing the tag on GitHub also stops propagation to users who have not pulled yet.
- **On the user's machine**: `uninstall.sh` plus a timestamped `settings.json` backup → back to the previous state in one command. Their trunk is never deleted.
- **On the source machine**: no risk — the pipeline is read-only on the living trunk.

## Delivery (mergeable lots, each testable alone)

| Lot | Content | Done when |
|---|---|---|
| **L0** ✅ | `sync.sh` (allowlist) + `leakcheck.py` + `.gitignore` + `skills/` | tools shipped and **executed**: `sync --check` proven on three simultaneous divergences, leakcheck red at 50 (it sees) |
| **L1** ✅ | `generalize.py` + `rules.json` + `skeleton/` | **leakcheck green** (50 → 0); `selftest` + `doctor` + `recall` + `graph_export` green in an isolated HOME |
| **L2** ✅ | `install.sh` + `uninstall.sh` + `merge_settings.py` + `INSTALL.md` | full cycle proven in an isolated HOME: second pass = zero change; `settings.json` returns **semantically identical** after uninstall — every key of
yours back, none of ours left. Not byte-identical: uninstall rewrites the file through
Python's JSON serializer, so hand-formatting comes back reformatted (corrected v1.13.0); the user's note intact |
| **L3** ✅ | Capsule + status line | screenshots: `DISTILLING` then `IDLE` on a `status.json` change; three components aligned on the same path |
| **L4** ✅ | Planet + Desktop `.command` | `launch.sh` → `200` on index/graph/glb; headless capture of the globe and its legend |
| **L5** ✅ | Companion | pre/post hooks replayed: `+3 −1` aggregated, status line at **two lines** |
| **L6** ✅ | `brain update` + `check_update.py` + `migrations/` + `VERSION` | a fake remote with two tags: update, migration run exactly once, rollback, note intact at every step |
| **L7** ✅ | README + verification recipe + `publish.sh` + the repo online | clone from GitHub → `install.sh` → selftest and doctor **green** |
| **L8** ✅ | English translation, `main` / `fr` split | every **user-visible** string in English, held by `tests/english_only.py` in CI; **hook comments are still French** and say so in the README; `fr` keeps the original and stays the sync branch |

Critical path: **L0 → L1 → L2 → L6**. L3/L4/L5 parallelize after L2.

## Open questions

1. **Tag signing**: GPG or a plain annotated tag? The first proves an update really comes from the author; the second is simpler.
2. **`sync.sh` cadence**: by hand, or a hook that warns when the package has fallen more than N days behind the living trunk?
3. **Is the empty trunk really empty?** A sample `MEMORY.md` and two or three demonstration notes would help a newcomer grasp the format — but they must be **written**, not extracted from somebody's real notes.

---

*First drafted 2026-07-26. Kept in sync with reality as the implementation
proceeded — a design doc that stops matching the code is a comment that lies.*
