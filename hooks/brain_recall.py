#!/usr/bin/env python3
"""brain_recall — récupération par pertinence dans le C Brain (Volet 2 · Horizon 1).

FONDATION du rappel sémantique : au lieu de charger MEMORY.md en entier à chaque
session, on récupère le top-k des fiches PERTINENTES pour une requête.

Backend v0 = BM25 lexical (pur Python, ZÉRO dépendance, ZÉRO API, instantané).
Architecture enfichable : un backend `Embedding` (sentence-transformers local) pourra
remplacer/compléter BM25 sans toucher l'appelant — c'est l'upgrade « vrai sémantique ».

Usage :
  brain_recall.py "rotation main capteur profondeur"        → top-k fiches
  brain_recall.py -k 8 "facturation coûts IA"
  brain_recall.py --json "..."                              → sortie machine
"""
import os, re, sys, json, math, glob, hashlib, unicodedata
from collections import Counter

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
# on exclut du recall les couches BRUTES/infra — le recall doit remonter le savoir DISTILLÉ
# (projects/lessons/meta/life), pas les catalogues d'agents, l'état ni le corpus froid.
#   • sessions/ : TIMELINE.md = index de 80+ sessions, si long qu'il matche presque tout → bruit.
#   • corpus/   : couche froide (milliers de conversations importées) → noierait le top-k. cf. carte-vivante
# Matché par SEGMENTS de dossier (pas en substring : sinon une fiche « capsule-… » ou « …-sessions »
# serait exclue à tort, comme l'ancien bug). cf. [[bm25-recall-exclure-index-catalogues]]
#   • tools/    : outillage. Le banc de valeur y garde des COPIES du tronc pour ses
#     conditions ; sans cette exclusion chaque fiche était indexée 5 fois (1 573 docs
#     au lieu de 312), ce qui fausse l'IDF de tout le corpus et donc tous les scores.
SKIP_DIRS = {
    ".git", "node_modules", "capsule", "capsule-v2", "corpus", "audits",
    "agents", "state", "tools",
}
SKIP_PREFIX = ("sessions",)
SKIP_FILES = {"MEMORY.md", os.path.join("lessons", "INDEX.md")}


