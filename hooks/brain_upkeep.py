#!/usr/bin/env python3
"""brain_upkeep — the SECOND autonomous layer (cohesion watch).

The SessionEnd loop (auto_maintain.py) wakes only two agents:
  distiller (writes) → gardener (files) → commit.
The four WATCH agents (challenger, architect, archivist, mechanic) used to
run only by hand. This module wires them into the automation WITHOUT blowing up the cost.

Principe « cadence + seuil capteur » :
  1. we only REGENERATE the sensors of agents whose cooldown has elapsed
     (free, zero LLM; no point recomputing topology while the architect sleeps):
       brain_topology --json  → state/topology.json   (architecte)
       brain_utility  --json  → state/utility.json     (archiviste)
       brain_doctor   --json  → state/doctor.json       (mechanic)
       coherence.json         → accumulated by check_coherence (challenger, no regen)
  2. each agent is ELIGIBLE only if ITS sensor crosses a threshold
     (real work to do) AND its cooldown has elapsed (no thrashing).
  3. AT MOST ONE is woken per pass (a cost guarantee: about one extra LLM run,
     and only when there is genuinely something to do). Over time,
     every dimension gets attention, by priority.
  quota resilience: preflight BEFORE spending, and the cooldown is engraved ONLY if
     the agent actually succeeded (a quota/login failure is retried, not "burned").

Separation of powers respected: HERE we MEASURE and DECIDE who to wake;
l'agent LLM, lui, JUGE et agit. On ne touche jamais au contenu des fiches.

Called from auto_maintain's headless wrapper (already under a preflighted quota,
CLAUDE_BRAIN_GARDENING=1). Best effort: if an agent fails (quota/login), the
watch pass is simply skipped — unlike distillation, nothing is lost.

Usage :
  brain_upkeep.py decide        → the decision as JSON (debug, no effect)
  brain_upkeep.py run [sid]      → regenerates, decides, wakes at most one agent
Sort toujours 0 (ne bloque jamais un hook).
"""
import os, sys, json, time, shutil, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from brain_status import write_status
except Exception:
    def write_status(*a, **k): pass
try:
    import brain_guard as guard          # quota/account resilience (the same guard as layer 1)
except Exception:
    guard = None

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
HOOKS = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BRAIN, "state")
CADENCE = os.path.join(STATE, "upkeep.json")   # memory of the last wake-ups
LOG = os.path.join(BRAIN, "sessions", "gardening.log")
COST = os.path.join(BRAIN, "sessions", "cost.jsonl")

# Cooldown: the same agent does not run again for N hours, even if its sensor
# reste au-dessus du seuil (anti-thrash : laisse le temps qu'une passe porte ses
# fruits avant d'en redemander une).
COOLDOWN_H = 12

# Wake priority (at most one per pass): honesty first (contradictions),
# then cohesion (links/islands), pruning (dead weight), finally infrastructure (doctor defects).
ORDER = ["challenger", "architect", "archivist", "mechanic"]

# Model per agent (consistent with their front matter; the parent shell forces haiku
# for distill/garden, here we respect what each role actually needs).
MODEL = {"architect": "sonnet", "challenger": "sonnet",
         "archivist": "haiku", "mechanic": "sonnet"}

# Capsule activity per agent (keys ALREADY recognized by capsule/index.html: the
# creature shows the right role at work). The architect has ITS own scene
# ('architecting' : ponts inter-domaines) — distincte du 'mapping' du jardinier.
ACT = {"architect": "architecting", "challenger": "challenging",
       "archivist": "archiving", "mechanic": "auditing"}

# The mechanical sensor to regenerate for EACH agent (we do not recompute a
# QUE les capteurs des agents dont le cooldown est ouvert — inutile de recalculer la
# TF-IDF topology over every note if the architect is on cooldown anyway).
# The challenger has no sensor to regenerate (coherence.json is accumulated
# continuously by check_coherence on every note written).
REGEN = {"architect": ("brain_topology.py", ["--json"]),
         "archivist": ("brain_utility.py", ["--json"]),
         "mechanic": ("brain_doctor.py", ["--json"])}


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def regen_sensors(agents):
    """Regenerates ONLY the sensors of the given `agents` (cheap, zero LLM).
    Optimisation O1 : on ne recalcule pas un capteur dont l'agent est en cooldown."""
    py = sys.executable
    seen = set()
    for ag in agents:
        spec = REGEN.get(ag)
        if not spec or spec[0] in seen:
            continue
        mod, flags = spec
        seen.add(mod)
        try:
            subprocess.run([py, os.path.join(HOOKS, mod), *flags],
                           cwd=BRAIN, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=60)
        except Exception:
            pass  # a silent sensor → that agent is simply judged ineligible


