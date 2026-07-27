#!/usr/bin/env python3
"""brain_guard — rend la maintenance autonome increvable face aux tokens / au compte.

Garanties :
  - never a crash (everything fails gently),
  - never a half state (lock + resume),
  - never a lost session (a retried queue),
  - never a false "distilled" on a 429 (we read the RESULT, not the exit code).

Principle: the structural consistency of the brain NEVER depends on an LLM call.
A quota or account problem only DEFERS distillation; it never breaks the system.
"""
import os, sys, json, time, subprocess, hashlib, re, fcntl

def _transcripts_key() -> str:
    """The folder name Claude Code uses for this HOME, under ~/.claude/projects.

    It encodes the absolute home path by replacing BOTH "/" and "." with "-".
    Replacing only "/" works for a plain account name and breaks silently for a
    home like /Users/john.smith: the transcripts folder is never found, so
    distillation runs and finds nothing to do. No error, no signal.
    """
    return os.path.expanduser("~").replace("/", "-").replace(".", "-")


BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
STATE = os.path.join(BRAIN, "state")
LOCK  = os.path.join(STATE, "maintenance.lock")
QUEUE = os.path.join(STATE, "pending-distill.json")   # sessions to distil later
QUOTA = os.path.join(STATE, "quota.json")             # {"blocked_until": epoch, "msg": ...}
LOGIN = os.path.join(STATE, "login.json")             # {"logged_out": bool, "ts": ..., "msg": ...}
LOCK_TTL = 20 * 60   # past this: the lock is presumed dead (zombie process / machine asleep)


