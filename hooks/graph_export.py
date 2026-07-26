#!/usr/bin/env python3
"""
graph_export.py — exporte le Claude Brain en graphe pour la PLANÈTE de connaissance.

Scanne toutes les fiches .md du tronc (projects/, lessons/, meta/, life/, agents/),
lit leur frontmatter (`name`, `description`) et leurs liens `[[...]]`, et écrit
`planet/graph.json` : la matière première du visualizer 3D (1 fiche = 1 point sur le globe).

Conçu pour être appelé :
  - à la main : `python3 hooks/graph_export.py`
  - automatiquement par on_fiche_write.py à chaque fiche écrite (croissance temps réel).

Déterministe et sans dépendance externe. Sort toujours 0 (ne bloque jamais un hook).
"""
import os, re, json, sys

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
OUT = os.path.join(BRAIN, "planet", "graph.json")
EMBED2 = os.path.join(BRAIN, "state", "embed2.json")   # carte SÉMANTIQUE (Étage 1), calculée par brain_embed2.py
COACT = os.path.join(BRAIN, "state", "coactivation.json")  # mémoire de travail (Étage 2), calculée par coactivation.py
CHALLENGES = os.path.join(BRAIN, "state", "challenges.json")  # avis du challenger (Étage 3 : la carte a un avis)
BELIEFS = os.path.join(BRAIN, "meta", "beliefs.json")        # convictions datées de l'auteur du tronc (Étage 3 : couche goût)
MEDIA = os.path.join(BRAIN, "meta", "media.json")            # nœuds REJOUABLES (Étage 4 : capture glb/clip/courbe)


def load_media():
    """Captures rejouables par fiche → { rel_path: {type, src, caption} }. Curé (meta/media.json). Stdlib."""
    out = {}
    try:
        for f, v in json.load(open(MEDIA, encoding="utf-8")).items():
            if f.startswith("_") or not isinstance(v, dict) or not v.get("src"):
                continue
            out[f] = {"type": v.get("type", "glb"), "src": v["src"], "caption": v.get("caption", "")}
    except Exception:
        return {}
    return out


def load_beliefs():
    """Convictions datées de l'auteur du tronc → { rel_path: "depuis <date> — <note>" }. Curé (meta/beliefs.json). Stdlib."""
    out = {}
    try:
        for f, v in json.load(open(BELIEFS, encoding="utf-8")).items():
            if f.startswith("_") or not isinstance(v, dict):
                continue
            since = v.get("since", "")
            out[f] = (f"depuis {since} — " if since else "") + v.get("note", "")
    except Exception:
        return {}
    return out


def load_challenges():
    """Verdicts ACTIFS du challenger par fiche → { rel_path: "verdict court" }. Les challenges
    marqués PÉRIMÉ/résolu sont ignorés (la carte ne conteste que ce qui tient encore). Stdlib."""
    out = {}
    try:
        for c in json.load(open(CHALLENGES, encoding="utf-8")):
            vp = (c.get("verdict_pair") or "")
            prob = (c.get("probleme") or "")
            if "PÉRIMÉ" in prob or "périmé" in vp.lower() or "résolu" in vp.lower():
                continue                                  # challenge éteint → pas un avis vivant
            f = c.get("fiche")
            if not f:
                continue
            reason = vp or prob
            out.setdefault(f, reason[:200])               # 1 verdict (le 1er actif) par fiche
    except Exception:
        return {}
    return out


def load_embed2():
    """Positions 2D sémantiques { rel_path: [x,y] } — cache produit hors-ligne (numpy).
    Lu SANS dépendance : graph_export reste pur-stdlib (appelé à chaque écriture de fiche)."""
    try:
        return json.load(open(EMBED2, encoding="utf-8")).get("pos", {})
    except Exception:
        return {}


def load_coact():
    """Chaleur (récence d'usage) par id + liens d'usage + fiches de la SESSION COURANTE — Étage 2. Stdlib."""
    try:
        c = json.load(open(COACT, encoding="utf-8"))
        hot = set((c.get("hot_session") or {}).get("paths", []))   # fiches activées dans la session la plus récente
        return c.get("heat_id", {}), c.get("edges", []), hot
    except Exception:
        return {}, [], set()
# dossiers de premier niveau = « domaines » (couleurs sur le globe)
DOMAINS = ["projects", "lessons", "meta", "life", "agents"]

FM_NAME = re.compile(r'^\s*name:\s*["\']?([^"\'\n]+)["\']?\s*$', re.M)
FM_TITLE = re.compile(r'^\s*title:\s*["\']?(.+?)["\']?\s*$', re.M)  # libellé humain descriptif (≠ slug stable)
FM_DESC = re.compile(r'^\s*description:\s*["\']?(.+?)["\']?\s*$', re.M)
FM_BORN = re.compile(r'^\s*born_from:\s*(.+?)\s*$', re.M)   # born_from: <projet>[, autre]
FM_SCALE = re.compile(r'^\s*scale:\s*([0-9](?:\.[0-9])?)\s*$', re.M)  # scale: 1..4 (centre-ville→périphérie)
LINK = re.compile(r'\[\[([^\]]+)\]\]')          # [[nom-de-fiche]]
RESUME_RE = re.compile(r'REPRENDRE ICI|point de reprise|à reprendre', re.I)   # point à reprendre (Étage 2/badge)
DASH = re.compile(r'\s+[—–]\s+')                # tiret cadratin/demi-cadratin entouré d'espaces

