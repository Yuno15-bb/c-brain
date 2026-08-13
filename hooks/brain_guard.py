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

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
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


# Recul progressif quand le message ne dit PAS quand ça repart (heures).
# Mesuré le 2026-08-07 : « monthly spend limit » et « weekly limit » ne portent
# aucune heure de reset. L'ancien défaut de +1 h traitait donc un plafond HEBDO
# comme une pause d'une heure : toutes les heures le blocage expirait, la
# maintenance repartait, se faisait refuser, re-bloquait 1 h — en boucle toute la
# journée, sans jamais rien distiller. Le défaut n'était pas la file, c'était son
# délai d'attente. cf. [[account-quota-resilience]].
_RECUL_H = [1, 2, 4, 8, 12, 24]


def _famille_limite(msg: str) -> str:
    """Trois familles, parce qu'elles ne repartent PAS au même rythme.
    'session' porte son heure de reset dans le message ; les deux autres non."""
    m = msg.lower()
    if "monthly spend limit" in m or "spend limit" in m:
        return "plafond"          # plafond de dépense : reset mensuel / relevé à la main
    if "weekly limit" in m or "week" in m:
        return "hebdo"            # limite hebdomadaire
    return "session"


def _parse_reset_epoch(msg: str, echecs: int = 0):
    """Quand repart-on ? Deux régimes :
      - le message donne l'heure ('... resets 2:50pm') → on la lit, c'est exact ;
      - il ne la donne pas (plafond, hebdo) → recul PROGRESSIF indexé sur le nombre
        d'échecs consécutifs, jamais un retry par heure jusqu'à la fin des temps.
    `echecs` = compteur porté par le marqueur de quota (0 au premier échec)."""
    try:
        m = re.search(r'resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)', msg, re.I)
        if m:
            h = int(m.group(1)) % 12
            if m.group(3).lower() == "pm":
                h += 12
            mn = int(m.group(2) or 0)
            now = time.localtime()
            target = list(now); target[3] = h; target[4] = mn; target[5] = 0
            t = time.mktime(time.struct_time(tuple(target)))
            if t < time.time():
                t += 24 * 3600                # reset demain
            return t
        # pas d'heure dans le message → recul progressif, plafonné à 24 h
        pas = _RECUL_H[min(max(echecs, 0), len(_RECUL_H) - 1)]
        return time.time() + pas * 3600
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
            # Le compteur d'échecs CONSÉCUTIFS pilote le recul et sert de capteur :
            # sans lui, rien ne distinguait « premier refus » de « neuvième refus
            # d'affilée », et le système repartait à l'identique à chaque fois.
            prec = _rj(QUOTA, None) or {}
            fam = _famille_limite(res)
            echecs = (prec.get("echecs", 0) + 1) if prec.get("famille") == fam else 1
            _wj(QUOTA, {"blocked_until": _parse_reset_epoch(res, echecs - 1),
                        "famille": fam, "echecs": echecs,
                        "depuis": prec.get("depuis") if prec.get("famille") == fam else time.time(),
                        "msg": res[:200]})
        return False
    _wj(LOGIN, {"logged_out": False, "ts": time.time()})   # run OK → session bien authentifiée
    # tokens revenus → on lève le blocage ET on remet le compteur d'échecs à zéro,
    # sinon le prochain refus repartirait au dernier palier de recul.
    _wj(QUOTA, {"blocked_until": 0, "famille": None, "echecs": 0, "msg": "ok"})
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


# --- F. Fiches au traitement INACHEVÉ --------------------------------------
# Le trou nommé par l'auteur le 2026-08-07 : la file suit des SESSIONS, pas des fiches.
# Une distillation tuée en plein vol ré-enfile sa session (bien). Mais une
# distillation qui se TERMINE en laissant une fiche à moitié écrite marque la
# session comme traitée : le trou devient invisible, et aucun compteur ne bouge.
# Ce contrôle regarde le RÉSULTAT sur le disque, pas le code de sortie du run.
_FICHE_SKIP = ("sessions", "corpus", "node_modules", "capsule", "capsule-v2",
               "planet", "audits", "tools", "state", "companion", "tests", ".git")
CORPS_MIN = 120          # sous ce seuil, la fiche n'a pas de contenu utile


def _lire_fiche(path):
    """(frontmatter, corps) ou None si le fichier n'a pas la forme d'une fiche."""
    try:
        t = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return None
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', t, re.S)
    return (m.group(1), m.group(2)) if m else None


