#!/usr/bin/env python3
"""brain_topology — vue GLOBALE de la cohésion du Claude Brain (Horizon 2, niveau graphe).

Là où check_coherence regarde les fiches DEUX PAR DEUX (recouvrement local) et où
brain_doctor traque les défauts ponctuels (liens morts, orphelins), CE module prend
de la hauteur : il lit TOUT le graphe `[[...]]` + la similarité de contenu, et calcule
la **structure d'ensemble** pour révéler ce qui se voit seulement de loin :

  - liens MANQUANTS  : 2 fiches très proches par le contenu mais qui ne se citent pas
                       → l'or de la cohésion (surtout entre projets différents).
  - fiches ISOLÉES   : 0 ou 1 lien dans tout l'arbre (présentes dans la carte mais
                       déconnectées du tissu de connaissance).
  - sous-ensembles   : composantes connexes du graphe de liens — un îlot détaché
                       = un pan de savoir qui ne dialogue avec rien.
  - placement INCOHÉRENT : une fiche dont les voisins (liens) sont majoritairement
                       d'un AUTRE domaine que le sien → peut-être mal classée.
  - santé par domaine : densité interne, ponts inter-domaines (la valeur transverse).

Séparation des pouvoirs (comme tout le Brain) :
  - ICI (mécanique, cheap, zéro LLM) : MESURER la topologie → state/topology.json.
  - ARCHITECTE (LLM) : JUGER quels liens tisser, quels îlots relier, quoi reclasser.

Usage :
  brain_topology.py            → rapport lisible (terminal)
  brain_topology.py --json     → state/topology.json + sortie machine
Sort toujours 0 (ne bloque jamais un hook).
"""
import os, re, sys, json, math, glob, time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import brain_recall as recall          # réutilise fold/tokenize/STOP + la règle SKIP_PARTS
except Exception:
    recall = None

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
OUT = os.path.join(BRAIN, "state", "topology.json")
DOMAINS = ("projects", "lessons", "meta", "life", "agents")

LINK = re.compile(r"\[\[([^\]]+)\]\]")
# placeholders de syntaxe présents dans les docs d'agents — jamais de vrais liens
NOT_A_LINK = {"slug", "lien", "liens", "...", "exemples", "nom-du-fichier", "name"}

MISS_MIN = 0.30     # cosinus TF-IDF : au-delà = assez proches pour SE CITER (< 0.45 = seuil doublon)
MISS_TOP = 25       # nb max de suggestions de liens remontées


def load():
    """Renvoie {name -> {domain, path, links:set, tokens:list}} pour les fiches de savoir."""
    fiches = {}
    for p in glob.glob(os.path.join(BRAIN, "**", "*.md"), recursive=True):
        rel = os.path.relpath(p, BRAIN)
        zone = rel.split(os.sep)[0]
        if zone not in DOMAINS:
            continue
        if os.path.basename(p).lower() == "readme.md":
            continue
        try:
            raw = open(p, encoding="utf-8").read()
        except Exception:
            continue
        fm = re.match(r"^---\n(.*?)\n---", raw, re.S)
        if not fm:
            continue
        m = re.search(r"^\s*name:\s*(.+)$", fm.group(1), re.M)
        if not m:
            continue
        name = m.group(1).strip().strip('"\'')
        links = {t.strip() for t in LINK.findall(raw)} - NOT_A_LINK
        toks = recall.tokenize(recall.strip_md(raw)) if recall else []
        fiches[name] = {"domain": zone, "path": rel, "links": links, "tokens": toks}
    return fiches


def tfidf(fiches):
    df = Counter()
    for d in fiches.values():
        for t in set(d["tokens"]):
            df[t] += 1
    N = len(fiches) or 1
    idf = {t: math.log(1 + N / (n + 0.5)) for t, n in df.items()}
    vecs = {}
    for name, d in fiches.items():
        tf = Counter(d["tokens"])
        v = {t: (f / len(d["tokens"])) * idf.get(t, 0) for t, f in tf.items()} if d["tokens"] else {}
        norm = math.sqrt(sum(w * w for w in v.values())) or 1.0
        vecs[name] = {t: w / norm for t, w in v.items()}
    return vecs


def cosine(a, b):
    small, big = (a, b) if len(a) < len(b) else (b, a)
    return sum(w * big.get(t, 0) for t, w in small.items())


