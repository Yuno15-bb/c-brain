#!/usr/bin/env python3
"""corpus_embed — embeddings + clustering de la COUCHE FROIDE (cf. carte-vivante-4-etages, Étage 1).

Pipeline (corpus_import → CE SCRIPT → distillation sélective) :
  corpus/cold/**/*.md  →  embeddings model2vec  →  KMeans cosinus  →  corpus/CLUSTERS.md (thèmes)

MÊME modèle que brain_embed.py (potion-base-8M) → corpus froid et fiches chaudes partagent le MÊME
espace vectoriel (on pourra plus tard relier une fiche à ses conversations d'origine). Zéro-dépendance
au-delà du venv du Brain (numpy + model2vec, PAS de sklearn) : KMeans cosinus réimplémenté en numpy.

Sorties (toutes sous corpus/, gitignoré, local-only) :
  • state/corpus_embeddings.npz / .json  → vecteurs + méta (rel, source, title), réutilisable
  • state/corpus_clusters.json           → assignation cluster par conversation
  • corpus/CLUSTERS.md                    → rapport LISIBLE : par cluster = taille, mix source, termes-clés, titres repré.

Usage (dans le venv ~/.c-brain/trunk/.venv) :
  corpus_embed.py [--k N] [--body-cap N]   # build : embeddings + clusters + rapport (k auto ≈ sqrt(n/2))
  corpus_embed.py query [-k N] "..."       # recherche sémantique sur le corpus (canal séparé des fiches)
"""
import os, re, sys, json, glob, argparse, datetime
import numpy as np
from model2vec import StaticModel

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
COLD = os.path.join(BRAIN, "corpus", "cold")
NPZ = os.path.join(BRAIN, "state", "corpus_embeddings.npz")
META = os.path.join(BRAIN, "state", "corpus_embeddings.json")
CLUST = os.path.join(BRAIN, "state", "corpus_clusters.json")
REPORT = os.path.join(BRAIN, "corpus", "CLUSTERS.md")
MODEL = "minishlab/potion-base-8M"          # IDENTIQUE à brain_embed.py

STOP = set("""au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me
même mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton
tu un une vos votre vous c d j l m n s t y est sont être ai as a avons avez ont fait faire plus moins
si comme tout tous cette ça cela donc alors aussi très peu bien encore the a an and are as at be by for
from has have i in is it its of on or that this to was were will with you your we my me he she they them
do does did not no yes can could would should will just like get got make made how what when where why
who which there here then than so up out about into over also their our""".split())
WORD = re.compile(r"[a-zàâäéèêëïîôöùûüç]{3,}", re.I)


def parse_cold(fp):
    """→ (source, title, body_text). Strip frontmatter + icônes de rôle."""
    raw = open(fp, encoding="utf-8").read()
    source, title = "?", os.path.basename(fp)
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            fm, body = raw[3:end], raw[end + 4:]
            for line in fm.splitlines():
                if line.startswith("corpus_source:"):
                    source = line.split(":", 1)[1].strip()
                elif line.startswith("title:"):
                    try:
                        title = json.loads(line.split(":", 1)[1].strip())
                    except Exception:
                        title = line.split(":", 1)[1].strip().strip('"')
    body = re.sub(r"^#+ .*$", "", body, flags=re.M)          # titres markdown / rôles
    body = re.sub(r"```.*?```", " ", body, flags=re.S)         # blocs de code = bruit thématique
    return source, title, body.strip()


def embed_text(title, body, cap):
    # titre pondéré ×3 (signal thématique fort) + extrait de corps borné (model2vec moyenne les tokens)
    return ((title + ". ") * 3) + body[:cap]


def kmeans_cosine(X, k, iters=40, seed=0):
    """KMeans sur vecteurs L2-normalisés (distance cosinus = euclidienne). Numpy pur, déterministe."""
    rng = np.random.default_rng(seed)
    # init k-means++ (cosine)
    n = len(X)
    centers = [X[rng.integers(n)]]
    for _ in range(k - 1):
        d = 1 - (X @ np.array(centers).T).max(axis=1)         # distance au centre le + proche
        d = np.clip(d, 0, None); p = d / (d.sum() + 1e-12)
        centers.append(X[rng.choice(n, p=p)])
    C = np.array(centers)
    assign = np.zeros(n, dtype=int)
    for _ in range(iters):
        sim = X @ C.T
        new = sim.argmax(axis=1)
        if (new == assign).all():
            break
        assign = new
        for j in range(k):
            m = X[assign == j]
            if len(m):
                v = m.sum(axis=0); C[j] = v / (np.linalg.norm(v) + 1e-9)
    return assign, C