def _rj(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def _wj(p, o):
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(o, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass


def _alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def _status_idle():
    try:
        subprocess.run([sys.executable, os.path.join(BRAIN, "hooks", "brain_status.py"), "idle"],
                       timeout=10)
    except Exception:
        pass


# --- A. Lock with zombie reclaim (fixes the stuck 'busy' state) -----
def acquire_lock(sid=None) -> bool:
    """True if we take the lock. Reclaims a stale lock or a dead process,
    re-queues the interrupted session and unblocks a status stuck on 'busy'."""
    payload = {"pid": os.getpid(), "ts": time.time(),
               "sid": sid, "account": account_fingerprint()}
    # ATOMIC creation (O_EXCL): closes the race where "two SessionEnd hooks read
    # 'no lock' at the same time and both take it". If the file does not exist we create it
    # in a single syscall; otherwise we fall through to the zombie-reclaim logic below.
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, json.dumps(payload, ensure_ascii=False).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        pass
    except Exception:
        pass                                 # filesystem without O_EXCL → fall back to reclaim
    cur = _rj(LOCK, None)
    if cur and _alive(cur.get("pid")) and (time.time() - cur.get("ts", 0)) < LOCK_TTL:
        return False                         # une VRAIE maintenance tourne → on n'en lance pas 2
    if cur:                                  # stale lock or dead process → we take it over
        if cur.get("sid"):
            enqueue(cur["sid"])              # la session interrompue repart en file
        _status_idle()                       # unblock a status stuck on 'busy'
    _wj(LOCK, payload)
    return True


def update_lock_pid(pid):
    """Rewrites the lock with the PID of the DETACHED WORKER. Essential: the hook that takes
    the lock (auto_maintain / resume_pending) DIES right after spawning the worker; without this,
    `_alive(pid)` sees a dead PID → the next session declares the lock stale and starts a
    maintenance run IN PARALLEL (a git/Inbox race). We therefore write
    the PID of the detached `sh -c`, alive for the whole pass; the worker calls `release` at the end."""
    cur = _rj(LOCK, None) or {}
    cur["pid"] = int(pid)
    cur["ts"] = time.time()
    _wj(LOCK, cur)


def release_lock():
    try:
        os.remove(LOCK)
    except FileNotFoundError:
        pass
    except Exception:
        pass


# --- B. Compte actif (creds en Keychain → empreinte indirecte) -------------
def account_fingerprint() -> str:
    """Approximate identity of the active account, without reading any secret. Claude Code
    credentials live in the macOS Keychain: we rely on the account_uuid present in
    recent transcripts (a reliable signal of which account ran)."""
    try:
        tdir = os.path.join(os.path.expanduser("~/.claude/projects"), _transcripts_key())
        jsonls = sorted(
            (os.path.join(tdir, f) for f in os.listdir(tdir) if f.endswith(".jsonl")),
            key=os.path.getmtime, reverse=True)
        for p in jsonls[:1]:
            for line in open(p, encoding="utf-8"):
                m = re.search(r'"(?:accountUuid|account_uuid)"\s*:\s*"([^"]+)"', line)
                if m:
                    return hashlib.sha256(m.group(1).encode()).hexdigest()[:12]
    except Exception:
        pass
    return "unknown"


# --- C. Preflight: are we allowed to spend tokens right now? -----
def preflight_ok() -> bool:
    """Consumes NO token: reads a quota marker left by a previous run."""
    q = _rj(QUOTA, None)
    if q and time.time() < q.get("blocked_until", 0):
        return False                         # quota spent, reset not reached yet
    return True


def _parse_reset_epoch(msg: str):
    """'... resets 2:50pm (Europe/Paris)' → best-effort epoch; defaults to +1h."""
    try:
        m = re.search(r'resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)', msg, re.I)
        if not m:
            return time.time() + 3600
        h = int(m.group(1)) % 12
        if m.group(3).lower() == "pm":
            h += 12
        mn = int(m.group(2) or 0)
        now = time.localtime()
        target = list(now); target[3] = h; target[4] = mn; target[5] = 0
        t = time.mktime(time.struct_time(tuple(target)))
        if t < time.time():
            t += 24 * 3600                    # reset demain
        return t
    except Exception:
        return time.time() + 3600


# --- D. Reading the result: THE fix for the 429 trap -------------------
def interpret_result(last_cost_line: str, sid: str, is_distill: bool = True) -> bool:
    """True if the run REALLY succeeded. Otherwise: re-queue (if distilling) + the right marker.
    Fixes two traps where the CLI exits 0 with is_error=true:
      - 429 (quota)        → we read the RESULT and set the quota marker.
      - "Not logged in"    → the detached headless run starts unauthenticated and
        fails in under a second. We set a login marker AND re-queue the session so it
        replays at the next authenticated SessionEnd → no session is ever lost."""
    try:
        r = json.loads(last_cost_line)
    except Exception:
        r = {}
    res = str(r.get("result", ""))
    rl = res.lower()
    # --- garde-fou NOT LOGGED IN -----------------------------------------
    if "not logged in" in rl or "please run /login" in rl:
        _wj(LOGIN, {"logged_out": True, "ts": time.time(), "msg": res[:200]})
        if is_distill:
            enqueue(sid)                      # nothing distilled → we replay once logged in
        return False
    if r.get("is_error") or r.get("api_error_status"):
        if is_distill:
            enqueue(sid)                      # NOT distilled → retried later
        if r.get("api_error_status") == 429 or "limit" in rl:
            _wj(QUOTA, {"blocked_until": _parse_reset_epoch(res), "msg": res[:200]})
        return False
    _wj(LOGIN, {"logged_out": False, "ts": time.time()})   # run OK → the session was authenticated
    _wj(QUOTA, {"blocked_until": 0, "msg": "ok"})          # tokens are back → lift the block
    return True


# --- E. File d'attente : aucune session perdue -----------------------------
# Toutes les mutations de la file passent par _with_queue, qui prend un verrou
# EXCLUSIF (flock) sur le fichier le temps du read-modify-write. Indispensable :
# when SEVERAL sessions are closed at once, that many SessionEnd hooks run in
# parallel and call enqueue() simultaneously; without a lock, the last write
# overwrites the previous ones → sessions vanish from the queue. The flock serializes.
def _with_queue(mutate):
    """Ouvre la file sous verrou exclusif, applique mutate(list)->(new_list, ret),
    rewrites atomically, returns ret. Tolerates a missing fcntl (best-effort fallback)."""
    try:
        os.makedirs(STATE, exist_ok=True)
        f = open(QUEUE, "a+", encoding="utf-8")
    except Exception:
        q = _rj(QUEUE, [])
        nq, ret = mutate(list(q))
        _wj(QUEUE, nq)
        return ret
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
        except Exception:
            pass
        f.seek(0)
        raw = f.read().strip()
        try:
            q = json.loads(raw) if raw else []
        except Exception:
            q = []
        if not isinstance(q, list):
            q = []
        nq, ret = mutate(list(q))
        f.seek(0)
        f.truncate()
        f.write(json.dumps(nq, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())
        return ret
    finally:
        try:
            fcntl.flock(f, fcntl.LOCK_UN)
        except Exception:
            pass
        f.close()


def enqueue(sid):
    if not sid:
        return
    def m(q):
        if sid not in q:
            q.append(sid)
        return q, None
    _with_queue(m)


def drain_queue():
    """Empties the queue and returns all of its content, atomically."""
    return _with_queue(lambda q: ([], q))


def dequeue_one():
    """Retire et renvoie la session la plus ancienne (None si vide), atomiquement.
    Preferable to drain+re-queue when only ONE session is handled per pass."""
    def m(q):
        if not q:
            return q, None
        s = q.pop(0)
        return q, s
    return _with_queue(m)


# --- CLI: used by auto_maintain's shell wrapper -------------------
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "interpret":
        # interpret <cost.jsonl> <sid> [distill 0|1] → exit 0 on success, 7 otherwise
        try:
            last = open(sys.argv[2], encoding="utf-8").read().splitlines()[-1]
        except Exception:
            last = "{}"
        sid = sys.argv[3] if len(sys.argv) > 3 else ""
        is_distill = (sys.argv[4] != "0") if len(sys.argv) > 4 else True
        ok = interpret_result(last, sid, is_distill)
        if not ok and _rj(LOGIN, {}).get("logged_out"):
            print("[brain_guard] not logged in — session re-queued, it will replay at the "
                  "next SessionEnd. Run `claude /login` to reactivate the agents.",
                  file=sys.stderr)
        sys.exit(0 if ok else 7)
    elif cmd == "release":
        release_lock(); sys.exit(0)
    elif cmd == "preflight":
        sys.exit(0 if preflight_ok() else 7)
    sys.exit(0)
