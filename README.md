# C Brain

[![CI](https://github.com/Yuno15-bb/c-brain/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Yuno15-bb/c-brain/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Yuno15-bb/c-brain?sort=semver&color=6b8afd)](https://github.com/Yuno15-bb/c-brain/releases/latest)
[![Licence](https://img.shields.io/github/license/Yuno15-bb/c-brain?color=8a8f98)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS-8a8f98)](#compatibility)

**A memory that grows** for command-line agents.

Your CLI agent is brilliant within a session, and amnesic between two. C Brain
gives it a persistent knowledge trunk: what you figure out once gets distilled
into a note, filed, linked — and **surfaced automatically** next time, from any
project.

The more work piles up, the more useful the tree gets. That is the opposite of a
conversation history, which only gets longer.

<p align="center">
  <img src="docs/media/capsule.webp" alt="The capsule: a small window cycling through every agent state — distilling, gardening, filing, correcting, mapping, architecting, challenging, archiving, synthesizing, auditing, committing, then back to idle" width="190">
</p>
<p align="center"><sub>The capsule, at its real size — all eleven states it can show you, then idle.</sub></p>

---

## What it actually does

| | |
|---|---|
| 🌳 **A trunk** | your lessons, projects, method — markdown, on your machine, versionable |
| 🔎 **Automatic recall** | relevant notes are injected into context on every prompt |
| 🤖 **8 agents** | they distill, file, link, challenge, synthesize, prune, repair, and watch the machine |
| 🔁 **A closed loop** | session ends → archive → distill → file, without being asked |
| 🥚 **A capsule** | a small window showing the agents at work, live |
| 🪐 **A planet** | your knowledge as a navigable 3D globe, rebuilt on every launch |
| ⬆️ **Updates** | the engine updates itself; **your notes are never touched** |

## Install

**As a Claude Code plugin** — the short way, and the one that updates itself:

```
/plugin marketplace add Yuno15-bb/c-brain
/plugin install c-brain@c-brain
```

That gives you the whole memory: the trunk, automatic recall, the eight agents
and the `brain` command. It creates `~/.c-brain/trunk` on your first session and
tells you so. It does **not** set up the capsule, the planet or the scheduled
jobs — a plugin cannot install a background service, and pretending otherwise
would leave you with a window that never opens.

**The full install** — everything above, plus the capsule, the planet and the
unattended maintenance:

```
Install C Brain: clone https://github.com/Yuno15-bb/c-brain into ~/dev/c-brain, read its INSTALL.md,
then run ./install.sh and show me the final verification output.
```

Or by hand: `git clone … && cd c-brain && ./install.sh`

Details, prerequisites and uninstall: **[INSTALL.md](INSTALL.md)**.

## The idea holding it all together

```
~/.c-brain/engine  ← the ENGINE. Code. Updates, gets replaced, is disposable.
~/.c-brain/trunk     ← the TRUNK. Your notes. Changes only when YOU write.
```

The two never mix. That is what lets an update land with zero risk to your work —
and lets `uninstall.sh` remove everything while leaving your knowledge intact.

Both live behind a leading dot, out of the way. Your notes should not: the
install puts a **`C Brain` shortcut in your home folder**, tagged, so the one
part that is yours is the one part you can see.

<p align="center">
  <img src="docs/media/where-it-lands.png" alt="A home folder in Finder: the usual Applications, Desktop, Documents, Downloads, Movies, Music and Pictures — plus a red-tagged C Brain folder, with an arrow pointing at it" width="900">
</p>

## What it does not do

- **It sends nothing.** No telemetry, no network call beyond `git pull`.
- **It does not read your notes**, except to hand them back to you.
- **It installs nothing on its own.** A new version is *announced*; you run
  `brain update` whenever suits you.
- **It ships no content.** Your tree starts empty — see
  [`skills/README.md`](skills/README.md) for the reasoning: we pass on the
  method, not somebody else's lived experience.

## The planet

Every note is a dot, every `[[link]]` an arc. The globe is rebuilt from your
trunk on each launch — projects become cities, cross-cutting lessons become
regions.

Turn the globe, point at a note: its links light up, and the panel gives you its
region, its neighbours, its description and the file it lives in — one
double-click away from the note itself.

<p align="center">
  <img src="docs/media/planet.webp" alt="The knowledge planet: the globe turns, the cursor lands on a note, its linked arcs light up and a panel opens showing the note's region, its seven connections, its description and its file path" width="900">
</p>
<p align="center"><sub>A demo trunk of 57 notes and 178 links. Yours starts empty.</sub></p>

## Commands

<p align="center">
  <img src="docs/media/recall.png" alt="Terminal: brain demo places three notes, brain recall ranks them by relevance, brain demo --remove takes them away" width="820">
</p>

```bash
brain status          where the trunk stands
brain recall <word>   search your memory
brain doctor          tree health (dead links, inconsistencies)
brain review          full audit of the trunk
brain next            your resume points
brain selftest        verify the installation
brain update          update the engine  (--check · --rollback)
brain version         installed version
```

## Compatibility

**macOS.** launchd, Electron and `open` are used.

**Claude Code** for the full experience: it is what fires the hooks (recall,
archiving, autonomous maintenance, status line). With another CLI agent, C Brain
installs and works **on demand** — trunk, agents, `brain`, planet, capsule — but
without the closed loop. The installer detects this and says so, rather than
pretending otherwise.

## Language

`main` is English. The French original lives on the **`fr` branch** — it is the
source the engine is extracted from, and English is derived from it. See
[`docs/translation.md`](docs/translation.md).

> **In progress**: the docs, the installer, the CLI and the eight agents are
> English. The hook comments and the capsule/planet interface strings are still
> being translated.

## For the curious

- [`docs/design-doc.md`](docs/design-doc.md) — the problem, the rejected
  alternatives, the traps hit along the way and how each was closed.
- `sync.sh` + `rules.json` + `leakcheck.py` — the chain that extracts this engine
  from a real, personal Brain without letting a single line of lived experience
  escape.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how the two branches relate, and why a
  hand-edited engine file on `fr` disappears on the next sync.
- [`SECURITY.md`](SECURITY.md) — what this writes to your machine, what runs
  unattended, and how to report a hole privately.
- [`CHANGELOG.md`](CHANGELOG.md) — generated from the tags, so it cannot drift.

## Licence

**Apache 2.0** — see [LICENSE](LICENSE).

You may use it, study it, modify it, redistribute it, and build on it, including
commercially. The licence includes a patent grant, and asks only that you keep
the attribution and state your changes.

Everything you write with it — your notes, your trunk, your skills — is yours,
and this licence makes no claim on it.
