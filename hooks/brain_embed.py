#!/usr/bin/env python3
"""brain_embed — backend embeddings local (Volet 2 · Horizon 1, upgrade « vrai sémantique »).

Tourne dans le venv ~/claude-brain/.venv (model2vec + numpy, SANS PyTorch).
Embeddings STATIQUES : modèle ~30 Mo, encodage instantané (0.001s), zéro API, hors-ligne.

Index sur disque INCRÉMENTAL (state/embeddings.npz + .json) : on ne ré-encode que les
fiches modifiées (hash du contenu). brain_recall y délègue en mode --semantic ;
le défaut reste BM25 (instantané) pour le hook à chaque message.

Usage (dans le venv) :
  brain_embed.py build              → (re)construit l'index incrémental
  brain_embed.py query [-k N] "..." → top-k par similarité sémantique
"""
import os, sys, re, json, glob, hashlib
import numpy as np
from model2vec import StaticModel

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
NPZ = os.path.join(BRAIN, "state", "embeddings.npz")
META = os.path.join(BRAIN, "state", "embeddings.json")
MODEL = "minishlab/potion-base-8M"
# dossiers à ignorer — matchés sur les SEGMENTS de chemin (pas en substring :
# sinon une fiche nommée « capsule-… » serait exclue à tort de l'index). cf. fix 2026-06-27
# IMPORTANT : MÊME corpus que brain_recall (BM25) — sinon les deux backends ne voient pas les mêmes
# fiches. On exclut TOUT sessions/ (TIMELINE.md = index de 130+ sessions → matche presque tout = bruit),
# pas seulement l'archive. cf. [[bm25-recall-exclure-index-catalogues]]
SKIP_DIRS = {".git", "node_modules", "capsule", "corpus", "audits"}
SKIP_PREFIX = ("sessions",)


def _skip(rel):
    if rel == "MEMORY.md" or any(rel.startswith(p) for p in SKIP_PREFIX):
        return True
    dirs = rel.split(os.sep)[:-1]               # segments de DOSSIER (hors nom de fichier)
    return any(d in SKIP_DIRS for d in dirs)

_model = None
def model():
    global _model
    if _model is None:
        _model = StaticModel.from_pretrained(MODEL)
    return _model


def fiche_text(raw):
    fm = re.match(r"^---\n(.*?)\n---", raw, re.S)
    name = desc = ""
    if fm:
        mn = re.search(r"^name:\s*(.+)$", fm.group(1), re.M)
        md = re.search(r'^description:\s*"?(.+?)"?\s*$', fm.group(1), re.M)
        name = mn.group(1).strip() if mn else ""
        desc = md.group(1).strip() if md else ""
    body = re.sub(r"```.*?```", " ", raw, flags=re.S)
    body = re.sub(r"^---\n.*?\n---", "", body, flags=re.S)
    # nom + description en tête (signal dense) puis corps tronqué
    return (name + ". " + desc + ". " + body)[:4000], name, desc


def fiches():
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        if _skip(rel):
            continue
        try:
            raw = open(p, encoding="utf-8").read()
        except Exception:
            continue
        yield rel, raw


def load_index():
    try:
        meta = json.load(open(META, encoding="utf-8"))
        vecs = np.load(NPZ)["v"]
        return meta, vecs
    except Exception:
        return [], None


def build():
    meta, vecs = load_index()
    cache = {m["path"]: (m["hash"], i) for i, m in enumerate(meta)} if vecs is not None else {}
    new_meta, rows, to_encode, enc_idx = [], [], [], []
    for rel, raw in fiches():
        h = hashlib.sha256(raw.encode()).hexdigest()[:16]
        text, name, desc = fiche_text(raw)
        new_meta.append({"path": rel, "name": name or os.path.basename(rel)[:-3],
                         "desc": desc, "hash": h})
        if rel in cache and cache[rel][0] == h:           # inchangée → réutilise le vecteur
            rows.append(vecs[cache[rel][1]])
        else:                                              # nouvelle / modifiée → à encoder
            rows.append(None); to_encode.append(text); enc_idx.append(len(rows) - 1)
    if to_encode:
        encoded = model().encode(to_encode)
        for j, i in enumerate(enc_idx):
            rows[i] = encoded[j]
    mat = np.vstack(rows).astype(np.float32)
    os.makedirs(os.path.dirname(NPZ), exist_ok=True)
    np.savez_compressed(NPZ, v=mat)
    json.dump(new_meta, open(META, "w", encoding="utf-8"), ensure_ascii=False)
    return len(new_meta), len(to_encode)


def query(q, k=5):
    meta, vecs = load_index()
    if vecs is None or len(meta) != len(vecs):
        build(); meta, vecs = load_index()
    qv = model().encode([q])[0].astype(np.float32)
    qn = qv / (np.linalg.norm(qv) or 1)
    vn = vecs / (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
    sims = vn @ qn
    order = np.argsort(-sims)[:k]
    return [(float(sims[i]), meta[i]) for i in order]


def main():
    args = sys.argv[1:]
    if args and args[0] == "build":
        n, enc = build()
        print(f"✅ index embeddings : {n} fiches ({enc} (ré)encodées)")
        return
    if args and args[0] == "query":
        args = args[1:]
        k = 5
        if "-k" in args:
            i = args.index("-k"); k = int(args[i + 1]); del args[i:i + 2]
        as_json = "--json" in args
        if as_json: args.remove("--json")
        q = " ".join(args).strip()
        res = query(q, k)
        if as_json:
            print(json.dumps([{"path": m["path"], "name": m["name"], "desc": m["desc"],
                               "score": round(s, 3)} for s, m in res], ensure_ascii=False))
        else:
            print(f"🔎 (sémantique) Top {len(res)} pour « {q} » :\n")
            for s, m in res:
                print(f"  [{s:5.3f}] {m['name']}  ({m['path']})")
                if m["desc"]: print(f"          {m['desc'][:110]}")
        return
    print("Usage : brain_embed.py build | query [-k N] \"...\"")


if __name__ == "__main__":
    main()