# poids des appartenances (modèle continent/ville/frontière) — voir respirabilite & volet-3
W_PRIMARY = 1.00     # dossier d'origine (un projet) = appartenance forte
W_BORN    = 0.70     # né d'un projet (born_from) mais rangé ailleurs (ex. leçon réutilisable)
W_LINK    = 0.18     # lien [[...]] vers/depuis une fiche de projet = appartenance douce
HOME_MIN  = 0.50     # appartenance mini pour avoir une VILLE maison (dossier/born_from, pas un simple lien)
FRONTIER_MIN = 0.30  # seuil pour qu'une 2ᵉ appartenance compte comme « frontière »

# heuristique d'échelle quand `scale:` absent : centre-ville (vision/projet) → périphérie (détail)
def guess_scale(nid):
    s = nid.lower()
    if s.startswith("project-") or "vision" in s:
        return 1.0                                   # cœur : le projet, sa vision
    if any(k in s for k in ("audit", "naming", "precision", "couts", "labo", "lab")):
        return 3.0                                   # périphérie : détail/annexe
    return 2.0                                        # ville standard


def clean_desc(raw):
    """Résumé court et propre pour le panneau : la phrase d'accroche avant le 1er ' — ',
    sinon la description entière ; jamais coupée en plein mot."""
    full = (raw or "").strip()
    summary = DASH.split(full, 1)[0].strip()
    if len(summary) < 35:                       # accroche trop maigre → on garde tout
        summary = full
    if len(summary) > 180:                       # coupe nette au mot + …
        summary = summary[:180].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return summary


