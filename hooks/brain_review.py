#!/usr/bin/env python3
"""brain_review — AUDIT GLOBAL du contenu/topologie du tronc (≠ brain_audit).

Trois audits distincts coexistent, ne pas confondre :
  - brain_audit  = santé du PIPELINE (distillation, quota, file d'attente).
  - brain_doctor = défauts PONCTUELS (liens morts, orphelins, frontmatter, nommage).
  - brain_review (ICI) = vue d'ensemble AGRÉGÉE de la SANTÉ DU SAVOIR : rassemble
    en UN seul rapport ce que mesurent déjà topology + utility + challenger +
    doctor, plus deux contrôles neufs (fiches périmées >3 mois, chemins d'infra
    incohérents), pour donner à un humain/agent une vue complète du tronc d'un
    coup d'œil — sans avoir à lire cinq JSON séparés.

Séparation des pouvoirs (cf. lessons/separation-pouvoirs-agent-teams.md) :
  ce module MESURE et PROPOSE, il ne MODIFIE AUCUNE fiche — exactement comme
  topology/utility (mécanique, cheap, zéro LLM). Le JUGEMENT et le geste restent
  aux agents : l'architecte tisse les liens, le challenger tranche les doutes,
  l'archiviste propose l'archivage, le jardinier range, le mécanicien répare
  l'infra. brain_review n'écrit QUE state/review.{json,md}.

Usage :
  brain_review.py            → régénère topology+utility, agrège tout, écrit
                               state/review.{json,md}, affiche le résumé markdown.
  brain_review.py --stale    → n'appelle pas les moteurs, lit les états existants
                               (rapide ; indique la fraîcheur des données).
  brain_review.py --json     → imprime aussi le JSON agrégé sur stdout.
  brain_review.py --quiet    → écrit les fichiers, pas d'affichage.
"""
import os, re, sys, json, time, glob, subprocess

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
STATE = os.path.join(BRAIN, "state")
HOOKS = os.path.join(BRAIN, "hooks")
STALE_DAYS = 90                                     # « plus de trois mois »
FICHE_DIRS = ("projects", "lessons", "meta", "life", "agents", "planet", "sessions")
SKIP_PARTS = {".git", "node_modules", "audits", "capsule", "planet/dist"}


def _rj(name, default):
    try:
        return json.load(open(os.path.join(STATE, name), encoding="utf-8"))
    except Exception:
        return default


def _run(engine, *args):
    """Lance un moteur de mesure (topology/utility) pour rafraîchir son état."""
    p = os.path.join(HOOKS, engine)
    if not os.path.exists(p):
        return
    try:
        subprocess.run([sys.executable, p, *args], cwd=BRAIN, capture_output=True, timeout=120)
    except Exception:
        pass


def _fiches_in(dirs):
    out = []
    for d in dirs:
        for p in glob.glob(os.path.join(BRAIN, d, "**", "*.md"), recursive=True):
            rel = os.path.relpath(p, BRAIN)
            if any(part in SKIP_PARTS for part in rel.split(os.sep)):
                continue
            out.append((rel, p))
    return out


def _all_fiches():
    return _fiches_in(FICHE_DIRS)


def _git_last_ts():
    """Timestamp du dernier commit par fichier, en une seule passe git."""
    last = {}
    try:
        r = subprocess.run(["git", "-C", BRAIN, "log", "--format=@%ct", "--name-only"],
                           capture_output=True, text=True, timeout=60)
        cur = 0
        for line in r.stdout.splitlines():
            if line.startswith("@"):
                cur = int(line[1:])
            elif line.strip() and line not in last:
                last[line.strip()] = cur      # 1re occurrence = commit le plus récent
    except Exception:
        pass
    return last


