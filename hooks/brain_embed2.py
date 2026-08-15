#!/usr/bin/env python3
"""brain_embed2 — projette les embeddings du Brain en 2D SÉMANTIQUE (Étage 1 de la carte vivante).

But : une carte où la proximité = le SENS (contenu), pas le rangement déclaré (dossiers + [[liens]]).
Deux fiches qui parlent de la même chose sans aucun lien doivent se retrouver voisines.

Backend ZÉRO-DÉPENDANCE (numpy seul, comme tout le venv du Brain — pas de umap/sklearn/scipy) :
  1. seed PCA (SVD top-DIM) → repère global stable et déterministe ;
  2. raffinement force-dirigé (Fruchterman-Reingold) sur le graphe des k plus proches voisins COSINUS
     → attire le sens proche, repousse le reste → les clusters se séparent (mieux que PCA seule).

Entrée : state/embeddings.{npz,json} (produit par brain_embed.py build).
Sortie : state/embed2.json = { generated_at, method, pos: { "<rel_path>": [x, y] } }  (x,y ~ dans [-1,1]).
graph_export.py lit ce cache SANS dépendance et attache node["embed2"]. planet/index.html : mode « S ».

Usage (dans le venv) :  brain_embed2.py            → calcule et écrit le cache
                        brain_embed2.py --probe N  → + imprime, pour N fiches, voisins sémantiques vs région
"""
import os, sys, json, time
import numpy as np

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
NPZ = os.path.join(BRAIN, "state", "embeddings.npz")
META = os.path.join(BRAIN, "state", "embeddings.json")
OUT = os.path.join(BRAIN, "state", "embed2.json")

K_NEIGHBORS = 8        # voisins cosinus attractifs par fiche
ITERS = 500            # itérations du raffinement force-dirigé
SEED_STD = 0.30        # échelle du seed PCA


def load():
    meta = json.load(open(META, encoding="utf-8"))
    vecs = np.load(NPZ)["v"].astype(np.float64)
    return meta, vecs


def normalize_rows(m):
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)


# La carte du SENS sort désormais en TROIS dimensions (2026-08-14, demande de l'auteur :
# « "sens" aussi doit faire un amas 3D harmonieux »). Elle était plate parce qu'elle était née
# comme une carte 2D à comparer côte à côte avec la carte de structure ; à plat, 357 fiches et
# 1386 liens se superposent et redonnent la pelote qu'on vient d'éliminer ailleurs. En volume,
# les groupes se séparent au lieu de se recouvrir, et on tourne autour.
# Le force-layout est déjà générique (opérations vectorielles sur la dernière dimension) :
# passer de 2 à 3 colonnes ne change rien à sa logique, seulement au nombre de degrés de liberté.
DIM = 3


def pca_init(vn):
    """Seed déterministe : DIM premières composantes principales (SVD), signe fixé."""
    x = vn - vn.mean(axis=0, keepdims=True)
    # SVD : x = U S Vt ; les scores = U[:, :DIM] * S[:DIM]
    u, s, _ = np.linalg.svd(x, full_matrices=False)
    p = u[:, :DIM] * s[:DIM]
    # signe déterministe : la composante de plus grande amplitude est positive
    for j in range(DIM):
        if p[np.argmax(np.abs(p[:, j])), j] < 0:
            p[:, j] = -p[:, j]
    # normalise l'échelle du seed (std cible) pour démarrer le force-layout proprement
    p = p / (p.std() + 1e-9) * SEED_STD
    return p


# Cohésion de FAMILLE (2026-08-14, l'auteur sur capture : « les couleurs doivent être plus
# sectionnées en familles distinctes, mais l'amas doit rester à peu près comme il est, avec des
# séparations qui se remarquent malgré l'amas »).
# Le layout ne connaissait QUE le sens : deux fiches proches sémantiquement se collaient, quelle
# que soit leur région, donc les couleurs se mêlaient uniformément et aucune famille ne se lisait.
# On ajoute une attraction FAIBLE entre fiches de la même région, en PLUS de l'attraction
# sémantique. Faible, c'est le mot : trop forte, elle referait les paquets par dossier et
# effacerait ce que la vue du sens sert à montrer — les voisinages qui traversent les régions.
# RÉGLÉE PAR BALAYAGE, pas au jugé. Indicateur : distance moyenne ENTRE centres de famille
# divisée par la dispersion INTERNE moyenne (>1 = les familles se distinguent).
#     0.0 → 0.97  les couleurs sont mêlées, aucune famille lisible (l'état d'avant)
#     0.6 → 2.20  familles nettes, l'amas garde 73 % de son étalement
#     1.8 → 3.15  familles nettes mais repliées en boules serrées : l'amas est perdu
# 0.6 tient les deux moitiés de la demande : « sectionné en familles distinctes » ET
# « l'amas doit rester à peu près comme il est ».
COHESION = 0.6   # réglé par balayage mesuré, cf. plus bas