def top_terms(docs_tokens, idx, global_df, n_docs, topn=8):
    """Termes saillants d'un cluster : fréquence locale pondérée par rareté globale (TF·IDF-light)."""
    from collections import Counter
    c = Counter()
    for i in idx:
        c.update(set(docs_tokens[i]))                          # présence par doc (pas brut)
    out = []
    for w, df_local in c.most_common(60):
        idf = np.log(n_docs / (1 + global_df.get(w, 1)))
        out.append((w, (df_local / len(idx)) * idf))
    out.sort(key=lambda x: -x[1])
    return [w for w, _ in out[:topn]]


def cmd_query(k, q):
    """Recherche sémantique sur le corpus froid — canal SÉPARÉ des fiches (ne pollue PAS brain_recall :
    1230 convs brutes noieraient les ~85 fiches curées ; cf. pourquoi brain_embed exclut corpus/)."""
    if not os.path.exists(NPZ):
        print("Pas d'index — lance d'abord: corpus_embed.py (build)", file=sys.stderr); return
    meta = json.load(open(META, encoding="utf-8"))
    X = np.load(NPZ)["v"].astype(np.float64)
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    qv = np.asarray(StaticModel.from_pretrained(meta.get("model", MODEL)).encode([q]), dtype=np.float64)[0]
    qv = qv / (np.linalg.norm(qv) + 1e-9)
    sims = X @ qv
    for i in np.argsort(-sims)[:k]:
        print(f"  {sims[i]:.3f}  [{meta['sources'][i]:7}] {meta['titles'][i][:72]}")
        print(f"         {meta['rels'][i]}")


def build(a):
    files = sorted(glob.glob(os.path.join(COLD, "**", "*.md"), recursive=True))
    if not files:
        print("Aucune conversation froide — lance d'abord corpus_import.py", file=sys.stderr); sys.exit(0)

    rels, sources, titles, texts, tokens = [], [], [], [], []
    from collections import Counter
    global_df = Counter()
    for fp in files:
        src, title, body = parse_cold(fp)
        rels.append(os.path.relpath(fp, BRAIN)); sources.append(src); titles.append(title)
        texts.append(embed_text(title, body, a.body_cap))
        tk = [w.lower() for w in WORD.findall(title + " " + body[:a.body_cap]) if w.lower() not in STOP]
        tokens.append(tk); global_df.update(set(tk))

    n = len(files)
    k = a.k or max(12, int((n / 2) ** 0.5))
    print(f"🧮 {n} conversations → embeddings (modèle {MODEL})…")
    model = StaticModel.from_pretrained(MODEL)
    X = np.asarray(model.encode(texts), dtype=np.float64)
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)

    print(f"🔗 KMeans cosinus k={k}…")
    assign, C = kmeans_cosine(X, k)

    # sorties machine
    os.makedirs(os.path.dirname(NPZ), exist_ok=True)
    np.savez_compressed(NPZ, v=X.astype(np.float32))
    json.dump({"model": MODEL, "rels": rels, "sources": sources, "titles": titles},
              open(META, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump({"k": k, "assign": assign.tolist(), "rels": rels},
              open(CLUST, "w", encoding="utf-8"), ensure_ascii=False)

    # rapport lisible : clusters triés par taille
    order = sorted(range(k), key=lambda j: -(assign == j).sum())
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# 🗺️ Corpus froid — {k} clusters thématiques",
         "",
         f"> {n} conversations ({sources.count('claude')} Claude · {sources.count('chatgpt')} ChatGPT) · "
         f"généré {now} · modèle {MODEL}.",
         "> Couche froide, lossless. La distillation en fiches chaudes reste séparée et sélective.",
         ""]
    for rank, j in enumerate(order, 1):
        idx = [i for i in range(n) if assign[i] == j]
        if not idx:
            continue
        nc = sum(1 for i in idx if sources[i] == "claude")
        ng = sum(1 for i in idx if sources[i] == "chatgpt")
        terms = ", ".join(top_terms(tokens, idx, global_df, n))
        sim = X[idx] @ C[j]
        repr_idx = [idx[t] for t in np.argsort(-sim)[:3]]
        L.append(f"## {rank}. ({len(idx)} convs · {nc}C/{ng}G) — {terms}")
        for i in repr_idx:
            L.append(f"- {titles[i][:80]}  ·  *{sources[i]}*")
        L.append("")
    open(REPORT, "w", encoding="utf-8").write("\n".join(L))

    print(f"✅ {k} clusters · rapport → {os.path.relpath(REPORT, BRAIN)} · vecteurs → {os.path.relpath(NPZ, BRAIN)}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "query":
        a = sys.argv[2:]; k = 8
        if "-k" in a:
            i = a.index("-k"); k = int(a[i + 1]); del a[i:i + 2]
        cmd_query(k, " ".join(a)); return
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=0, help="nb clusters (0 = auto ≈ sqrt(n/2))")
    ap.add_argument("--body-cap", type=int, default=4000)
    build(ap.parse_args())


if __name__ == "__main__":
    main()
    sys.exit(0)
