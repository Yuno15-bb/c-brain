#!/usr/bin/env python3
"""coactivation — the brain's WORKING MEMORY, made computable.

One layer maps by MEANING. This layer is the brain CONSUMING its own graph:
we look at what was actually activated TOGETHER during sessions (not the declared links).

Sources : state/recall_log.jsonl ({ts,sid,path,score}) + state/read_log.jsonl ({ts,sid,path}).
  • CO-ACTIVATION: two notes surfaced/read in the SAME session = linked by usage (not a declared [[link]]).
  • HEAT: how recently a note was activated (exponential decay) → what is "hot" right now.

Sortie : state/coactivation.json = { heat:{path:0..1}, edges:[[a,b,w],…], hot_session:{sid,paths} }.
Pure stdlib, deterministic, reads ONLY the notes that are planet nodes (distilled) —
le corpus froid et les sessions/ sont exclus (ils ne sont pas sur la carte). Sort toujours 0.
"""
import os, sys, json, time, math
from collections import defaultdict

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
RECALL = os.path.join(BRAIN, "state", "recall_log.jsonl")
READ = os.path.join(BRAIN, "state", "read_log.jsonl")
GRAPH = os.path.join(BRAIN, "planet", "graph.json")
OUT = os.path.join(BRAIN, "state", "coactivation.json")

TAU_DAYS = 10.0          # approximate half-life of heat (recency)
MAX_SESSION = 25         # a session "touching" too many notes says nothing about pairs → ignored
MIN_EDGE = 2.0           # a pair must co-occur with at least this cumulative weight to count
TOP_EDGES = 120          # keep the strongest usage links (readability)


def node_paths():
    """The notes that are planet nodes (file → id). Everything else is ignored."""
    try:
        g = json.load(open(GRAPH, encoding="utf-8"))
        return {n["file"]: n["id"] for n in g["nodes"]}
    except Exception:
        return {}


def read_events(path, keep):
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("path") in keep and e.get("sid"):
            out.append((e["sid"], e["path"], float(e.get("ts", 0))))
    return out


def compute():
    keep = node_paths()
    events = read_events(RECALL, keep) + read_events(READ, keep)
    now = time.time()
    tau = TAU_DAYS * 86400.0

    # HEAT: sum of activations weighted by recency (exponential decay)
    heat = defaultdict(float)
    last = defaultdict(float)
    for sid, path, ts in events:
        age = max(0.0, now - ts)
        heat[path] += math.exp(-age / tau)
        last[path] = max(last[path], ts)
    hmax = max(heat.values()) if heat else 1.0
    heat_n = {p: round(v / hmax, 4) for p, v in heat.items()}

    # CO-ACTIVATION: pairs of notes seen in the same session, weighted by the session's recency
    by_sid = defaultdict(set)
    sid_ts = defaultdict(float)
    for sid, path, ts in events:
        by_sid[sid].add(path)
        sid_ts[sid] = max(sid_ts[sid], ts)
    pair = defaultdict(float)
    for sid, paths in by_sid.items():
        ps = sorted(paths)
        if len(ps) < 2 or len(ps) > MAX_SESSION:
            continue
        w = 0.5 + 0.5 * math.exp(-(now - sid_ts[sid]) / tau)   # recent sessions weigh more
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                pair[(ps[i], ps[j])] += w
    edges = [[keep[a], keep[b], round(w, 3)] for (a, b), w in pair.items() if w >= MIN_EDGE]
    edges.sort(key=lambda e: -e[2])
    edges = edges[:TOP_EDGES]

    # current "hot" session = the most recent one with ≥2 notes on the map
    hot_sid = max(sid_ts, key=sid_ts.get) if sid_ts else None
    hot = {"sid": hot_sid, "paths": sorted(by_sid.get(hot_sid, []))} if hot_sid else {}

    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "counts": {"events": len(events), "hot_notes": len(heat_n), "usage_links": len(edges)},
            "heat": heat_n, "edges": edges, "hot_session": hot,
            "heat_id": {keep[p]: v for p, v in heat_n.items()}}


def main():
    data = compute()
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    if sys.stdout.isatty() or "--show" in sys.argv:
        c = data["counts"]
        print(f"⚡ co-activation: {c['events']} activations · {c['hot_notes']} hot notes · {c['usage_links']} usage links d'usage")
        top = sorted(data["heat"].items(), key=lambda kv: -kv[1])[:8]
        print("  🔥 hottest:")
        for p, v in top:
            print(f"     {v:.2f}  {os.path.basename(p)[:-3]}")
        print("  🔗 strong usage links (co-activated, not necessarily linked with [[…]]):")
        for a, b, w in data["edges"][:8]:
            print(f"     {w:.1f}  {a}  ⟷  {b}")


if __name__ == "__main__":
    main()
    sys.exit(0)