def region_de(path):
    """La famille d'une fiche = son premier dossier ; projects/<x>/ compte comme sa propre famille."""
    parts = path.replace("\\", "/").split("/")
    if parts[0] == "projects" and len(parts) > 2:
        return "projects/" + parts[1]
    return parts[0]


def family_weights(meta):
    """Attraction douce, uniforme, entre membres d'une même famille — normalisée par sa taille
    pour qu'une famille de 170 fiches ne s'écrase pas en un point pendant qu'une famille de 2
    reste libre."""
    fam = [region_de(m["path"]) for m in meta]
    n = len(fam)
    w = np.zeros((n, n))
    from collections import defaultdict
    par = defaultdict(list)
    for i, f in enumerate(fam):
        par[f].append(i)
    for membres in par.values():
        if len(membres) < 2:
            continue
        idx = np.array(membres)
        w[np.ix_(idx, idx)] = COHESION / np.sqrt(len(membres))
    np.fill_diagonal(w, 0.0)
    return w


def neighbor_weights(vn, k):
    """Matrice d'attraction symétrique W : poids = cosinus pour les k plus proches voisins."""
    sims = vn @ vn.T
    np.fill_diagonal(sims, -1.0)
    n = len(vn)
    w = np.zeros((n, n))
    idx = np.argsort(-sims, axis=1)[:, :k]
    for i in range(n):
        for j in idx[i]:
            s = max(sims[i, j], 0.0)
            w[i, j] = max(w[i, j], s)
            w[j, i] = max(w[j, i], s)   # symétrise (voisinage non orienté)
    return w


def fr_layout(p, w, iters):
    """Fruchterman-Reingold pondéré : répulsion globale + attraction des voisins (poids = sens)."""
    n = len(p)
    k = np.sqrt(1.0 / n)                 # distance idéale (aire unité / n)
    temp = 0.10
    cool = 0.985
    eps = 1e-9
    for _ in range(iters):
        diff = p[:, None, :] - p[None, :, :]          # n×n×DIM
        dist = np.sqrt((diff * diff).sum(-1)) + eps   # n×n
        unit = diff / dist[..., None]
        rep = (k * k / dist)[..., None] * unit         # répulsion ∝ k²/d
        att = (dist * dist / k * w)[..., None] * unit  # attraction voisins ∝ d²/k · poids
        disp = (rep - att).sum(axis=1)                 # somme sur j
        dlen = np.sqrt((disp * disp).sum(-1)) + eps
        p = p + disp / dlen[:, None] * np.minimum(dlen, temp)[:, None]
        temp *= cool
    return p


def to_unit(p):
    """Centre + met à l'échelle dans la BOULE unité (max rayon = 1) pour un espace stable côté JS."""
    p = p - p.mean(axis=0, keepdims=True)
    r = np.sqrt((p * p).sum(-1)).max() or 1.0
    return p / r


def compute():
    meta, vecs = load()
    vn = normalize_rows(vecs)
    p = pca_init(vn)
    w = neighbor_weights(vn, K_NEIGHBORS) + family_weights(meta)
    p = fr_layout(p, w, ITERS)
    p = to_unit(p)
    pos = {meta[i]["path"]: [round(float(p[i, j]), 4) for j in range(DIM)]
           for i in range(len(meta))}
    return meta, vn, pos


def write(pos):
    data = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "dim": DIM, "method": f"pca-seed + cosine-kNN + cohesion-famille({COHESION}) force-layout {DIM}D (numpy)", "pos": pos}
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)


def probe(meta, vn, n_show):
    """Test de l'étage 1 : pour quelques fiches, voisins SÉMANTIQUES (révélés par le sens)."""
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
    print(f"\n🔎 ÉTAGE 1 — voisinages SÉMANTIQUES (région entre [ ]) :")
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
    print(f"🗺️  carte sémantique : {len(pos)} fiches → {os.path.relpath(OUT, BRAIN)}")
    if "--probe" in sys.argv:
        i = sys.argv.index("--probe")
        n = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 8
        probe(meta, vn, n)


if __name__ == "__main__":
    main()
