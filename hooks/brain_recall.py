#!/usr/bin/env python3
"""brain_recall — relevance retrieval inside the trunk.

The FOUNDATION of semantic recall: instead of loading all of MEMORY.md on every
session, we retrieve the top-k RELEVANT notes for a query.

Default backend = lexical BM25 (pure Python, ZERO dependencies, ZERO API, instant).
Architecture enfichable : un backend `Embedding` (sentence-transformers local) pourra
replace or complement BM25 without touching the caller — that is the "true semantic" upgrade.

Usage :
  brain_recall.py "rotation main capteur profondeur"        → top-k fiches
  brain_recall.py -k 8 "billing AI costs"
  brain_recall.py --json "..."                              → sortie machine
"""
import os, re, sys, json, math, glob, unicodedata
from collections import Counter

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
# the RAW/infra layers are excluded from recall — recall must surface DISTILLED knowledge
# (projects/lessons/meta/life/agents), pas l'archive ni le corpus froid des 4 comptes.
#   • sessions/ : TIMELINE.md = index de 80+ sessions, si long qu'il matche presque tout → bruit.
#   • corpus/   : the cold layer (thousands of imported conversations) → would drown the top-k.
# Matched on folder SEGMENTS (not substrings: otherwise a note named "capsule-…" or "…-sessions"
# would be wrongly excluded, which is exactly the old bug).
SKIP_DIRS = {".git", "node_modules", "capsule", "corpus", "audits"}
SKIP_PREFIX = ("sessions",)


def _skip(rel):
    if rel == "MEMORY.md" or any(rel.startswith(p) for p in SKIP_PREFIX):
        return True
    dirs = rel.split(os.sep)[:-1]               # segments de DOSSIER (hors nom de fichier)
    return any(d in SKIP_DIRS for d in dirs)
STOP = set("""
au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me meme
mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi
ton tu un une vos votre vous c d j l m n s t y est sont a as ai ont pas plus tres etre fait
le la les un une que qui pour dans sur avec sans est the and for with not are was you your
""".split())


def fold(s):
    """lowercase + accent-stripped (so 'résumé' matches 'resume')."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tokenize(text):
    return [t for t in re.findall(r"[a-z0-9]+", fold(text)) if len(t) > 2 and t not in STOP]


def strip_md(text):
    text = re.sub(r"^---\n.*?\n---", "", text, flags=re.S)   # frontmatter
    text = re.sub(r"```.*?```", " ", text, flags=re.S)        # blocs code
    return text


def load_corpus():
    docs = []
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        if _skip(rel):
            continue
        try:
            raw = open(p, encoding="utf-8").read()
        except Exception:
            continue
        fm = re.match(r"^---\n(.*?)\n---", raw, re.S)
        name = re.search(r"^name:\s*(.+)$", fm.group(1), re.M) if fm else None
        desc = re.search(r'^description:\s*"?(.+?)"?\s*$', fm.group(1), re.M) if fm else None
        body = strip_md(raw)
        # title/description weigh more (×3): the densest signal
        boosted = ((name.group(1) + " ") * 3 if name else "") + \
                  ((desc.group(1) + " ") * 3 if desc else "") + body
        docs.append({
            "path": rel,
            "name": name.group(1).strip() if name else os.path.basename(rel)[:-3],
            "desc": desc.group(1).strip() if desc else "",
            "tokens": tokenize(boosted),
        })
    return docs


class BM25:
    """Lexical backend — Okapi BM25. Swappable for an embeddings backend."""
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.N = len(docs)
        self.dl = [len(d["tokens"]) for d in docs]
        self.avgdl = (sum(self.dl) / self.N) if self.N else 0
        self.tf = [Counter(d["tokens"]) for d in docs]
        df = Counter()
        for d in docs:
            for t in set(d["tokens"]):
                df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def search(self, query, k=5):
        q = tokenize(query)
        scored = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                if t not in self.tf[i]:
                    continue
                f = self.tf[i][t]
                denom = f + self.k1 * (1 - self.b + self.b * self.dl[i] / (self.avgdl or 1))
                s += self.idf.get(t, 0) * (f * (self.k1 + 1)) / denom
            if s > 0:
                scored.append((s, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:k]


def main():
    args = [a for a in sys.argv[1:]]

    # --semantic mode: delegates to the embeddings backend (venv model2vec) when available.
    # Default = BM25 (instant, and better than static embeddings at small scale).
    if "--semantic" in args:
        args.remove("--semantic")
        venv_py = os.path.join(BRAIN, ".venv", "bin", "python")
        embed = os.path.join(BRAIN, "hooks", "brain_embed.py")
        if os.path.exists(venv_py) and os.path.exists(embed):
            import subprocess
            os.execv(venv_py, [venv_py, embed, "query"] + args)
        # sinon : repli silencieux sur BM25

    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    k = 5
    if "-k" in args:
        i = args.index("-k")
        try:
            k = int(args[i + 1]); del args[i:i + 2]
        except Exception:
            pass
    query = " ".join(args).strip()
    if not query:
        print('Usage: brain_recall.py [-k N] [--json] "your query"'); sys.exit(1)

    results = BM25(load_corpus()).search(query, k)
    if as_json:
        print(json.dumps([{"path": d["path"], "name": d["name"],
                           "desc": d["desc"], "score": round(s, 3)}
                          for s, d in results], ensure_ascii=False, indent=2))
        return
    if not results:
        print(f"No relevant note for: {query}"); return
    print(f"🔎 Top {len(results)} for '{query}':\n")
    for s, d in results:
        print(f"  [{s:5.2f}] {d['name']}  ({d['path']})")
        if d["desc"]:
            print(f"          {d['desc'][:110]}")


if __name__ == "__main__":
    main()
