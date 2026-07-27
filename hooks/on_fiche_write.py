#!/usr/bin/env python3
"""
PostToolUse (Write|Edit) hook — the instant mechanical guard.
On EVERY note landing in the trunk, with no LLM, no loop and no blocking:
  1. masque tout secret en clair
  2. guarantees the note is on the MEMORY.md map (otherwise -> the "to file" Inbox)
  3. signale si le frontmatter manque

Loop guard: this script edits files through direct Python I/O (not through the
Write/Edit tool), so it never re-triggers the hook. The semantic work
(dedup, refiling, distillation) stays with the gardener and distiller agents.

Golden rule: NEVER block. Always exits 0.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from brain_status import write_status
except Exception:
    def write_status(*a, **k): pass

BRAIN = os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
INBOX_HEADER = "## 🆕 Inbox — notes to file (auto)"

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

    # --- status pulse for the capsule (any activity on the tree) ---
    name = os.path.basename(rel)[:-3] if rel.endswith(".md") else os.path.basename(rel)
    if rel == "MEMORY.md":
        write_status("busy", "mapping", "updating the map")
    elif rel.endswith(".md") and not rel.startswith("sessions" + os.sep):
        write_status("busy", "filing", name)

    # exclude the map itself, the automatic archive, and non-.md files from the mechanical work
    if rel == "MEMORY.md" or rel.startswith("sessions" + os.sep) or not rel.endswith(".md"):
        return
    if not os.path.exists(real):
        return
    try:
        txt = open(real, encoding="utf-8").read()
    except Exception:
        return

    # --- LEDGER « sauvegardes manuelles » (anti-redondance distillateur) ---
    # If YOU (the live session, not the headless gardener) write or refine a knowledge note,
    # we record it by session_id. At SessionEnd the distiller is told "do not recreate these notes"
    # → it does not redo work already done by hand (tokens saved, zero duplicates), while still
    # keeping the automatic net for knowledge NOT saved. Foreground only, knowledge areas only.
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

    # coherence detection: flags overlapping notes, detached
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
    masked = SECRET.sub("«SECRET-MASKED»", txt)
    if masked != txt:
        try:
            open(real, "w", encoding="utf-8").write(masked)
            txt = masked
            write_status("busy", "correcting", f"secret masked in {name}")
        except Exception:
            pass

    # slug / name used to detect presence on the map
    m = re.search(r'^name:\s*(.+)$', txt, re.M)
    slug = m.group(1).strip() if m else None
    fname = os.path.basename(rel)[:-3]

    # --- 2. guarantee presence on the map ---
    try:
        mem = open(MEMORY, encoding="utf-8").read()
    except Exception:
        return
    linked = (rel in mem) or (fname in mem) or (slug and f"[[{slug}]]" in mem) \
             or (slug and f"({rel})" in mem)
    # F2 — pendant une passe de maintenance (CLAUDE_BRAIN_GARDENING=1), c'est le
    # gardener owns the map: it files notes INTO MEMORY.md and empties
    # the Inbox. Dropping into the Inbox in parallel would race (re-adding a note
    # fiche qu'il vient de classer). On garde le masquage des secrets et le capteur de
    # coherence (above, always active) but we skip the Inbox drop here.
    if not linked and os.environ.get("CLAUDE_BRAIN_GARDENING") != "1":
        title = slug or fname
        line = f"- [{title}]({rel}) — auto-added, to be filed by the [[gardener]]"
        if INBOX_HEADER in mem:
            mem = mem.replace(INBOX_HEADER, INBOX_HEADER + "\n" + line, 1)
        else:
            mem = mem.rstrip() + f"\n\n---\n\n{INBOX_HEADER}\n\n*The hook drops any note not yet on the map here; the gardener files them into the right section afterwards.*\n\n{line}\n"
        try:
            open(MEMORY, "w", encoding="utf-8").write(mem)
        except Exception:
            pass

def refresh_doctor():
    """Refreshes state/doctor.json in the background (detached, never blocking)."""
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
    """Regenerates planet/graph.json — the knowledge PLANET grows in real time
    with every note written (detached, never blocking)."""
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
    # refresh the artefacts (doctor.json + planet/graph.json) ONLY for a write INSIDE
    # the trunk. Before, the hook being global (Write|Edit), EVERY edit in any project
    # triggered two full scans of the trunk and appended a line to metrics.jsonl (over-frequency +
    # a polluted curve). We gate on belonging to the trunk.
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
