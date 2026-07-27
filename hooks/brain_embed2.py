#!/usr/bin/env python3
"""brain_embed2 — projects the trunk embeddings into a SEMANTIC 2D map.

Goal: a map where proximity means MEANING (content), not declared filing (folders + [[links]]).
Two notes about the same thing, with no link between them, must end up neighbours.

ZERO-DEPENDENCY backend (numpy alone — no umap/sklearn/scipy):
  1. PCA seed (top-2 SVD) → a stable, deterministic global frame;
  2. force-directed refinement (Fruchterman-Reingold) on the k-nearest-neighbour COSINE graph
     → pulls close meaning together, pushes the rest apart → clusters separate (better than PCA alone).

Input: state/embeddings.{npz,json} (produced by brain_embed.py build).
Sortie : state/embed2.json = { generated_at, method, pos: { "<rel_path>": [x, y] } }  (x,y ~ dans [-1,1]).
graph_export.py reads this cache with NO dependency and attaches node["embed2"]. planet/index.html: mode "S".

Usage (inside the venv):  brain_embed2.py            → computes and writes the cache
                          brain_embed2.py --probe N  → also prints, for N notes, semantic neighbours vs region
"""
import os, sys, json, time
import numpy as np

BRAIN = os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))
NPZ = os.path.join(BRAIN, "state", "embeddings.npz")
META = os.path.join(BRAIN, "state", "embeddings.json")
OUT = os.path.join(BRAIN, "state", "embed2.json")

K_NEIGHBORS = 8        # voisins cosinus attractifs par fiche
ITERS = 500            # iterations of the force-directed refinement
SEED_STD = 0.30        # scale of the PCA seed


def load():
    meta = json.load(open(META, encoding="utf-8"))
    vecs = np.load(NPZ)["v"].astype(np.float64)
    return meta, vecs


def normalize_rows(m):
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


def pca_init(vn):
    """Deterministic seed: the first two principal components (SVD), sign pinned."""
    x = vn - vn.mean(axis=0, keepdims=True)
    # SVD : x = U S Vt ; les scores 2D = U[:, :2] * S[:2]
    u, s, _ = np.linalg.svd(x, full_matrices=False)
    p = u[:, :2] * s[:2]
    # deterministic sign: the largest-amplitude component is made positive
    for j in range(2):
        if p[np.argmax(np.abs(p[:, j])), j] < 0:
            p[:, j] = -p[:, j]
    # normalize the seed's scale (target std) so the force layout starts cleanly
    p = p / (p.std() + 1e-9) * SEED_STD
    return p


def neighbor_weights(vn, k):
    """Symmetric attraction matrix W: weight = cosine for the k nearest neighbours."""
    sims = vn @ vn.T
    np.fill_diagonal(sims, -1.0)
    n = len(vn)
    w = np.zeros((n, n))
    idx = np.argsort(-sims, axis=1)[:, :k]
    for i in range(n):
        for j in idx[i]:
            s = max(sims[i, j], 0.0)
            w[i, j] = max(w[i, j], s)
            w[j, i] = max(w[j, i], s)   # symmetrize (undirected neighbourhood)
    return w


def fr_layout(p, w, iters):
    """Weighted Fruchterman-Reingold: global repulsion + neighbour attraction (weight = meaning)."""
    n = len(p)
    k = np.sqrt(1.0 / n)                 # ideal distance (unit area / n)
    temp = 0.10
    cool = 0.985
    eps = 1e-9
    for _ in range(iters):
        diff = p[:, None, :] - p[None, :, :]          # n×n×2
        dist = np.sqrt((diff * diff).sum(-1)) + eps   # n×n
        unit = diff / dist[..., None]
        rep = (k * k / dist)[..., None] * unit         # repulsion ∝ k²/d
        att = (dist * dist / k * w)[..., None] * unit  # attraction voisins ∝ d²/k · poids
        disp = (rep - att).sum(axis=1)                 # somme sur j
        dlen = np.sqrt((disp * disp).sum(-1)) + eps
        p = p + disp / dlen[:, None] * np.minimum(dlen, temp)[:, None]
        temp *= cool
    return p


def to_unit(p):
    """Centres + scales into the unit disc (max radius 1) for a stable space on the JS side."""
    p = p - p.mean(axis=0, keepdims=True)
    r = np.sqrt((p * p).sum(-1)).max() or 1.0
    return p / r


def compute():
    meta, vecs = load()
    vn = normalize_rows(vecs)
    p = pca_init(vn)
    w = neighbor_weights(vn, K_NEIGHBORS)
    p = fr_layout(p, w, ITERS)
    p = to_unit(p)
    pos = {meta[i]["path"]: [round(float(p[i, 0]), 4), round(float(p[i, 1]), 4)] for i in range(len(meta))}
    return meta, vn, pos


def write(pos):
    data = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "method": "pca-seed + cosine-kNN force-layout (numpy)", "pos": pos}
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)


def probe(meta, vn, n_show):
    """A probe: for a few notes, their SEMANTIC neighbours (revealed by meaning)."""
    sims = vn @ vn.T
    np.fill_diagonal(sims, -1.0)
    reg = {}
    try:
        g = json.load(open(os.path.join(BRAIN, "planet", "graph.json"), encoding="utf-8"))
        for nd in g["nodes"]:
            reg[nd["file"]] = nd.get("primary_project") or nd.get("domain")
    except Exception:
        pass
    paths = [m["path"] for m in meta]
    pick = [p for p in paths if reg.get(p)][:n_show]
    print(f"\n🔎 SEMANTIC neighbourhoods (region in [ ]):")
    for pth in pick:
        i = paths.index(pth)
        order = np.argsort(-sims[i])[:4]
        me = f"[{reg.get(pth,'?')}] {meta[i]['name']}"
        print(f"\n  {me}")
        for j in order:
            cross = "  ⟂CROSS" if reg.get(paths[j]) != reg.get(pth) else ""
            print(f"     {sims[i,j]:.3f}  [{reg.get(paths[j],'?')}] {meta[j]['name']}{cross}")


def main():
    meta, vn, pos = compute()
    write(pos)
    print(f"🗺️  semantic map: {len(pos)} notes → {os.path.relpath(OUT, BRAIN)}")
    if "--probe" in sys.argv:
        i = sys.argv.index("--probe")
        n = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 8
        probe(meta, vn, n)


if __name__ == "__main__":
    main()
