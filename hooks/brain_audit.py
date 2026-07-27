#!/usr/bin/env python3
"""brain_audit — état opérationnel du pipeline de distillation (≠ brain_doctor).

brain_doctor vérifie la COHÉRENCE du savoir (liens, orphelins, frontmatter).
brain_audit répond à la question née de la nuit du 24/06 : « qu'est-ce qui a été
PERDU / est en attente, et le système va-t-il bien ? » — sans rien modifier.

Il croise la couche brute (transcripts) avec ce qui a été distillé / mis en file,
et lit les marqueurs de résilience (verrou, quota, login) pour donner un verdict.

Principe rassurant central : un transcript présent = JAMAIS perdu irréversiblement.
« Perdu » ne veut dire que « pas encore distillé » → rattrapable tant que le .jsonl existe.

Usage :
  brain_audit.py            → rapport lisible
  brain_audit.py --json     → écrit state/audit.json (pour hooks) + rapport
  brain_audit.py --quiet    → exit code seulement (0 sain / 1 attention)
"""
import os, sys, json, time, glob, subprocess

BRAIN = os.path.realpath(os.path.expanduser("~/.c-brain/trunk"))
STATE = os.path.join(BRAIN, "state")
TDIR = os.path.join(os.path.expanduser("~/.claude/projects"), os.path.expanduser("~").replace(os.sep, "-"))   # couche brute (transcripts)
DISTILLED = os.path.join(BRAIN, "sessions", ".distilled.json")
MIN_MSG = 20                                                    # seuil de auto_maintain
# Naissance du système auto (tronc créé le 2026-06-21). Avant : pas d'auto-distillation
# → le savoir était capté à la main ; non-distillé n'y est PAS une anomalie.
INFRA_BIRTH = time.mktime(time.strptime("2026-06-21", "%Y-%m-%d"))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import brain_guard as guard          # réutilise lecture file/quota/login + verrou
except Exception:
    guard = None


def _rj(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


def _nlines(p):
    try:
        with open(p, "rb") as f:
            return sum(1 for l in f if l.strip())
    except Exception:
        return 0


def _last_commit():
    try:
        r = subprocess.run(["git", "-C", BRAIN, "log", "-1", "--format=%cr · %s"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return "?"


def collect():
    distilled = set(_rj(DISTILLED, []))
    queued = list(_rj(os.path.join(STATE, "pending-distill.json"), []))

    transcripts = []
    for p in glob.glob(os.path.join(TDIR, "*.jsonl")):
        sid = os.path.basename(p)[:-6]
        transcripts.append({"sid": sid, "n": _nlines(p), "mtime": os.path.getmtime(p)})

    pre, post = [], []
    for t in transcripts:
        if t["sid"] in distilled or t["sid"] in queued or t["n"] < MIN_MSG:
            continue
        (post if t["mtime"] >= INFRA_BIRTH else pre).append(t)
    pre.sort(key=lambda t: t["n"], reverse=True)
    post.sort(key=lambda t: t["mtime"], reverse=True)

    # --- santé du pipeline (marqueurs de résilience) ---
    quota = _rj(os.path.join(STATE, "quota.json"), {})
    login = _rj(os.path.join(STATE, "login.json"), {})
    lock = _rj(os.path.join(STATE, "maintenance.lock"), None)
    status = _rj(os.path.join(STATE, "status.json"), {})
    blocked = bool(quota.get("blocked_until", 0) > time.time())
    logged_out = bool(login.get("logged_out"))

    lock_state = "libre"
    if lock:
        pid_alive = guard._alive(lock.get("pid")) if guard else False
        stale = (time.time() - lock.get("ts", 0)) > (20 * 60)
        lock_state = "actif" if (pid_alive and not stale) else "périmé (sera récupéré)"

    return {
        "transcripts": len(transcripts),
        "distilled": len(distilled),
        "queued": queued,
        "pre_infra": pre,
        "post_infra": post,
        "quota_blocked": blocked,
        "quota_until": quota.get("blocked_until", 0),
        "logged_out": logged_out,
        "lock_state": lock_state,
        "status": status.get("state", "?"),
        "last_metric_ts": None,
        "last_commit": _last_commit(),
    }


def main():
    d = collect()
    # un transcript présent = récupérable → aucune perte IRRÉVERSIBLE possible
    irreversible_loss = 0
    health_ok = not d["quota_blocked"] and not d["logged_out"] and d["lock_state"] != "périmé (sera récupéré)"

    if "--json" in sys.argv:
        try:
            os.makedirs(STATE, exist_ok=True)
            json.dump(d, open(os.path.join(STATE, "audit.json"), "w"),
                      ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

    if "--quiet" not in sys.argv:
        ico = "✅" if health_ok else "⚠️"
        print(f"{ico} brain audit — pipeline de distillation")
        print(f"  Couche brute : {d['transcripts']} transcripts (jamais supprimés)")
        print(f"  Distillés    : {d['distilled']}   ·   en file d'attente : {len(d['queued'])}")
        print(f"  Perte irréversible : {irreversible_loss}  (transcript présent = rattrapable)")
        print()
        print(f"  Verrou maintenance : {d['lock_state']}   ·   statut capsule : {d['status']}")
        if d["quota_blocked"]:
            reste = int((d["quota_until"] - time.time()) / 60)
            print(f"  ⚠️  Quota épuisé — reprise dans ~{reste} min (file drainée au reset)")
        else:
            print(f"  Quota : OK")
        if d["logged_out"]:
            print(f"  ⚠️  Déconnecté — lance `claude /login` (sessions ré-enfilées en attendant)")
        print(f"  Dernier commit : {d['last_commit']}")

        if d["queued"]:
            print(f"\n  📥 En file de rattrapage ({len(d['queued'])}) — drainées 1/10 min par launchd :")
            for sid in d["queued"]:
                print(f"     {sid[:8]}")

        if d["post_infra"]:
            print(f"\n  🟠 Sessions substantielles non distillées DEPUIS le système auto "
                  f"({len(d['post_infra'])}) — vraies candidates au rattrapage :")
            for t in d["post_infra"]:
                when = time.strftime("%m-%d %H:%M", time.localtime(t["mtime"]))
                print(f"     {when}  {t['n']:>5} lignes  {t['sid'][:8]}")
        else:
            print(f"\n  ✅ Aucune session non distillée depuis le système auto.")

        if d["pre_infra"]:
            print(f"\n  ⚪ {len(d['pre_infra'])} sessions pré-infra non distillées — savoir capté "
                  f"à la main à l'époque, transcripts gardés en filet (pas une anomalie).")

    sys.exit(0 if health_ok else 1)


if __name__ == "__main__":
    main()