def _skip(rel):
    if rel in SKIP_FILES or any(rel.startswith(p) for p in SKIP_PREFIX):
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
    """minuscule + sans accents (robustesse FR : 'résumé' ~ 'resume')."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# Racinisation légère du français. Sans elle, « ranger » et « rangement » sont deux
# tokens étrangers l'un à l'autre : la requête « comment ranger une fiche du brain » ne
# touchait pas jardinage-regles.md, dont la description dit « rangement ». BM25 ne ratait
# pas la fiche par manque de finesse, il la ratait par absence de recouvrement lexical.
#
# Deux temps, et l'ordre est le cœur du correctif :
#   1. le PLURIEL d'abord, sinon « fiche » et « fiches » ne se rejoignent jamais
#      (« fiches » tombait sur la règle -es et donnait « fich », « fiche » restait
#      « fiche ») — c'est le mot le plus fréquent du tronc, le rater ruine tout ;
#   2. puis UN SEUL suffixe, du plus long au plus court, et seulement si la racine
#      garde au moins 4 lettres.
# Volontairement conservateur : un stemmer gourmand fabrique des collisions silencieuses
# qui abîment toutes les autres requêtes. Les suffixes ambigus sont donc absents — -re
# donnait « mesure » → « mesu », -es et -ee font doublon avec l'étape 1.
_SUFFIXES = sorted((
    "issement", "ellement", "ications", "ication", "atrice", "ateur", "ation",
    "ement", "ance", "ence", "isme", "iste", "euse", "able", "ible", "aire",
    "ite", "ive", "age", "ure", "eur",
    # formes verbales courantes
    "eraient", "erions", "assent", "erais", "erait", "erons", "eront", "aient",
    "ant", "ent", "ons", "ier", "ez", "er", "ir",
), key=len, reverse=True)
_MIN_RACINE = 4          # en dessous, la racine ne veut plus rien dire


def stem(t):
    if len(t) <= 4:
        return t
    # Pluriel : le « s » seulement. Retirer un « x » final visait les pluriels
    # français en -aux/-eux, mais le tronc est bilingue et ça MUTILE les mots
    # anglais : « outbox » → « outbo », « index » → « inde ». Le gain sur
    # « journaux » ne vaut pas ce dégât ; attrapé par tests/recall_cache.py du
    # paquet, que mes propres essais n'avaient pas vu.
    if t.endswith("s") and len(t) > 4:             # 1. pluriel
        t = t[:-1]
    for suf in _SUFFIXES:                          # 2. un seul suffixe
        if t.endswith(suf) and len(t) - len(suf) >= _MIN_RACINE:
            return t[: -len(suf)]
    return t


# Alias français ↔ anglais. Le tronc est écrit dans les deux langues : « offline » est
# dans 37 fiches, « queue » dans 27, « deploy » dans 54 — mais on tape « hors ligne »,
# « file d'attente », « déploiement ». AUCUN stemmer ne franchit une TRADUCTION : mesuré,
# « l app terrain plante hors ligne » laissait offline-first-queue-pattern au-delà du
# rang 20 avec ou sans racinisation ; avec ces alias il remonte au rang 4.
# Appliqué AVANT la racinisation, pour que corpus et requête soient normalisés pareil.
# Table courte et justifiée par le corpus : on n'ajoute un couple que si les deux mots y
# sont réellement présents — pas de vocabulaire inventé.
_ALIAS = {
    r"hors[- ]ligne": "offline",
    r"file d[' ]attente": "queue",
    r"\bsauvegarde\w*": "backup",
    r"\bdeploiement\w*": "deploy",
    r"\bdeploy(?:er|ee?s?)\b": "deploy",
    r"mise en production": "deploy",
    r"\bmemoire cache\b": "cache",
}
_ALIAS_RE = [(re.compile(k), v) for k, v in
             sorted(_ALIAS.items(), key=lambda kv: -len(kv[0]))]


def aliaser(txt):
    for motif, canon in _ALIAS_RE:
        txt = motif.sub(canon, txt)
    return txt


def tokenize(text):
    return [stem(t) for t in re.findall(r"[a-z0-9]+", aliaser(fold(text)))
            if len(t) > 2 and t not in STOP]


def strip_md(text):
    text = re.sub(r"^---\n.*?\n---", "", text, flags=re.S)   # frontmatter
    text = re.sub(r"```.*?```", " ", text, flags=re.S)        # blocs code
    return text


def _indexable():
    """Les .md que le rappel considère, triés — l'entrée de l'empreinte."""
    out = []
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        if not _skip(rel):
            out.append((rel, p))
    out.sort()
    return out


def _fingerprint(files):
    """Identité du contenu indexable du tronc : chemin, mtime, taille.

    Un stat() par fichier, quelques millisecondes — contre les ~200 ms qu'il
    faut pour les lire et les tokeniser. Hacher le contenu obligerait à tout
    lire, c'est-à-dire exactement le coût qu'on évite.
    """
    h = hashlib.sha256()
    for rel, p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        h.update(f"{rel}\0{st.st_mtime_ns}\0{st.st_size}\0".encode())
    return h.hexdigest()


# Incrémenté dès que la tokenisation ou la forme d'un document change, pour
# qu'un vieux cache soit jeté au lieu de servir en silence des fiches notées
# selon les règles précédentes.
#   v2 (2026-08-12) : racinisation + alias FR/EN dans tokenize().
#   v3 (2026-08-12) : les documents portent redirectsTo / relations.remplace.
_CACHE_VERSION = 3


def load_corpus():
    """Fiches tokenisées, depuis un cache tant que le tronc n'a pas bougé.

    POURQUOI C'EST CACHÉ. Ceci tourne à CHAQUE prompt, via le hook de rappel.
    Sans cache, il relisait et retokenisait tout le tronc à chaque fois :
    214 ms sur un tronc de 241 fiches, et ça croît linéairement — environ 1,6 s
    à 5000 fiches. L'utilisateur payait ça à chaque message, et rien ne l'aurait
    jamais signalé, puisque le rappel restait parfaitement correct. Il devenait
    simplement plus lent chaque semaine.

    JSON plutôt que pickle : le cache est un fichier sur disque, et un format
    capable d'exécuter du code au chargement ne vaut pas quelques millisecondes.
    """
    files = _indexable()
    fp = _fingerprint(files)
    cache = os.path.join(BRAIN, "state", "recall-index.json")

    try:
        with open(cache, encoding="utf-8") as f:
            blob = json.load(f)
        if blob.get("fingerprint") == fp and blob.get("version") == _CACHE_VERSION:
            return blob["docs"]
    except Exception:
        pass        # absent, illisible, tronqué : on reconstruit, jamais d'échec

    docs = _read_corpus(files)

    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        # Atomique : un hook tué en pleine écriture ne doit pas laisser un
        # demi-fichier que la fois suivante lira comme faisant autorité.
        tmp = f"{cache}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": _CACHE_VERSION, "fingerprint": fp, "docs": docs}, f)
        os.replace(tmp, cache)
    except Exception:
        pass        # tronc en lecture seule, disque plein : le rappel marche, en plus lent

    return docs


def _read_corpus(files):
    docs = []
    for rel, p in files:
        try:
            raw = open(p, encoding="utf-8").read()
        except Exception:
            continue
        fm = re.match(r"^---\n(.*?)\n---", raw, re.S)
        name = re.search(r"^name:\s*(.+)$", fm.group(1), re.M) if fm else None
        desc = re.search(r'^description:\s*"?(.+?)"?\s*$', fm.group(1), re.M) if fm else None
        body = strip_md(raw)
        # le titre/description pèsent plus (×3) : signal le plus dense
        boosted = ((name.group(1) + " ") * 3 if name else "") + \
                  ((desc.group(1) + " ") * 3 if desc else "") + body
        docs.append({
            "path": rel,
            # succession : cette fiche est-elle un alias (redirectsTo) et/ou en
            # remplace-t-elle d'autres (relations.remplace) ? cf. _perimees()
            "redirige_vers": _fm_champ(raw, "redirectsTo"),
            "remplace": _fm_remplace(raw),
            "name": name.group(1).strip() if name else os.path.basename(rel)[:-3],
            "desc": desc.group(1).strip() if desc else "",
            "tokens": tokenize(boosted),
        })
    return docs


# ---------------------------------------------------------------- boucle usage → classement
# Ce qui a DÉJÀ servi remonte. Le journal de rappel existait depuis des mois et personne ne
# le relisait : `inject_recall.py` l'ouvrait en « a » et rien ne le lisait — 2,3 % des
# fiches proposées étaient réellement ouvertes, et rien ne corrigeait ce taux.
# Le multiplicateur est logarithmique : 1 succès pèse beaucoup, le 10ᵉ presque plus. Une
# fiche utilisée 3 fois ne doit pas écraser la pertinence lexicale, juste la départager.
# α MESURÉ, PAS CHOISI AU HASARD. Il n'y a pas de vérité terrain pour l'optimiser ; on
# mesure donc sa SENSIBILITÉ. Sur 10 requêtes, part du top-3 occupée par des fiches à
# historique : α=0 → 3/30 · 0,2 → 8/30 · 0,5 → 12/30 · 1,0 → 15/30 (et une seule requête
# sur dix garde son top-3 d'origine). Au-delà de ~0,3 l'historique dicte le classement et
# le lexical n'est plus le juge. 0,2 = l'usage départage sans dominer.
ALPHA = 0.2
SEUIL_PEU_PROPOSEE = 3      # en dessous, une fiche est « peu vue » et a droit à l'exploration
_UTILITE_CACHE = None


def _utilite():
    """{chemin: {sugg, hit}} produit par recall_feedback.py. Chargé une fois par processus.
    Absent = le rappel fonctionne exactement comme avant : jamais d'échec sur ce fichier."""
    global _UTILITE_CACHE
    if _UTILITE_CACHE is None:
        try:
            with open(os.path.join(BRAIN, "state", "recall-utilite.json"), encoding="utf-8") as f:
                _UTILITE_CACHE = json.load(f)
        except Exception:
            _UTILITE_CACHE = {}
    return _UTILITE_CACHE


