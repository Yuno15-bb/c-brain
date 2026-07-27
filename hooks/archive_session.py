#!/usr/bin/env python3
"""
Hook SessionEnd du Claude Brain.
At the end of every session:
  1. refreshes the lossless index sessions/TIMELINE.md (incremental cache, fast)
  2. captures the git diff of the project worked on (cwd) into sessions/archive/
  3. commit le tronc ~/claude-brain pour versionner la croissance
  4. pushes to the private remote if configured (silent, non-blocking, offline is fine)

Golden rule: NEVER block or fail the session. Always exits 0.
"""
import sys, os, json, re, glob, subprocess
from datetime import datetime

def _transcripts_key() -> str:
    """The folder name Claude Code uses for this HOME, under ~/.claude/projects.

    It encodes the absolute home path by replacing BOTH "/" and "." with "-".
    Replacing only "/" works for a plain account name and breaks silently for a
    home like /Users/john.smith: the transcripts folder is never found, so
    distillation runs and finds nothing to do. No error, no signal.
    """
    return os.path.expanduser("~").replace("/", "-").replace(".", "-")


BRAIN = os.path.expanduser("~/claude-brain")
# Nom du dossier transcripts = $HOME avec "/" -> "-" (convention Claude Code).
# NEVER hardcode the user name here (it silently broke distillation during a
# distillation lors de la migration d'un compte utilisateur vers un autre, cf. [[restauration-machine-2026-07-22]]).
PROJECTS_DIR = os.path.join(os.path.expanduser("~/.claude/projects"), _transcripts_key())
SESSIONS = os.path.join(BRAIN, "sessions")
ARCHIVE = os.path.join(SESSIONS, "archive")
CACHE = os.path.join(SESSIONS, ".index.json")

SECRET = re.compile(
    r'(ntn_[A-Za-z0-9]+|sk-ant-[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+|secret_[A-Za-z0-9]+'
    r'|eyJ[A-Za-z0-9_.-]{20,}|[A-Za-z0-9_-]{32,}\.apps\.googleusercontent|gh[pousr]_[A-Za-z0-9]{20,})'
)
def redact(s): return SECRET.sub("«SECRET-MASKED»", s or "")

# Session filing table: keyword (lowercase) → project name.
# FILL IT IN with YOUR projects — this is what files your archived sessions.
# Left empty, everything lands in "UNSORTED" — still correct, but not very useful.
# Exemple :
#   PROJ = {
#       'facture': 'Compta', 'devis': 'Compta',
#       'shader': 'Graphismes', 'wallpaper': 'Graphismes',
#   }
PROJ = {
}
def classify(topic):
    low = (topic or "").lower()
    return next((v for k, v in PROJ.items() if k in low), "UNSORTED")

def parse_transcript(path):
    """start date, subject (first text message), message count."""
    ts = topic = None; nmsg = 0
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            for line in f:
                try: o = json.loads(line)
                except Exception: continue
                if o.get('type') in ('user', 'assistant'): nmsg += 1
                if o.get('timestamp') and ts is None: ts = o['timestamp']
                if topic is None and o.get('type') == 'user':
                    c = o.get('message', {}).get('content'); t = None
                    if isinstance(c, str): t = c
                    elif isinstance(c, list):
                        for p in c:
                            if isinstance(p, dict) and p.get('type') == 'text': t = p.get('text'); break
                    if t:
                        t = t.strip()
                        if t.startswith('<') or t.startswith('Caveat') or 'system-reminder' in t[:40] or t.startswith('[Request'):
                            continue
                        topic = redact(re.sub(r'\s+', ' ', t))[:200]
    except Exception:
        pass
    return ts, topic, nmsg

def load_cache():
    try:
        return json.load(open(CACHE, encoding='utf-8'))
    except Exception:
        return {}

def rebuild_timeline():
    """Incremental: only re-parses the .jsonl files whose mtime changed."""
    cache = load_cache()
    changed = False
    for path in glob.glob(os.path.join(PROJECTS_DIR, "*.jsonl")):
        pid = os.path.basename(path)[:-6]
        mt = os.path.getmtime(path)
        ent = cache.get(pid)
        if ent and abs(ent.get("mtime", 0) - mt) < 1:
            continue
        ts, topic, n = parse_transcript(path)
        if not topic:
            topic = "(resumed through a brief file — no initial text message)"
        cache[pid] = {"mtime": mt, "ts": ts or "z", "date": (ts[:10] if ts else "?"),
                      "proj": classify(topic), "n": n, "topic": topic}
        changed = True
    if changed or not os.path.exists(os.path.join(SESSIONS, "TIMELINE.md")):
        json.dump(cache, open(CACHE, "w", encoding='utf-8'), ensure_ascii=False, indent=0)
        write_timeline(cache)
    return cache, changed

