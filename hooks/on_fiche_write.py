#!/usr/bin/env python3
"""
Hook PostToolUse (Write|Edit) du C Brain — garde mécanique instantanée.
À CHAQUE fiche déposée dans le tronc, sans LLM, sans boucle, sans bloquer :
  1. masque tout secret en clair
  2. garantit que la fiche est dans la carte MEMORY.md (sinon -> Inbox "à classer")
  3. signale si le frontmatter manque

Anti-boucle : ce script édite les fichiers en I/O direct Python (pas via l'outil
Write/Edit), donc il ne re-déclenche jamais le hook. Le travail sémantique
(dédup, reclassement, distillation) reste aux agents LLM jardinier/distillateur.

Règle d'or : ne JAMAIS bloquer. Sort toujours 0.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from brain_status import write_status
except Exception:
    def write_status(*a, **k): pass

BRAIN = os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
INBOX_HEADER = "## 🆕 Inbox — fiches à classer (auto)"

SECRET = re.compile(
    r'(ntn_[A-Za-z0-9]+|sk-ant-[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+|secret_[A-Za-z0-9]+'
    r'|eyJ[A-Za-z0-9_.-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})'
)

def get_target(data):
    ti = (data or {}).get("tool_input", {}) or {}
    return ti.get("file_path") or ti.get("path")

def main(data):
    fp = get_target(data)
    if not fp:
        return
    real = os.path.realpath(fp)
    # uniquement les fiches du tronc
    if not real.startswith(BRAIN + os.sep):
        return
    rel = os.path.relpath(real, BRAIN)

    # --- pulse de statut pour la capsule (toute activité sur l'arbre) ---
    name = os.path.basename(rel)[:-3] if rel.endswith(".md") else os.path.basename(rel)
    if rel == "MEMORY.md":
        write_status("busy", "mapping", "mise à jour de la carte")
    elif rel.endswith(".md") and not rel.startswith("sessions" + os.sep):
        write_status("busy", "filing", name)

    # exclure la carte elle-même, l'archive auto, et les non-.md du travail mécanique
    if rel == "MEMORY.md" or rel.startswith("sessions" + os.sep) or not rel.endswith(".md"):
        return
    if not os.path.exists(real):
        return
    try:
        txt = open(real, encoding="utf-8").read()
    except Exception:
        return

    # --- LEDGER « sauvegardes manuelles » (anti-redondance distillateur) ---
    # Si TU (la session en cours, pas le jardinier headless) écris/affines une fiche de savoir,
    # on le note par session_id. Au SessionEnd, le distillateur recevra « ne recrée pas ces fiches »
    # → il ne refait pas le travail déjà fait à la main (tokens économisés, zéro doublon), tout en
    # gardant le filet auto pour le savoir NON sauvé. Foreground seulement, zones de savoir seulement.
    if os.environ.get("CLAUDE_BRAIN_GARDENING") != "1":
        sid = (data or {}).get("session_id")
        if sid and rel.split(os.sep)[0] in ("projects", "lessons", "meta", "life"):
            try:
                import time
                led = os.path.join(BRAIN, "state", "manual-saves.jsonl")
                os.makedirs(os.path.dirname(led), exist_ok=True)
                with open(led, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": int(time.time()), "sid": sid, "path": rel},
                                       ensure_ascii=False) + "\n")
            except Exception:
                pass

    # détection de cohérence (Horizon 2) : flag des fiches qui se recouvrent, détaché
    try:
        import subprocess
        cc = os.path.join(BRAIN, "hooks", "check_coherence.py")
        if os.path.exists(cc):
            subprocess.Popen([sys.executable, cc, real],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:
        pass

    # --- 1. masquage des secrets (in place, I/O direct) ---
    masked = SECRET.sub("«SECRET-MASQUÉ»", txt)
    if masked != txt:
        try:
            open(real, "w", encoding="utf-8").write(masked)
            txt = masked
            write_status("busy", "correcting", f"secret masqué dans {name}")
        except Exception:
            pass

    # slug / nom pour la détection de présence dans la carte
    m = re.search(r'^name:\s*(.+)$', txt, re.M)
    slug = m.group(1).strip() if m else None
    fname = os.path.basename(rel)[:-3]

    # --- 2. garantir la présence dans la carte ---
    try:
        mem = open(MEMORY, encoding="utf-8").read()
    except Exception:
        return
    linked = (rel in mem) or (fname in mem) or (slug and f"[[{slug}]]" in mem) \
             or (slug and f"({rel})" in mem)
    # F2 — pendant une passe de maintenance (CLAUDE_BRAIN_GARDENING=1), c'est le
    # jardinier qui possède la carte : il range les fiches DANS MEMORY.md et vide
    # l'Inbox. Déposer en parallèle dans l'Inbox créerait une course (re-déposer une
    # fiche qu'il vient de classer). On garde le masquage des secrets et le capteur de
    # cohérence (au-dessus, toujours actifs) mais on saute le dépôt Inbox ici.
    if not linked and os.environ.get("CLAUDE_BRAIN_GARDENING") != "1":
        title = slug or fname
        line = f"- [{title}]({rel}) — déposée auto, à classer par le [[jardinier]]"
        if INBOX_HEADER in mem:
            mem = mem.replace(INBOX_HEADER, INBOX_HEADER + "\n" + line, 1)
        else:
            mem = mem.rstrip() + f"\n\n---\n\n{INBOX_HEADER}\n\n*Le hook dépose ici toute fiche non encore cartographiée ; le jardinier les range ensuite dans la bonne section.*\n\n{line}\n"
        try:
            open(MEMORY, "w", encoding="utf-8").write(mem)
        except Exception:
            pass

def refresh_doctor():
    """Rafraîchit state/doctor.json en arrière-plan (détaché, jamais bloquant)."""
    try:
        import subprocess
        doc = os.path.join(BRAIN, "hooks", "brain_doctor.py")
        if os.path.exists(doc):
            subprocess.Popen([sys.executable, doc, "--json"],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:
        pass

def refresh_planet():
    """Régénère planet/graph.json — la PLANÈTE de connaissance grandit en temps réel
    à chaque fiche écrite (détaché, jamais bloquant)."""
    try:
        import subprocess
        ge = os.path.join(BRAIN, "hooks", "graph_export.py")
        if os.path.exists(ge):
            subprocess.Popen([sys.executable, ge],
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception:
        pass

if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    fp = get_target(data)
    in_brain = bool(fp) and os.path.realpath(fp).startswith(BRAIN + os.sep)
    try:
        main(data)
    except Exception:
        pass
    # refresh des artefacts (doctor.json + planet/graph.json) UNIQUEMENT pour une écriture DANS
    # le tronc. Avant, le hook étant global (Write|Edit), CHAQUE édition de n'importe quel projet
    # lançait 2 scans complets du Brain et appendait une ligne à metrics.jsonl (sur-fréquence +
    # courbe polluée). On gate sur l'appartenance au tronc.
    if in_brain:
        try:
            refresh_doctor()
        except Exception:
            pass
        try:
            refresh_planet()
        except Exception:
            pass
    sys.exit(0)
