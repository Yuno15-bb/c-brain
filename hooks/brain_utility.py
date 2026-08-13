#!/usr/bin/env python3
"""brain_utility — boucle de vérité (H3) : mesure l'UTILITÉ réelle de chaque fiche.

Croise state/recall_log.jsonl (fiches remontées par le rappel) et
state/read_log.jsonl (fiches effectivement lues). En déduit, par fiche :
  - surfaced  : nb de fois remontée par le retriever
  - read      : nb de fois lue
  - hit       : remontée ET lue dans la MÊME session (le rappel a « servi »)
Et range les fiches en catégories actionnables pour le jardinier :
  - 💀 poids mort   : jamais remontée ni lue (candidate archivage — PROPOSITION)
  - 🔇 ignorée      : remontée ≥3× mais jamais lue (desc faible ? faible valeur ?)
  - ⭐ pilier       : beaucoup lue (à garder, peut-être à scinder)

Signal fondé sur l'USAGE, pas l'introspection. Honnêteté : une fiche peut être utile
sans être *lue* (le pointeur en contexte a suffi) → "ignorée" est un indice, pas un verdict.

Usage : brain_utility.py [--json]   (exit 0)
"""
import os, sys, json, glob, time
from collections import defaultdict

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
RECALL = os.path.join(BRAIN, "state", "recall_log.jsonl")
READ = os.path.join(BRAIN, "state", "read_log.jsonl")
DEAD_AGE_DAYS = 30      # une fiche n'est "poids mort" que si elle a au moins cet âge
STRUCTURAL_MAPS = {os.path.join("lessons", "INDEX.md")}


def all_fiches():
    out = {}
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        # la whitelist de zone (1er segment) suffit et est SÛRE : l'ancien `any(part in rel ...)`
        # (substring) excluait à tort les fiches « capsule-… »/« corpus-… ». cf. [[scan-skip-par-segment-pas-substring]]
        if rel == "MEMORY.md" or rel in STRUCTURAL_MAPS:
            continue
        if rel.split(os.sep)[0] in ("projects", "lessons", "life", "meta"):
            out[rel] = os.path.getmtime(p)
    return out


def read_log(path):
    rows = []
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    except Exception:
        pass
    return rows


def main():
    fiches = all_fiches()
    recalls, reads = read_log(RECALL), read_log(READ)

    surfaced = defaultdict(int); read_n = defaultdict(int)
    surf_sids = defaultdict(set); read_sids = defaultdict(set)
    for r in recalls:
        surfaced[r["path"]] += 1; surf_sids[r["path"]].add(r.get("sid", ""))
    for r in reads:
        read_n[r["path"]] += 1; read_sids[r["path"]].add(r.get("sid", ""))

    now = time.time()
    stats = []
    for rel, mtime in fiches.items():
        hits = len((surf_sids[rel] & read_sids[rel]) - {""})
        stats.append({"path": rel, "surfaced": surfaced[rel], "read": read_n[rel],
                      "hits": hits, "age_days": int((now - mtime) / 86400)})

    dead = [s for s in stats if s["surfaced"] == 0 and s["read"] == 0
            and s["age_days"] >= DEAD_AGE_DAYS]
    ignored = [s for s in stats if s["surfaced"] >= 3 and s["read"] == 0]
    pillars = sorted([s for s in stats if s["read"] > 0], key=lambda x: -x["read"])[:5]

    report = {"ts": int(now), "fiches": len(stats),
              "events": {"surfaced": len(recalls), "read": len(reads)},
              "poids_mort": [s["path"] for s in dead],
              "ignorees": [s["path"] for s in ignored],
              "piliers": [{"path": s["path"], "read": s["read"]} for s in pillars]}

    if "--json" in sys.argv:
        os.makedirs(os.path.join(BRAIN, "state"), exist_ok=True)
        json.dump(report, open(os.path.join(BRAIN, "state", "utility.json"), "w"),
                  ensure_ascii=False, indent=2)
        return

    print(f"📊 Utilité — {len(stats)} fiches | {len(recalls)} remontées, {len(reads)} lectures")
    if len(recalls) + len(reads) < 5:
        print("  ⏳ Pas encore assez d'historique d'usage (le signal se construit "
              "au fil des sessions).")
    if pillars:
        print("\n  ⭐ Piliers (les plus lues) :")
        for s in pillars:
            print(f"     {s['read']:3}×  {s['path']}")
    if ignored:
        print("\n  🔇 Remontées mais jamais lues (desc à revoir ?) :")
        for s in ignored[:8]:
            print(f"     {s['surfaced']:3}↑  {s['path']}")
    if dead:
        print(f"\n  💀 Poids mort (jamais remontée ni lue, ≥{DEAD_AGE_DAYS}j) "
              f"→ PROPOSER l'archivage :")
        for s in dead[:8]:
            print(f"        {s['path']}")
    if not (pillars or ignored or dead):
        print("  (rien de notable — l'usage est encore jeune)")


if __name__ == "__main__":
    main()