def sensor_signal():
    """Reads the four sensors and returns, per agent, (does it have work?, a readable reason)."""
    topo = load_json(os.path.join(STATE, "topology.json"), {})
    util = load_json(os.path.join(STATE, "utility.json"), {})
    coh = load_json(os.path.join(STATE, "coherence.json"), [])
    doc = load_json(os.path.join(STATE, "doctor.json"), {})

    n_miss = len(topo.get("missing_links", []))
    n_iso = len(topo.get("isolated", []))
    n_bad = len(topo.get("odd_placement", []))
    n_comp = topo.get("n_components", 1)
    n_dead = len(util.get("poids_mort", []))
    # A sensor counts UNITS OF WORK, not lines. coherence.json may carry
    # arbitration notes ("✓ false positive") left by an agent: counting those
    # kept the challenger eligible forever → a sonnet run every 12 h for nothing, which
    # preempted the architect (first in ORDER). Only an (a,b) pair is work.
    n_contra = sum(1 for f in coh if isinstance(f, dict)
                   and isinstance(f.get("a"), str) and isinstance(f.get("b"), str)
                   ) if isinstance(coh, list) else 0
    n_defaut = doc.get("total", 0) if isinstance(doc, dict) else 0

    sig = {}
    # ARCHITECT: global cohesion is fraying — a detached island, an isolated note,
    # a doubtful placement, or a pile of obvious missing links.
    arch_ok = n_iso >= 1 or n_bad >= 3 or n_comp >= 2 or n_miss >= 8
    sig["architect"] = (arch_ok,
        f"{n_miss} missing links, {n_iso} isolated, {n_bad} doubtful placements, "
        f"{n_comp} composante(s)")
    # CHALLENGER: at least one pair flagged "duplicate OR contradiction" to settle.
    sig["challenger"] = (n_contra >= 1, f"{n_contra} heavy overlap(s) to arbitrate")
    # ARCHIVIST: dead weight is piling up (cold notes, archiving candidates).
    sig["archivist"] = (n_dead >= 3, f"{n_dead} note(s) of dead weight")
    # MECHANIC: the doctor reports infrastructure defects (dead links, orphans,
    # front matter, naming, off-index). It wakes ONLY on a real defect —
    # donc rare, exactement quand on en a besoin (sinon doctor.total = 0).
    sig["mechanic"] = (n_defaut >= 1, f"{n_defaut} infrastructure defect(s) reported by the doctor")
    return sig


def cooldown_ok(agent, now):
    cad = load_json(CADENCE, {})
    last = cad.get(agent, {}).get("last_ts", 0)
    return (now - last) >= COOLDOWN_H * 3600


