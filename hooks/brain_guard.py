#!/usr/bin/env python3
"""brain_guard — rend la maintenance autonome increvable face aux tokens / au compte.

Garanties :
  - jamais de crash (tout échoue en douceur),
  - jamais d'état à moitié (lock + reprise),
  - jamais de perte de session (file d'attente retentée),
  - jamais de "distillé à tort" sur un 429 (lecture du RÉSULTAT, pas du code retour).

Principe : la cohérence structurelle du cerveau ne dépend JAMAIS d'un appel LLM.
Un problème de quota/compte ne fait que DIFFÉRER la distillation, jamais casser le système.
"""
import os, sys, json, time, subprocess, hashlib, re, fcntl

BRAIN = os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))
STATE = os.path.join(BRAIN, "state")
LOCK  = os.path.join(STATE, "maintenance.lock")
QUEUE = os.path.join(STATE, "pending-distill.json")   # sessions à distiller plus tard
QUOTA = os.path.join(STATE, "quota.json")             # {"blocked_until": epoch, "msg": ...}
LOGIN = os.path.join(STATE, "login.json")             # {"logged_out": bool, "ts": ..., "msg": ...}
LOCK_TTL = 20 * 60   # au-delà : lock réputé mort (process zombie / Mac en veille)


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


# --- A. Verrou avec récupération des zombies (corrige le 'busy' bloqué) -----
def acquire_lock(sid=None) -> bool:
    """True si on prend le verrou. Récupère un verrou périmé / process mort,
    ré-enfile la session interrompue et débloque le statut resté 'busy'."""
    payload = {"pid": os.getpid(), "ts": time.time(),
               "sid": sid, "account": account_fingerprint()}
    # Création ATOMIQUE (O_EXCL) : ferme la course « deux SessionEnd lisent en même temps
    # 'pas de lock' et le prennent tous les deux ». Si le fichier n'existe pas, on le crée
    # d'un seul syscall ; sinon on bascule sur la logique de récupération du zombie ci-dessous.
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
        pass                                 # FS sans O_EXCL → repli sur la récupération
    cur = _rj(LOCK, None)
    if cur and _alive(cur.get("pid")) and (time.time() - cur.get("ts", 0)) < LOCK_TTL:
        return False                         # une VRAIE maintenance tourne → on n'en lance pas 2
    if cur:                                  # lock périmé ou process mort → on le reprend
        if cur.get("sid"):
            enqueue(cur["sid"])              # la session interrompue repart en file
        _status_idle()                       # on débloque le statut resté 'busy'
    _wj(LOCK, payload)
    return True


def update_lock_pid(pid):
    """Réinscrit le lock avec le PID du WORKER DÉTACHÉ. Indispensable : le hook qui prend le
    lock (auto_maintain / resume_pending) MEURT juste après avoir spawné le worker ; sans ça,
    `_alive(pid)` voit un PID mort → la session suivante répute le lock périmé et lance une
    maintenance EN PARALLÈLE (race git/Inbox, cf. [[headless-concurrent-git-race]]). On y inscrit
    le PID du `sh -c` détaché, vivant toute la passe ; le worker fait `release` en fin de course."""
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
    """Identité approx. du compte actif, sans lire de secret. Les creds Claude Code
    sont dans le Keychain macOS : on se base sur l'account_uuid présent dans les
    transcripts récents (signal fiable du compte qui a tourné)."""
    try:
        tdir = os.path.join(os.path.expanduser("~/.claude/projects"), os.path.expanduser("~").replace(os.sep, "-"))
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


# --- C. Preflight : a-t-on le droit de dépenser des tokens maintenant ? -----
def preflight_ok() -> bool:
    """Ne consomme AUCUN token : lit un marqueur de quota posé par un run précédent."""
    q = _rj(QUOTA, None)
    if q and time.time() < q.get("blocked_until", 0):
        return False                         # quota épuisé, reset pas encore atteint
    return True


def _parse_reset_epoch(msg: str):
    """'... resets 2:50pm (Europe/Paris)' → epoch best-effort ; défaut +1h."""
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


# --- D. Lecture du résultat : LA correction du piège 429 -------------------
def interpret_result(last_cost_line: str, sid: str, is_distill: bool = True) -> bool:
    """True si le run a VRAIMENT réussi. Sinon : ré-enfile (si distill) + marqueur adéquat.
    Corrige deux pièges où le CLI sort en code 0 avec is_error=true :
      - 429 (quota)        → on lit le RÉSULTAT, on pose le marqueur quota.
      - "Not logged in"    → le headless détaché part sans session authentifiée et
        échoue en <1 s. On pose un marqueur login ET on ré-enfile la session pour la
        rejouer au prochain SessionEnd authentifié → aucune session jamais perdue."""
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
            enqueue(sid)                      # rien distillé → on rejouera une fois connecté
        return False
    if r.get("is_error") or r.get("api_error_status"):
        if is_distill:
            enqueue(sid)                      # NON distillé → retenté plus tard
        if r.get("api_error_status") == 429 or "limit" in rl:
            _wj(QUOTA, {"blocked_until": _parse_reset_epoch(res), "msg": res[:200]})
        return False
    _wj(LOGIN, {"logged_out": False, "ts": time.time()})   # run OK → session bien authentifiée
    _wj(QUOTA, {"blocked_until": 0, "msg": "ok"})          # tokens revenus → on lève le blocage
    return True


# --- E. File d'attente : aucune session perdue -----------------------------
# Toutes les mutations de la file passent par _with_queue, qui prend un verrou
# EXCLUSIF (flock) sur le fichier le temps du read-modify-write. Indispensable :
# quand on ferme PLUSIEURS sessions à la fois, autant de SessionEnd s'exécutent en
# parallèle et appellent enqueue() simultanément ; sans verrou, le dernier write
# écrase les précédents → des sessions disparaissent de la file. Le flock sérialise.
def _with_queue(mutate):
    """Ouvre la file sous verrou exclusif, applique mutate(list)->(new_list, ret),
    réécrit atomiquement, renvoie ret. Tolère l'absence de fcntl (fallback best-effort)."""
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
    """Vide la file et renvoie tout son contenu, atomiquement."""
    return _with_queue(lambda q: ([], q))


def dequeue_one():
    """Retire et renvoie la session la plus ancienne (None si vide), atomiquement.
    À préférer à drain+réenfile quand on ne traite qu'UNE session par passage."""
    def m(q):
        if not q:
            return q, None
        s = q.pop(0)
        return q, s
    return _with_queue(m)


# --- CLI : utilisé par le wrapper shell de auto_maintain -------------------
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "interpret":
        # interpret <cost.jsonl> <sid> [distill 0|1] → exit 0 si succès, 7 sinon
        try:
            last = open(sys.argv[2], encoding="utf-8").read().splitlines()[-1]
        except Exception:
            last = "{}"
        sid = sys.argv[3] if len(sys.argv) > 3 else ""
        is_distill = (sys.argv[4] != "0") if len(sys.argv) > 4 else True
        ok = interpret_result(last, sid, is_distill)
        if not ok and _rj(LOGIN, {}).get("logged_out"):
            print("[brain_guard] not logged in — session ré-enfilée, rejouée au "
                  "prochain SessionEnd. Lance `claude /login` pour réactiver les agents.",
                  file=sys.stderr)
        sys.exit(0 if ok else 7)
    elif cmd == "release":
        release_lock(); sys.exit(0)
    elif cmd == "preflight":
        sys.exit(0 if preflight_ok() else 7)
    sys.exit(0)