def write_timeline(cache):
    rows = sorted(cache.values(), key=lambda e: e["ts"])
    out = ["# 🕰️ Timeline — every Claude Code session\n",
           "A **lossless** index of every session. Raw transcripts: "
           f"`{PROJECTS_DIR}/<id>.jsonl`. Kept up to date automatically by the SessionEnd hook. "
           "Secrets are masked automatically.\n"]
    cur = None
    for e in rows:
        mois = e["date"][:7]
        if mois != cur:
            cur = mois; out.append(f"\n## {mois}\n")
        out.append(f"- **{e['date']}** · `{e['proj']}` · {e['n']} msg — {e['topic']}")
    from collections import Counter
    c = Counter(e["proj"] for e in rows)
    out.append("\n\n---\n\n## Summary by area\n")
    for k, v in c.most_common(): out.append(f"- **{k}** — {v} sessions")
    out.append(f"\n\n*Total: {len(rows)} sessions. Last updated: {datetime.now():%Y-%m-%d %H:%M}.*\n")
    open(os.path.join(SESSIONS, "TIMELINE.md"), "w", encoding='utf-8').write("\n".join(out))

def capture_git_diff(cwd):
    """If cwd is a git repo (and not the trunk itself), capture a summary of the diff."""
    if not cwd or os.path.realpath(cwd) == os.path.realpath(BRAIN):
        return None
    try:
        inside = subprocess.run(["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=10)
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        stat = subprocess.run(["git", "-C", cwd, "diff", "--stat"],
                              capture_output=True, text=True, timeout=15).stdout.strip()
        status = subprocess.run(["git", "-C", cwd, "status", "--short"],
                                capture_output=True, text=True, timeout=15).stdout.strip()
        branch = subprocess.run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, timeout=10).stdout.strip()
        if not (stat or status):
            return None
        return {"branch": branch, "stat": stat, "status": status}
    except Exception:
        return None

def write_archive_note(data, cache):
    sid = data.get("session_id", "unknown")
    pid = sid
    ent = cache.get(pid, {})
    cwd = data.get("cwd", "")
    reason = data.get("reason", "?")
    git = capture_git_diff(cwd)
    date = ent.get("date") or f"{datetime.now():%Y-%m-%d}"
    proj = ent.get("proj", classify(cwd))
    os.makedirs(ARCHIVE, exist_ok=True)
    safe_proj = re.sub(r'[^A-Za-z0-9]+', '-', proj).strip('-').lower()
    fn = os.path.join(ARCHIVE, f"{date}_{safe_proj}_{sid[:8]}.md")
    lines = [
        "---",
        f"name: session-{sid[:8]}",
        f"description: Archive auto de session {date} · {proj}",
        "metadata:\n  type: reference",
        "---\n",
        f"# Session {date} — {proj}\n",
        f"- **Subject**: {ent.get('topic','(not captured)')}",
        f"- **Messages** : {ent.get('n','?')}",
        f"- **Fin** : `{reason}`",
        f"- **Dossier** : `{cwd}`",
        f"- **Transcript brut** : `{PROJECTS_DIR}/{sid}.jsonl`",
    ]
    if git:
        lines.append(f"\n## Diff git (`{git['branch']}`)\n")
        if git["stat"]:
            lines.append("```\n" + redact(git["stat"])[:3000] + "\n```")
        if git["status"]:
            lines.append("\n**Files touched (status):**\n```\n" + redact(git["status"])[:2000] + "\n```")
    else:
        lines.append("\n*(No git diff captured — cwd outside a repo, or nothing changed.)*")
    open(fn, "w", encoding='utf-8').write("\n".join(lines))
    return fn

def commit_brain():
    try:
        subprocess.run(["git", "-C", BRAIN, "add", "-A"], capture_output=True, timeout=20)
        diff = subprocess.run(["git", "-C", BRAIN, "diff", "--cached", "--quiet"], timeout=20)
        if diff.returncode == 0:
            return  # nothing to commit
        subprocess.run(["git", "-C", BRAIN,
                        "-c", "user.name=Claude Brain", "-c", "user.email=brain@local",
                        "commit", "-q", "-m",
                        f"auto: archivage session ({datetime.now():%Y-%m-%d %H:%M})"],
                       capture_output=True, timeout=20)
        push_brain()
    except Exception:
        pass

def push_brain():
    """Pushes to the remote if configured. Silent and non-blocking (offline is fine)."""
    try:
        has_remote = subprocess.run(["git", "-C", BRAIN, "remote"],
                                    capture_output=True, text=True, timeout=10)
        if not has_remote.stdout.strip():
            return  # no remote → nothing to push
        subprocess.run(["git", "-C", BRAIN, "push", "--quiet"],
                       capture_output=True, timeout=30)
    except Exception:
        pass  # offline or push refused → we never block the end of a session

def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}
    try:
        cache, _ = rebuild_timeline()
        if data.get("session_id"):
            write_archive_note(data, cache)
        commit_brain()
    except Exception:
        pass  # jamais bloquer la session
    sys.exit(0)

if __name__ == "__main__":
    main()