def record_run(agent, now):
    cad = load_json(CADENCE, {})
    ent = cad.get(agent, {})
    ent["last_ts"] = now
    ent["runs"] = ent.get("runs", 0) + 1
    cad[agent] = ent
    try:
        os.makedirs(STATE, exist_ok=True)
        json.dump(cad, open(CADENCE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass


def decide(now=None):
    """Returns the agent to wake (or None) plus the per-agent detail, launching nothing."""
    now = now or time.time()
    sig = sensor_signal()
    report = {}
    chosen = None
    for agent in ORDER:
        has_work, reason = sig.get(agent, (False, ""))
        cd = cooldown_ok(agent, now)
        eligible = has_work and cd
        report[agent] = {"has_work": has_work, "cooldown_ok": cd,
                         "eligible": eligible, "reason": reason}
        if eligible and chosen is None:
            chosen = agent          # the first eligible one, in priority order
    return {"chosen": chosen, "agents": report}


TASKS = {
    "architect": (
        "COHESION watch (automatic). The state/topology.json sensor is up to date: "
        "read it and handle, IN PRIORITY ORDER, the detached islands, the isolated notes, "
        "the odd placements, then a few of the highest-value cross-domain missing "
        "links. Weave the missing [[...]] links, reattach what is isolated. "
        "TOKEN ECONOMY: lean on the sensor JSON, open only the "
        "notes you modify. Do NOT commit (the shell handles it). Short report."),
    "challenger": (
        "HONESTY watch (automatic). state/coherence.json lists pairs with heavy "
        "overlap (duplicate OR contradiction). For each one, decide: a real "
        "a duplicate to merge, a contradiction to report, or a false positive. Produce your "
        "substantiated doubts (you do not rewrite the knowledge, you test it). "
        "TOKEN ECONOMY: open only the notes involved. Do NOT commit. Short report."),
    "archivist": (
        "FRESHNESS watch (automatic). state/utility.json lists the dead weight (cold "
        "notes). PROPOSE archiving the most clearly stale ones (never delete "
        "on your own: mark or move them following the archiving convention). "
        "TOKEN ECONOMY: lean on the JSON. Do NOT commit. Short report."),
    "mechanic": (
        "INFRASTRUCTURE watch (automatic). state/doctor.json lists mechanical defects: "
        "liens_morts, orphelins, frontmatter, nommage, hors_index. Corrige UNIQUEMENT "
        "those targeted and SAFE defects (dead link → right link or removal, missing "
        "front matter → completed, naming → kebab-case). ABSOLUTE CAUTION: touch "
        "hooks, settings or symlinks ONLY if the doctor points at them explicitly; at the slightest "
        "doubt, do nothing and say so in the report. TOKEN ECONOMY: "
        "lean on the JSON, open only what you fix. Do NOT commit. Short report."),
}


def _last_cost_line():
    last = ""
    try:
        with open(COST, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line
    except Exception:
        pass
    return last


def run(sid=""):
    now = time.time()
    # Which agents have an elapsed cooldown? If none, we stop BEFORE any
    # spending: no sensor regeneration, no LLM call. Cost strictly zero.
    open_agents = [a for a in ORDER if cooldown_ok(a, now)]
    if not open_agents:
        return
    # Quota guard BEFORE spending anything (the same resilience as layer 1).
    # Quota spent → we defer without engraving a cooldown: the watch pass
    # will come round again at the next authenticated SessionEnd, nothing is "burned".
    if guard is not None and not guard.preflight_ok():
        return
    regen_sensors(open_agents)         # only the sensors of eligible agents
    d = decide(now)
    agent = d["chosen"]
    if not agent:
        return                          # capteurs sous le seuil → veille au repos
    claude = shutil.which("claude")
    if not claude:
        return
    reason = d["agents"][agent]["reason"]
    write_status("busy", ACT.get(agent, "gardening"), f"{agent}: {reason}", source="agent")
    cmd = [claude, "-p", "--model", MODEL.get(agent, "sonnet"),
           "--output-format", "json", "--dangerously-skip-permissions",
           "--agent", agent, TASKS[agent]]
    try:
        with open(COST, "a") as cf, open(LOG, "a") as lf:
            subprocess.run(cmd, cwd=BRAIN, stdin=subprocess.DEVNULL,
                           stdout=cf, stderr=lf, timeout=900)
    except Exception:
        return  # best effort: a failed watch pass loses no data
    # ENGRAVE the 12 h cooldown only if the agent REALLY succeeded. A failure
    # quota/login sort en code 0 avec is_error=true (pas d'exception Python) : sans ce
    # guard, we burned 12 h of watch doing nothing. interpret_result also sets the
    # quota/login markers → layer 1 knows to defer next time.
    ok = True
    if guard is not None:
        try:
            ok = guard.interpret_result(_last_cost_line(), sid, is_distill=False)
        except Exception:
            ok = True   # when in doubt we engrave (avoids a loop if interpret breaks)
    if ok:
        record_run(agent, now)


if __name__ == "__main__":
    try:
        arg = sys.argv[1] if len(sys.argv) > 1 else "decide"
        if arg == "run":
            run(sys.argv[2] if len(sys.argv) > 2 else "")
        else:
            print(json.dumps(decide(), ensure_ascii=False, indent=2))
    except Exception:
        pass
    sys.exit(0)
