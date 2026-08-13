---
name: readme
description: Guide to the 8 agents (distiller, gardener, architect, challenger, synthesizer, archivist, mechanic, machinist) — roles, how to run them, autonomous thresholds
metadata:
  type: reference
---

# Agents

Native Claude Code sub-agents that maintain and feed the trunk. The canonical
files are **versioned here** and symlinked into `~/.claude/agents/` so Claude
Code can discover them.

## The agents

- **[distiller](distiller.md)** — creates knowledge: turns raw sessions (`sessions/archive/`, transcripts) into clean notes and lessons, or updates what exists. *Does not tidy the tree globally* (that is the gardener).
- **[gardener](gardener.md)** — tidies the tree: deduplicates, guarantees every note is on the map (`MEMORY.md` + `lessons/INDEX.md`), weaves and repairs the **obvious** `[[...]]` links, masks secrets, handles coherence and usefulness. *Creates no knowledge.*
- **[architect](architect.md)** — **global** cohesion: reads the whole graph topology (`hooks/brain_topology.py`) to weave the **missing** links, connect isolated notes, reattach detached islands, favour cross-domain bridges. *The wide view, where the gardener files note by note.*
- **[challenger](challenger.md)** — puts the knowledge to the test: hunts the stale, the false, the contradicted, the oversold; produces substantiated doubts (`state/challenges.json`). *Fixes nothing — it doubts.*
- **[synthesizer](synthesizer.md)** — second-order knowledge: connects a cross-cutting theme across several projects into a dense essay (`lessons/`). *Creates the wide view no single note states.*
- **[archivist](archivist.md)** — manages the cold layer: freshness, staleness, archiving dead weight (via `state/utility.json`). *Proposes, never deletes.*
- **[mechanic](mechanic.md)** — repairs the machine infrastructure: hooks, wiring, symlinks, capsule. *Never note content.*
- **[machinist](machinist.md)** — the physical machine: RAM, CPU, heat, orphaned processes. *Never the knowledge, never the software infrastructure.*

> **Eight roles, one team (separation of powers).** The distiller *writes*, the gardener *files* (local), the architect *connects* (global), the challenger *doubts*, the synthesizer *synthesizes*, the archivist *prunes*, the mechanic *repairs the infrastructure*, the machinist *keeps the machine cool*. None does another's job — that is what keeps the system safe and auditable.

## How to run them

In any Claude Code session, in plain language:
- "**run the distiller** on my last session" → capture what deserves to stay.
- "**run the gardener**" → clean and tidy the tree.

Or by naming them explicitly as sub-agents. A typical flow after a heavy session:
1. `distiller` extracts the notes from the session,
2. `gardener` checks they are filed, linked, and on the map.

## Reinstalling the symlinks (new machine / after a git clone)

`install.sh` does this for you. By hand:

```bash
mkdir -p ~/.claude/agents
# symlink EVERY agent — anything left out stays silent after a clone
for a in ~/.c-brain/trunk/agents/*.md; do
  [ "$(basename "$a")" = "README.md" ] && continue
  ln -sf "$a" ~/.claude/agents/"$(basename "$a")"
done
```

## The second autonomous layer — cohesion watch

Beyond the SessionEnd pair `distiller → gardener`, a **second layer** maintains
the trunk on its own through `hooks/brain_upkeep.py`, called at the end of every
maintenance pass:

1. it **regenerates the mechanical sensors** (free, zero LLM): `brain_topology.py`, `brain_utility.py` (plus the accumulated `coherence.json`);
2. each watch agent is **eligible** only if **its sensor crosses a threshold** (real work exists) **and** its **cooldown** (12 h) has elapsed;
3. **at most ONE agent is woken per pass** (a cost guarantee: about one extra LLM run, and only when there is something to do), in priority order **challenger → architect → archivist → mechanic** (`brain_upkeep.ORDER`).

Thresholds: architect (≥1 isolated note OR ≥3 doubtful placements OR ≥2 components OR ≥8 missing links) · challenger (≥1 **`(a,b)` pair** to arbitrate in `coherence.json` — arbitration notes do not count) · archivist (≥3 notes of dead weight) · **mechanic (≥1 defect in `doctor.json`)**. Over time every dimension gets its turn. Best effort: if a watch agent fails (quota, login), the pass is skipped — no data is lost (unlike distillation). Dry-run debug: `python3 hooks/brain_upkeep.py decide`.

> ⚠️ **The mechanic IS wired into the autonomous loop.** It runs on `sonnet` with `--dangerously-skip-permissions` and the `Edit/Write/Bash` tools: it can therefore **modify the infrastructure on its own** when `brain_doctor` reports a defect. Its mission (`brain_upkeep.TASKS`) bounds it to the defects the doctor listed and forbids touching hooks, settings or symlinks unless explicitly pointed at them. It is the only watch agent whose failed pass cannot be replayed identically — watch it through `sessions/gardening.log`.

Still optional: wiring in the **synthesizer** (no sensor — it is triggered by thematic density, not by a defect).

**Mechanical guard after gardening** (zero LLM): `auto_maintain` re-runs `brain_doctor --json` right after the gardener and logs `[doctor] … post-gardening: N defect(s)` into `sessions/gardening.log` when `N != 0`. The gardener can no longer be the sole judge of its own pass.

**Invariants**: `python3 tests/invariants_brain.py` — sensors that come back down, tolerance for legacy entries, doc↔code agreement, per-agent model. Run by `hooks/selftest.sh`.
