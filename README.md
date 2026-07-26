# C Brain

**A memory that grows** for command-line agents.

Your CLI agent is brilliant within a session, and amnesic between two. C Brain
gives it a persistent knowledge trunk: what you figure out once gets distilled
into a note, filed, linked — and **surfaced automatically** next time, from any
project.

The more work piles up, the more useful the tree gets. That is the opposite of a
conversation history, which only gets longer.

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

Paste this into your CLI:

```
Install C Brain: clone <REPO-URL> into ~/dev/c-brain, read its INSTALL.md,
then run ./install.sh and show me the final verification output.
```

Or by hand: `git clone … && cd c-brain && ./install.sh`

Details, prerequisites and uninstall: **[INSTALL.md](INSTALL.md)**.

## The idea holding it all together

```
~/.c-brain/engine  ← the ENGINE. Code. Updates, gets replaced, is disposable.
~/claude-brain     ← the TRUNK. Your notes. Changes only when YOU write.
```

The two never mix. That is what lets an update land with zero risk to your work —
and lets `uninstall.sh` remove everything while leaving your knowledge intact.

## What it does not do

- **It sends nothing.** No telemetry, no network call beyond `git pull`.
- **It does not read your notes**, except to hand them back to you.
- **It installs nothing on its own.** A new version is *announced*; you run
  `brain update` whenever suits you.
- **It ships no content.** Your tree starts empty — see
  [`skills/README.md`](skills/README.md) for the reasoning: we pass on the
  method, not somebody else's lived experience.

## Commands

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

## For the curious

- [`docs/design-doc.md`](docs/design-doc.md) — the problem, the rejected
  alternatives, the traps hit along the way and how each was closed.
- `sync.sh` + `rules.json` + `leakcheck.py` — the chain that extracts this engine
  from a real, personal Brain without letting a single line of lived experience
  escape.