# ---------------------------------------------------------------- succession de fiches
# `redirectsTo:` existait DÉJÀ dans le frontmatter (1 fiche) et n'était lu par PERSONNE :
# une fiche fusionnée restait donc l'égale de celle qui la remplace dans le rappel, et
# pouvait sortir devant elle. C'est la même relation que `relations.remplace` de
# jardinage-regles §4 bis, vue de l'autre bout — on lit les deux plutôt que d'inventer
# une convention concurrente.
_FM_REMPL = re.compile(r"^\s+remplace\s*:\s*\[([^\]]*)\]", re.M)


def _entete(raw):
    m = re.match(r"^---\n(.*?)\n---", raw, re.S)
    return m.group(1) if m else ""


def _fm_champ(raw, champ):
    m = re.search(rf"^\s*{champ}\s*:\s*[\"']?([^\"'\n]+)[\"']?\s*$", _entete(raw), re.M)
    return m.group(1).strip() if m else None


def _fm_remplace(raw):
    m = _FM_REMPL.search(_entete(raw))
    return [c.strip().strip("\"'") for c in m.group(1).split(",") if c.strip()] if m else []


def _perimees(docs):
    """Noms de fiches remplacées par une autre — retirées du rappel, jamais du disque.
    On n'écarte QUE si la fiche qui succède est réellement présente dans l'index :
    sinon une redirection cassée effacerait le savoir au lieu de le rediriger."""
    presents = {d["name"] for d in docs}
    morts = set()
    for d in docs:
        if d.get("redirige_vers") and d["redirige_vers"] in presents:
            morts.add(d["name"])                 # cette fiche-ci est un alias
        for cible in d.get("remplace") or ():
            if cible in presents and d["name"] in presents:
                morts.add(cible)                 # cette fiche-ci en remplace une autre
    return morts