def frontmatter(text):
    """Renvoie le bloc frontmatter (entre les --- de tête) ou ''."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[3:end]
    return ""


def clean_body(text):
    """Corps de la fiche nettoyé du markdown → explication longue, lisible, pour le panneau déplié."""
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            body = text[end + 4:]
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)        # images
    body = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)          # [[lien]] → lien
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)     # [texte](url) → texte
    out = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            out.append("")
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)                     # titres
        s = re.sub(r"^[-*]\s+", "• ", s)                      # puces
        s = re.sub(r"^\d+\.\s+", "• ", s)                     # listes numérotées
        s = re.sub(r"^>\s?", "", s)                           # citations
        s = s.replace("**", "").replace("`", "").replace("*", "")
        out.append(s)
    txt = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    if len(txt) > 1600:                                       # coupe nette au mot + …
        txt = txt[:1600].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return txt


def scan():
    nodes = {}      # id -> {id, name, domain, group, desc, file}
    raw_links = []  # (src_id, target_name)
    embed2 = load_embed2()         # positions sémantiques par chemin de fiche (Étage 1)
    heat, coact_edges, active = load_coact()   # chaleur + liens de co-activation + session courante (Étage 2)
    challenges = load_challenges()             # avis du challenger par fiche (Étage 3)
    beliefs = load_beliefs()                   # convictions datées de l'auteur du tronc (Étage 3 : couche goût)
    media = load_media()                       # captures rejouables par fiche (Étage 4)

    for domain in DOMAINS:
        root = os.path.join(BRAIN, domain)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                # on ne garde QUE des fiches de savoir : pas les README ni les docs
                if fn.lower() == "readme.md":
                    continue
                low = dirpath.lower()
                if os.sep + "documentation" in low or os.sep + "docs" in low:
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    text = open(path, encoding="utf-8").read()
                except Exception:
                    continue
                fm = frontmatter(text)
                m = FM_NAME.search(fm)
                if not m:
                    continue                     # pas de `name:` → ce n'est pas une fiche, on saute
                nid = m.group(1).strip()
                dm = FM_DESC.search(fm)
                desc = clean_desc(dm.group(1) if dm else "")
                tm = FM_TITLE.search(fm)
                title = tm.group(1).strip() if tm else nid.replace("-", " ")
                # sous-groupe = sous-dossier de projet (ex. mon-projet) sinon = domaine
                rel = os.path.relpath(dirpath, root)
                group = rel.split(os.sep)[0] if rel != "." else domain
                # appartenance déclarée : born_from (1+ projets), scale (centre↔périphérie)
                bm = FM_BORN.search(fm)
                born = [b.strip().strip("[]\"'") for b in bm.group(1).split(",")] if bm else []
                born = [b for b in born if b]
                sm = FM_SCALE.search(fm)
                scale = float(sm.group(1)) if sm else guess_scale(nid)
                rel_file = os.path.relpath(path, BRAIN)
                nodes[nid] = {"id": nid, "name": nid, "title": title, "domain": domain,
                              "group": group, "desc": desc,
                              "born_from": born, "scale": scale,
                              "long": clean_body(text),
                              "embed2": embed2.get(rel_file),   # [x,y] sémantique ou None
                              "heat": heat.get(nid, 0.0),        # chaleur d'usage 0..1 (Étage 2)
                              "active": rel_file in active,      # activée dans la session courante (Étage 2)
                              "challenge": challenges.get(rel_file),   # avis du challenger (Étage 3) ou None
                              "conviction": beliefs.get(rel_file),     # conviction datée de l'auteur du tronc (Étage 3) ou None
                              "media": media.get(rel_file),            # capture rejouable (Étage 4) ou None
                              "resume": bool(RESUME_RE.search(text)),  # porte un « point à reprendre » (badge ↻)
                              "file": rel_file}
                # liens sortants (dédupliqués plus bas)
                for tgt in set(LINK.findall(text)):
                    raw_links.append((nid, tgt.strip()))

    # ne garde que les liens dont la cible est une fiche connue (pas les [[à écrire]])
    ids = set(nodes)
    seen = set()
    links = []
    for src, tgt in raw_links:
        if tgt in ids and src != tgt and (src, tgt) not in seen and (tgt, src) not in seen:
            seen.add((src, tgt))
            links.append({"source": src, "target": tgt})

    # ---------- APPARTENANCE (modèle continent/ville/frontière) ----------
    # « villes » = les sous-dossiers du domaine projects (chaque projet est une ville).
    projects = sorted({n["group"] for n in nodes.values() if n["domain"] == "projects"})
    proj_set = set(projects)
    # voisinage non orienté vers les fiches de projet (pour l'appartenance douce des leçons)
    proj_of = {nid: n["group"] for nid, n in nodes.items() if n["domain"] == "projects"}
    adj_proj = {nid: [] for nid in nodes}       # nid -> [groupes de projet reliés]
    for l in links:
        s, t = l["source"], l["target"]
        if s in proj_of and t not in proj_of:
            adj_proj[t].append(proj_of[s])
        elif t in proj_of and s not in proj_of:
            adj_proj[s].append(proj_of[t])

    for nid, n in nodes.items():
        m = {}
        if n["domain"] == "projects":                       # fiche déjà dans une ville
            m[n["group"]] = m.get(n["group"], 0.0) + W_PRIMARY
        for b in n["born_from"]:                              # née d'un projet, rangée ailleurs
            if b in proj_set:
                m[b] = m.get(b, 0.0) + W_BORN
        for g in adj_proj[nid]:                               # tirée par les liens vers un projet
            m[g] = m.get(g, 0.0) + W_LINK
        if not m:
            n["membership"] = {}                             # hors-ville (méta/vie pures)
            n["primary_project"] = None
            n["frontier"] = False
            continue
        # poids ABSOLUS ancrés sur W_PRIMARY=1.0 (pas de normalisation par le max :
        # un simple lien reste ténu ~0.20, il ne doit pas se gonfler en pleine appartenance)
        m = {k: round(min(v, 1.0), 3) for k, v in m.items()}
        n["membership"] = dict(sorted(m.items(), key=lambda kv: -kv[1]))
        mx = max(m.values())
        # une fiche n'a une VILLE que si son appartenance est FORTE (dossier d'origine ou born_from).
        # Un simple lien (~0.18) ne suffit pas → l'agent/méta qui mentionne un projet n'y est pas classé.
        n["primary_project"] = max(m, key=m.get) if mx >= HOME_MIN else None
        # frontière = a une vraie ville maison ET une 2ᵉ ville ≥ seuil (ex. VoiceShell)
        n["frontier"] = (n["primary_project"] is not None
                         and sum(1 for v in m.values() if v >= FRONTIER_MIN) >= 2)

    return {
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
        "counts": {"nodes": len(nodes), "links": len(links),
                   "projects": len(projects),
                   "frontier": sum(1 for n in nodes.values() if n.get("frontier")),
                   "challenged": sum(1 for n in nodes.values() if n.get("challenge")),
                   "convictions": sum(1 for n in nodes.values() if n.get("conviction")),
                   "media": sum(1 for n in nodes.values() if n.get("media")),
                   "active": sum(1 for n in nodes.values() if n.get("active")),
                   "resume": sum(1 for n in nodes.values() if n.get("resume"))},
        "domains": DOMAINS,
        "projects": projects,
        "nodes": sorted(nodes.values(), key=lambda n: (n["domain"], n["group"], n["id"])),
        "links": links,
        # liens d'USAGE (co-activation) : fiches activées ensemble en session, ≠ liens déclarés (Étage 2)
        "coact": [e for e in coact_edges if e[0] in ids and e[1] in ids],
    }


def main():
    try:
        data = scan()
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        if sys.stdout.isatty():
            c = data["counts"]
            print(f"🪐 graph.json écrit : {c['nodes']} points, {c['links']} liens → {os.path.relpath(OUT, BRAIN)}")
    except Exception as e:
        if sys.stdout.isatty():
            print(f"graph_export: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
    sys.exit(0)