def fiches_incompletes(brain=None):
    """Liste les fiches dont le traitement n'est jamais allé au bout.
    Trois symptômes, chacun constatable sur le fichier lui-même :
      - pas de frontmatter        → écriture interrompue avant l'en-tête
      - name/description absents  → en-tête commencé, jamais rempli
      - corps < CORPS_MIN         → en-tête posé, contenu jamais écrit
    Mesuré sur le tronc réel au moment de l'écriture : 0 fiche signalée sur 314.
    Un contrôle qui crie sur un tronc sain est un contrôle qu'on apprend à ignorer."""
    brain = brain or BRAIN
    out = []
    for root, dirs, files in os.walk(brain):
        rel_root = os.path.relpath(root, brain)
        tete = rel_root.split(os.sep)[0]
        if tete in _FICHE_SKIP:
            dirs[:] = []
            continue
        for f in files:
            # MEMORY.md / INDEX.md / README.md sont des CARTES, pas des fiches :
            # elles n'ont pas de frontmatter par conception. Les signaler, c'est
            # apprendre à ignorer le contrôle.
            if not f.endswith(".md") or f in ("MEMORY.md", "README.md", "INDEX.md"):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, brain)
            fm_corps = _lire_fiche(p)
            if fm_corps is None:
                out.append({"fiche": rel, "motif": "pas de frontmatter", "sid": None})
                continue
            fm, corps = fm_corps
            motifs = []
            if not re.search(r'^\s*name\s*:', fm, re.M):
                motifs.append("name absent")
            if not re.search(r'^\s*description\s*:', fm, re.M):
                motifs.append("description absente")
            if len(corps.strip()) < CORPS_MIN:
                motifs.append("corps vide")
            if motifs:
                m = re.search(r'originSessionId\s*:\s*([0-9a-fA-F-]+)', fm)
                out.append({"fiche": rel, "motif": ", ".join(motifs),
                            "sid": m.group(1) if m else None})
    return out


MAX_REPRISES = 2          # au-delà, on cesse de rejouer et on le DIT


def reenfiler_inacheves(brain=None, journal=None):
    """Remet en file les sessions des fiches inachevées qui portent leur origine.

    ⚠ Le piège fermé ici : une fiche qui reste incomplète APRÈS retraitement se
    remettrait en file à chaque passage du timer — une boucle qui brûle des tokens
    toutes les dix minutes, exactement ce qu'on cherche à éviter. D'où un compteur
    de tentatives par session, plafonné : au-delà, la session n'est plus rejouée,
    elle est signalée. Un abandon visible vaut mieux qu'une boucle invisible.

    Renvoie (nb_fiches_signalees, nb_sessions_reenfilees, nb_abandonnees)."""
    journal = journal or os.path.join(STATE, "inacheves.json")
    inc = fiches_incompletes(brain)
    hist = _rj(journal, {}) or {}
    sids = {x["sid"] for x in inc if x["sid"]}
    reenfilees, abandonnees = 0, 0
    for s in sids:
        essais = hist.get(s, {}).get("essais", 0)
        if essais >= MAX_REPRISES:
            abandonnees += 1
            continue
        enqueue(s)
        hist[s] = {"essais": essais + 1, "ts": time.time()}
        reenfilees += 1
    # une session dont les fiches sont redevenues saines sort de l'historique
    for s in list(hist):
        if s not in sids:
            hist.pop(s, None)
    _wj(journal, hist)
    return len(inc), reenfilees, abandonnees


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
    elif cmd == "inacheves":
        # inacheves [--reenfiler] → liste les fiches au traitement inachevé.
        # Exit 0 si le tronc est sain, 7 s'il en reste — pour qu'un contrôle
        # automatique puisse RÉAGIR au lieu de se contenter d'afficher.
        inc = fiches_incompletes()
        for x in inc:
            print(f"  ⚠ {x['fiche']} — {x['motif']}"
                  + (f" (session {x['sid'][:8]})" if x["sid"] else " (origine inconnue)"))
        if "--reenfiler" in sys.argv:
            n, s, ab = reenfiler_inacheves()
            print(f"[brain_guard] {n} fiche(s) inachevée(s), {s} session(s) ré-enfilée(s)"
                  + (f", {ab} abandonnée(s) après {MAX_REPRISES} tentatives" if ab else ""))
        elif not inc:
            print("[brain_guard] aucune fiche inachevée")
        sys.exit(0 if not inc else 7)
    sys.exit(0)
