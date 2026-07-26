#!/usr/bin/env python3
"""coactivation — la MÉMOIRE DE TRAVAIL du cerveau, rendue calculable (Étage 2).

Étage 1 = la carte par le SENS. Étage 2 = le cerveau qui CONSOMME son propre graphe :
on regarde ce qui a réellement été activé ENSEMBLE pendant les sessions (pas les liens déclarés).

Sources : state/recall_log.jsonl ({ts,sid,path,score}) + state/read_log.jsonl ({ts,sid,path}).
  • CO-ACTIVATION : deux fiches surgies/lues dans la MÊME session = liées par l'usage (≠ [[lien]] déclaré).
  • CHALEUR : récence d'activation d'une fiche (décroissance exponentielle) → ce qui est « chaud » maintenant.

Sortie : state/coactivation.json = { heat:{path:0..1}, edges:[[a,b,w],…], hot_session:{sid,paths} }.
Pur stdlib, déterministe, ne lit QUE les fiches qui sont des nœuds de la planète (distillées) —
le corpus froid et les sessions/ sont exclus (ils ne sont pas sur la carte). Sort toujours 0.
"""
import os, sys, json, time, math
from collections import defaultdict

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
RECALL = os.path.join(BRAIN, "state", "recall_log.jsonl")
READ = os.path.join(BRAIN, "state", "read_log.jsonl")
GRAPH = os.path.join(BRAIN, "planet", "graph.json")
OUT = os.path.join(BRAIN, "state", "coactivation.json")

TAU_DAYS = 10.0          # demi-vie ~ de la chaleur (récence)
MAX_SESSION = 25         # une session qui « touche » trop de fiches n'informe pas sur les paires → ignorée
MIN_EDGE = 2.0           # une paire doit co-survenir dans ≥ ce poids cumulé pour compter
TOP_EDGES = 120          # garde les liens d'usage les plus forts (lisibilité)


def node_paths():
    """Les fiches qui sont des nœuds de la planète (file → id). Tout le reste est ignoré."""
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

    # CHALEUR : somme des activations pondérées par la récence (exp decay)
    heat = defaultdict(float)
    last = defaultdict(float)
    for sid, path, ts in events:
        age = max(0.0, now - ts)
        heat[path] += math.exp(-age / tau)
        last[path] = max(last[path], ts)
    hmax = max(heat.values()) if heat else 1.0
    heat_n = {p: round(v / hmax, 4) for p, v in heat.items()}

    # CO-ACTIVATION : paires de fiches vues dans la même session, pondérées par la récence de la session
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
        w = 0.5 + 0.5 * math.exp(-(now - sid_ts[sid]) / tau)   # sessions récentes pèsent plus
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                pair[(ps[i], ps[j])] += w
    edges = [[keep[a], keep[b], round(w, 3)] for (a, b), w in pair.items() if w >= MIN_EDGE]
    edges.sort(key=lambda e: -e[2])
    edges = edges[:TOP_EDGES]

    # session « chaude » courante = la plus récente avec ≥2 fiches sur la carte
    hot_sid = max(sid_ts, key=sid_ts.get) if sid_ts else None
    hot = {"sid": hot_sid, "paths": sorted(by_sid.get(hot_sid, []))} if hot_sid else {}

    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "counts": {"events": len(events), "fiches_chaudes": len(heat_n), "liens_usage": len(edges)},
            "heat": heat_n, "edges": edges, "hot_session": hot,
            "heat_id": {keep[p]: v for p, v in heat_n.items()}}


def main():
    data = compute()
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    if sys.stdout.isatty() or "--show" in sys.argv:
        c = data["counts"]
        print(f"⚡ co-activation : {c['events']} activations · {c['fiches_chaudes']} fiches chaudes · {c['liens_usage']} liens d'usage")
        top = sorted(data["heat"].items(), key=lambda kv: -kv[1])[:8]
        print("  🔥 plus chaudes :")
        for p, v in top:
            print(f"     {v:.2f}  {os.path.basename(p)[:-3]}")
        print("  🔗 liens d'usage forts (co-activés, pas forcément liés en [[…]]) :")
        for a, b, w in data["edges"][:8]:
            print(f"     {w:.1f}  {a}  ⟷  {b}")


if __name__ == "__main__":
    main()
    sys.exit(0)