class BM25:
    """Backend lexical v0 — Okapi BM25. Remplaçable par un backend embeddings."""
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

    def search(self, query, k=5, feedback=True):
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
        if not scored:
            return []
        morts = _perimees(self.docs)
        if morts:
            vivants = [(sc, d) for sc, d in scored if d["name"] not in morts]
            scored = vivants or scored        # jamais de résultat vide à cause du filtre
        util = _utilite() if feedback else {}
        ajuste = [(s * (1 + ALPHA * math.log(1 + util.get(d["path"], {}).get("hit", 0))), d)
                  for s, d in scored]
        ajuste.sort(key=lambda x: x[0], reverse=True)
        if not util:
            return ajuste[:k]

        # QUOTA D'EXPLORATION — 1 place sur 3. Sans lui, la boucle s'auto-renforce : une
        # fiche déjà ouverte remonte, donc elle est plus souvent proposée, donc plus
        # souvent ouverte. Les fiches rares mais justes disparaîtraient du rappel sans
        # que rien ne le signale. On réserve donc des places aux PEU proposées.
        n_explo = k // 3
        retenues = ajuste[:k - n_explo]
        deja = {id(d) for _, d in retenues}
        neuves = [(s, d) for s, d in ajuste[k - n_explo:]
                  if id(d) not in deja
                  and util.get(d["path"], {}).get("sugg", 0) < SEUIL_PEU_PROPOSEE]
        for s, d in neuves[:n_explo]:
            retenues.append((s, d)); deja.add(id(d))
        for s, d in ajuste[k - n_explo:]:          # pas assez de neuves : on complète normalement
            if len(retenues) >= k:
                break
            if id(d) not in deja:
                retenues.append((s, d)); deja.add(id(d))
        return retenues[:k]


def main():
    args = [a for a in sys.argv[1:]]

    # mode --semantic : délègue au backend embeddings (venv model2vec) s'il est dispo.
    # Défaut = BM25 (instantané, meilleur que les embeddings statiques à petite échelle).
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
        print('Usage : brain_recall.py [-k N] [--json] "ta requête"'); sys.exit(1)

    results = BM25(load_corpus()).search(query, k)
    if as_json:
        print(json.dumps([{"path": d["path"], "name": d["name"],
                           "desc": d["desc"], "score": round(s, 3)}
                          for s, d in results], ensure_ascii=False, indent=2))
        return
    if not results:
        print(f"Aucune fiche pertinente pour : {query}"); return
    print(f"🔎 Top {len(results)} pour « {query} » :\n")
    for s, d in results:
        print(f"  [{s:5.2f}] {d['name']}  ({d['path']})")
        if d["desc"]:
            print(f"          {d['desc'][:110]}")


if __name__ == "__main__":
    main()