def stale_fiches():
    """Fiches dont le dernier commit remonte à plus de STALE_DAYS jours."""
    now = time.time()
    last = _git_last_ts()
    out = []
    for rel, p in _all_fiches():
        ts = last.get(rel)
        if ts is None:
            try:
                ts = os.path.getmtime(p)      # non suivie par git → mtime en repli
            except OSError:
                continue
        age_days = (now - ts) / 86400
        if age_days > STALE_DAYS:
            out.append({"fiche": rel, "jours": int(age_days),
                        "date": time.strftime("%Y-%m-%d", time.localtime(ts))})
    out.sort(key=lambda x: x["jours"], reverse=True)
    return out


# Fiches d'INFRA seulement : y décrire un chemin périmé est un vrai bug. Ailleurs
# (sessions/archive, journaux projet), un ancien home est un fait HISTORIQUE daté,
# pas une incohérence — on ne le signale pas (bruit).
INFRA_DIRS = ("meta", "agents")


def path_incoherences():
    """Chemins incohérents dans les fiches d'INFRA : référence à un home qui n'est
    pas celui de la machine courante (migration de compte, copier-coller d'une
    autre machine). Constat, pas correction.

    Le nom d'utilisateur est DÉRIVÉ, jamais codé en dur : c'est exactement le
    bug qui avait cassé la distillation lors d'une migration de compte."""
    me = os.path.basename(os.path.expanduser("~"))
    other = re.compile(r"/Users/(?!" + re.escape(me) + r"\b)([A-Za-z0-9._-]+)")
    hits = []
    for rel, p in _fiches_in(INFRA_DIRS):
        try:
            lines = open(p, encoding="utf-8", errors="ignore").read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            m = other.search(line)
            if m:
                hits.append({"fiche": rel, "ligne": i,
                             "type": f"chemin d'un autre utilisateur ({m.group(1)})",
                             "extrait": line.strip()[:160]})
    return hits


def build():
    topo = _rj("topology.json", {})
    util = _rj("utility.json", {})
    challenges = _rj("challenges.json", [])
    coherence = _rj("coherence.json", [])
    doctor = _rj("doctor.json", {})

    review = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "topology_generated_at": topo.get("generated_at"),
        "n_notes": topo.get("n_notes", doctor.get("notes")),
        "n_liens": topo.get("n_liens"),
        # — topology (l'architecte tisse / reclasse) —
        "liens_manquants": topo.get("liens_manquants", []),
        "isolees": topo.get("isolees", []),
        "faiblement_liees": topo.get("faiblement_liees", []),
        "n_composantes": topo.get("n_composantes"),
        "composantes": topo.get("composantes", []),
        "placement_incoherent": topo.get("placement_incoherent", []),
        # — utility (l'archiviste élague) —
        "poids_mort": util.get("poids_mort", []),
        "ignorees": util.get("ignorees", []),
        # — challenger (tranche les doutes) —
        "doutes": challenges,
        "recouvrements": coherence,
        # — doctor (défauts ponctuels ; le mécanicien/jardinier répare) —
        "dead_links": doctor.get("dead_links", []),
        "orphans": doctor.get("orphans", []),
        "off_index": doctor.get("off_index", []),
        "naming": doctor.get("naming", []),
        "frontmatter": doctor.get("frontmatter", []),
        "drift_git": doctor.get("drift_git"),
        # — contrôles neufs de brain_review —
        "fiches_perimees": stale_fiches(),
        "chemins_incoherents": path_incoherences(),
    }
    return review


def _n(x):
    return len(x) if isinstance(x, (list, dict)) else (x or 0)