def analyze():
    fiches = load()
    names = set(fiches)
    # --- graphe de liens non orienté (ne garde que les liens résolus) ---
    adj = defaultdict(set)
    for name, d in fiches.items():
        for tgt in d["links"]:
            if tgt in names and tgt != name:
                adj[name].add(tgt)
                adj[tgt].add(name)

    degree = {n: len(adj.get(n, ())) for n in names}
    isolated = sorted([n for n in names if degree[n] == 0])
    weak = sorted([n for n in names if degree[n] == 1])

    # --- composantes connexes (sous-ensembles déconnectés) ---
    seen, components = set(), []
    for n in names:
        if n in seen:
            continue
        stack, comp = [n], []
        seen.add(n)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nb in adj.get(cur, ()):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        components.append(sorted(comp))
    components.sort(key=len, reverse=True)

    # --- liens manquants : proches par le contenu mais non reliés ---
    vecs = tfidf(fiches)
    ordered = sorted(names)
    missing = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b in adj.get(a, ()):
                continue
            sim = cosine(vecs[a], vecs[b])
            if sim >= MISS_MIN:
                cross = fiches[a]["domain"] != fiches[b]["domain"]
                # score = similarité + petit bonus « pont transverse » (sans écraser une paire forte)
                missing.append({"a": a, "b": b, "sim": round(sim, 3), "cross_domain": cross,
                                "score": round(sim + (0.08 if cross else 0), 3)})
    missing.sort(key=lambda x: x["score"], reverse=True)
    missing = missing[:MISS_TOP]

    # --- placement incohérent : voisins majoritairement d'un autre domaine ---
    # On IGNORE les patterns LÉGITIMES par construction (sinon que des faux positifs) :
    #   une leçon/un objectif de vie pointe vers SON projet d'origine ; un projet vers les
    #   leçons qu'il a engendrées ; le méta-Brain vers ses agents. Le reste = vraie question.
    EXPECTED = {("lessons", "projects"), ("life", "projects"), ("projects", "lessons"),
                ("life", "meta"), ("meta", "agents"), ("agents", "meta"), ("meta", "projects")}
    misfiled = []
    for n in names:
        nbs = adj.get(n, ())
        if len(nbs) < 2:
            continue
        own = fiches[n]["domain"]
        ext = Counter(fiches[x]["domain"] for x in nbs)
        dom_voisin, cnt = ext.most_common(1)[0]
        if dom_voisin != own and cnt > len(nbs) / 2 and (own, dom_voisin) not in EXPECTED:
            misfiled.append({"fiche": n, "domaine": own, "voisins_surtout": dom_voisin,
                             "ratio": f"{cnt}/{len(nbs)}"})

    # --- santé par domaine : densité interne + ponts inter-domaines ---
    intra, cross = 0, 0
    bridges = []
    edges = set()
    for a in names:
        for b in adj.get(a, ()):
            e = tuple(sorted((a, b)))
            if e in edges:
                continue
            edges.add(e)
            if fiches[a]["domain"] == fiches[b]["domain"]:
                intra += 1
            else:
                cross += 1
                bridges.append({"a": e[0], "b": e[1],
                                "da": fiches[e[0]]["domain"], "db": fiches[e[1]]["domain"]})
    dom_counts = Counter(d["domain"] for d in fiches.values())

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_fiches": len(fiches), "n_liens": len(edges),
        "liens_intra_domaine": intra, "ponts_inter_domaines": cross,
        "domaines": dict(dom_counts),
        "isolees": isolated, "faiblement_liees": weak,
        "n_composantes": len(components),
        "composantes": [c for c in components if len(c) < len(fiches)],  # tout sauf le continent principal
        "liens_manquants": missing,
        "placement_incoherent": misfiled,
        "ponts_existants": bridges,
    }


def main():
    as_json = "--json" in sys.argv[1:]
    data = analyze()
    if as_json:
        try:
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception:
            pass
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    # rapport lisible
    print(f"🕸️  TOPOLOGIE DU BRAIN — {data['n_fiches']} fiches, {data['n_liens']} liens "
          f"({data['liens_intra_domaine']} internes, {data['ponts_inter_domaines']} ponts inter-domaines)\n")
    if data["isolees"]:
        print(f"🏝️  ISOLÉES ({len(data['isolees'])}) — aucun lien dans tout l'arbre :")
        for n in data["isolees"]:
            print(f"     · {n}")
    if len(data["composantes"]):
        print(f"\n🧩 SOUS-ENSEMBLES DÉTACHÉS ({len(data['composantes'])} hors continent principal) :")
        for c in data["composantes"][:8]:
            print(f"     · {{{', '.join(c)}}}")
    print(f"\n🔗 LIENS MANQUANTS suggérés (proches mais ne se citent pas) — top {len(data['liens_manquants'])} :")
    for m in data["liens_manquants"]:
        tag = " 🌉 PONT" if m["cross_domain"] else ""
        print(f"     [{m['sim']:.2f}]{tag}  {m['a']}  ⇄  {m['b']}")
    if data["placement_incoherent"]:
        print(f"\n📍 PLACEMENT À QUESTIONNER ({len(data['placement_incoherent'])}) :")
        for x in data["placement_incoherent"]:
            print(f"     · {x['fiche']} (dans {x['domaine']}) — voisins surtout {x['voisins_surtout']} ({x['ratio']})")
    print("\n→ state/topology.json écrit. L'ARCHITECTE juge et tisse.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        if sys.stdout.isatty():
            print(f"brain_topology: {e}", file=sys.stderr)
    sys.exit(0)