def to_markdown(r):
    L = []
    a = L.append
    a(f"# Audit global du tronc — {r['generated_at']}")
    a(f"\n{r['n_notes']} fiches · {r['n_liens']} liens · {r['n_composantes']} composante(s)"
      f" · topologie mesurée le {r.get('topology_generated_at','?')}\n")

    a("## 🔴 À traiter (par ordre d'impact)\n")
    rows = [
        ("Liens manquants (fiches proches non reliées)", "liens_manquants", "→ architecte : tisser"),
        ("Fiches isolées (0-1 lien)", "isolees", "→ architecte : relier"),
        ("Composantes déconnectées (>1)", None, ""),
        ("Placements incohérents (voisins d'un autre domaine)", "placement_incoherent", "→ jardinier : reclasser"),
        ("Poids mort (jamais consulté / utile)", "poids_mort", "→ archiviste : archiver"),
        ("Doutes du challenger (périmé/faux/contredit)", "doutes", "→ challenger : trancher"),
        ("Recouvrements forts (doublon ?)", "recouvrements", "→ jardinier : dédupe/contradiction"),
        ("Fiches périmées (>3 mois)", "fiches_perimees", "→ archiviste : vérifier fraîcheur"),
        ("Chemins d'infra incohérents", "chemins_incoherents", "→ mécanicien : corriger l'infra"),
        ("Liens morts", "dead_links", "→ mécanicien/jardinier"),
        ("Orphelins (hors carte)", "orphans", "→ jardinier : indexer"),
        ("Hors index (MEMORY.md)", "off_index", "→ jardinier : indexer"),
    ]
    for label, key, who in rows:
        n = (r["n_composantes"] - 1 if key is None and r.get("n_composantes") else _n(r.get(key)))
        if not n or n <= 0:
            continue
        a(f"- **{label}** : {n} {who}")
    if all((_n(r.get(k)) == 0) for _, k, _ in rows if k) and (r.get("n_composantes") or 1) <= 1:
        a("- ✅ Rien de saillant — le tronc est sain.")

    def section(title, items, fmt, cap=25):
        if not items:
            return
        a(f"\n## {title} ({len(items)})\n")
        for it in items[:cap]:
            a(f"- {fmt(it)}")
        if len(items) > cap:
            a(f"- … et {len(items)-cap} autres (voir state/review.json)")

    section("Fiches périmées (>3 mois)", r["fiches_perimees"],
            lambda x: f"`{x['fiche']}` — {x['jours']} j ({x['date']})")
    section("Chemins d'infra incohérents", r["chemins_incoherents"],
            lambda x: f"`{x['fiche']}:{x['ligne']}` — {x['type']} — `{x['extrait']}`")
    section("Fiches isolées", r["isolees"], lambda x: f"`{x}`" if isinstance(x, str) else f"`{x.get('fiche', x)}`")
    section("Placements incohérents", r["placement_incoherent"],
            lambda x: f"`{x.get('fiche', x)}`" if isinstance(x, dict) else f"`{x}`")
    section("Liens manquants", r["liens_manquants"],
            lambda x: (f"`{x.get('a','?')}` ↔ `{x.get('b','?')}` (sim {x.get('sim','?')})" if isinstance(x, dict) else f"`{x}`"))
    section("Poids mort", r["poids_mort"], lambda x: f"`{x}`")
    section("Doutes du challenger", r["doutes"],
            lambda x: f"`{x.get('fiche','?')}` — {x.get('probleme','')[:160]}" if isinstance(x, dict) else f"{x}")

    a("\n---\n*brain_review CONSTATE et PROPOSE ; il ne modifie aucune fiche. "
      "Le jugement et le geste reviennent aux agents (séparation des pouvoirs).*")
    return "\n".join(L)


def main():
    args = sys.argv[1:]
    if "--stale" not in args:
        _run("brain_topology.py", "--json")
        _run("brain_utility.py", "--json")

    r = build()
    os.makedirs(STATE, exist_ok=True)
    try:
        json.dump(r, open(os.path.join(STATE, "review.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass
    md = to_markdown(r)
    try:
        open(os.path.join(STATE, "review.md"), "w", encoding="utf-8").write(md + "\n")
    except Exception:
        pass

    if "--json" in args:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    elif "--quiet" not in args:
        print(md)
    sys.exit(0)


if __name__ == "__main__":
    main()
