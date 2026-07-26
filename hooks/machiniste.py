#!/usr/bin/env python3
"""
Machiniste — le 8e agent du Claude Brain, couche MACHINE PHYSIQUE.

Les 7 autres agents entretiennent le savoir ; le mécanicien entretient l'infra du Brain.
Le machiniste, lui, entretient **la machine qui fait tourner tout ça** : RAM, CPU, chaleur.

Il tourne SANS LLM (launchd, toutes les 10 min) — coût zéro, aucun quota consommé.
Il ne réfléchit pas, il applique des règles vérifiables. L'analyse fine est le boulot de
l'agent `machiniste.md`, qui lit ce que ce démon a mesuré.

DOCTRINE DE SÛRETÉ — un tueur automatique qui se trompe détruit du travail.
  · Il ne tue QUE des serveurs de dev ORPHELINS, INACTIFS et VIEUX. Trois conditions, toutes requises.
  · Tout le reste est SIGNALÉ, jamais touché.
  · Une liste de protection en dur + une liste éditable par l'utilisateur passent avant tout.
  · Chaque action est journalisée avec sa justification complète.

Usage :
  python3 machiniste.py            # ronde normale (mesure + actions sûres)
  python3 machiniste.py --dry-run  # montre ce qu'il ferait, ne touche à rien
  python3 machiniste.py --report   # dernier état, lisible
"""
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone

BRAIN = os.path.realpath(os.path.expanduser("~/claude-brain"))
STATE = os.path.join(BRAIN, "state")
SNAPSHOT = os.path.join(STATE, "machiniste.json")       # dernier état, écrasé
JOURNAL = os.path.join(STATE, "machiniste.jsonl")       # historique, append-only
PROTECT = os.path.join(STATE, "machiniste-protect.txt") # patterns éditables par l'utilisateur
LOG = os.path.join(BRAIN, "sessions", "machiniste.log")

PAGE = 16384  # taille de page mémoire sur Apple Silicon

# --- Ce qu'on ne touche JAMAIS, quoi qu'il arrive -----------------------------
#     Sessions de travail, agents de sécurité, applications, infra système, la capsule.
#
#     ⚠️ Leçon du test du 2026-07-25 : une première version matchait le mot « claude »
#     n'importe où dans la ligne de commande. Résultat, TOUT process dont le chemin
#     contenait « claude » (donc tout ~/claude-brain/, tout /tmp/claude-501/) devenait
#     intouchable — le filet attrapait tout et ne prouvait plus rien. On ancre donc les
#     motifs sur l'exécutable, pas sur un fragment de chemin.
NEVER_KILL = re.compile(
    r"(?:^|/)claude(?:\s|$)"                    # le binaire claude lui-même
    # ⚠️ 2e piège du même test : « .app/Contents/MacOS/ » paraissait désigner les apps GUI.
    #    En réalité TOUS les interpréteurs Python vivent dans un bundle .app
    #    (Homebrew comme CommandLineTools) — la règle rendait donc immune le serveur
    #    VoiceShell qui avait motivé tout ce travail. On ancre sur /Applications/.
    r"|^/Applications/|^/System/Applications/|/Applications/[^/]+\.app/Contents/"
    r"|/System/|/usr/libexec/|/usr/sbin/|/sbin/"  # infra système
    r"|(?:^|/)(gpg-agent|ssh-agent|launchd|sshd|cron)(?:\s|$)"
    r"|node_modules/electron"                   # la capsule du Brain
    r"|(?:^|/)(Code|Cursor|Xcode|Docker)(?:\s|$)",
    re.I)

# --- Serveurs de dev : le seul gibier autorisé -------------------------------
#     Motifs volontairement précis. Un motif trop large tuerait du vrai travail.
DEV_SERVER = re.compile(
    r"(backend/server\.py|manage\.py\s+runserver|uvicorn|gunicorn|flask\s+run|"
    r"http\.server|vite(\s|$)|next\s+dev|nodemon|webpack(-dev-server)?|"
    r"rails\s+s(erver)?|php\s+-S|serve\s+-p|live-server)",
    re.I)

MIN_AGE_S = 20 * 60      # un orphelin doit avoir au moins 20 min pour être suspect
IDLE_SAMPLE_S = 5        # fenêtre d'échantillonnage pour prouver l'inactivité
IDLE_MAX_CPU_S = 0.2     # au-delà, le process travaille → on ne touche pas
MIN_FOOTPRINT_MB = 200   # en dessous, ça ne vaut pas le risque


def sh(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                           text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ============================ CAPTEURS ======================================

def read_memory():
    """État mémoire réel. Le 'compressé' est la métrique qui compte sur 16 Go."""
    out = sh(["vm_stat"])
    vals = {}
    for line in out.splitlines():
        m = re.match(r"([^:]+):\s+(\d+)", line)
        if m:
            vals[m.group(1).strip()] = int(m.group(2))
    g = lambda k: vals.get(k, 0) * PAGE / 1073741824
    swap = sh(["sysctl", "-n", "vm.swapusage"])
    sm = re.search(r"used\s*=\s*([\d.,]+)M", swap)
    return {
        "active_gb": round(g("Pages active"), 2),
        "wired_gb": round(g("Pages wired down"), 2),
        "inactive_gb": round(g("Pages inactive"), 2),
        "free_gb": round(g("Pages free"), 2),
        "compressed_gb": round(g("Pages occupied by compressor"), 2),
        "swap_mb": round(float((sm.group(1) if sm else "0").replace(",", ".")), 1),
    }


def read_cpu():
    """Charge et fréquence. Pas de température : elle exige sudo (powermetrics)."""
    up = sh(["uptime"])
    la = re.search(r"averages?:?\s*([\d.,]+)[,\s]+([\d.,]+)[,\s]+([\d.,]+)", up)
    f = lambda s: float(s.replace(",", "."))
    ncpu = int(sh(["sysctl", "-n", "hw.ncpu"]).strip() or 8)
    return {
        "load1": f(la.group(1)) if la else 0.0,
        "load5": f(la.group(2)) if la else 0.0,
        "load15": f(la.group(3)) if la else 0.0,
        "ncpu": ncpu,
        "uptime_days": round(float(sh(["sysctl", "-n", "kern.boottime"]) and
                                   (time.time() - _boottime()) / 86400 or 0), 2),
    }


def _boottime():
    m = re.search(r"sec\s*=\s*(\d+)", sh(["sysctl", "-n", "kern.boottime"]))
    return int(m.group(1)) if m else time.time()


def footprint_mb(pid):
    """Empreinte PHYSIQUE, compression comprise.

    Le piège trouvé le 2026-07-25 : un serveur VoiceShell abandonné affichait 10 Mo de
    RSS alors qu'il retenait 2,2 Go. Tout son contenu était compressé, donc invisible
    dans `ps` et dans le Moniteur d'activité trié par RSS. Seul vmmap dit la vérité.
    """
    out = sh(["vmmap", "--summary", str(pid)], timeout=25)
    m = re.search(r"Physical footprint:\s+([\d.]+)([KMG])", out)
    if not m:
        return None
    n, unit = float(m.group(1)), m.group(2)
    return n * (1024 if unit == "G" else 1 if unit == "M" else 1 / 1024)


def cpu_time_s(pid):
    t = sh(["ps", "-o", "time=", "-p", str(pid)]).strip()
    m = re.match(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", t)
    if not m:
        return None
    d, h, mi, s = m.groups()
    return (int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi) * 60 + float(s))


def load_protect():
    """Patterns supplémentaires que l'utilisateur veut sanctuariser. Un par ligne."""
    pats = []
    try:
        with open(PROTECT) as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line:
                    pats.append(line)
    except FileNotFoundError:
        pass
    return pats


def scan_processes():
    """Inventaire : pid, ppid, âge, commande. Un seul appel ps."""
    out = sh(["ps", "-Ao", "pid=,ppid=,etime=,command="])
    procs = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        pid, ppid, etime, cmd = parts
        try:
            procs.append({"pid": int(pid), "ppid": int(ppid),
                          "age_s": _etime_s(etime), "cmd": cmd})
        except ValueError:
            continue
    return procs


def _etime_s(e):
    m = re.match(r"(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$", e)
    if not m:
        return 0
    d, h, mi, s = m.groups()
    return int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi) * 60 + int(s)


def _ancestors():
    """Toute la chaîne de parenté du machiniste lui-même — intouchable par construction."""
    out, pid = set(), os.getpid()
    while pid and pid > 1:
        out.add(pid)
        try:
            pid = int(sh(["ps", "-o", "ppid=", "-p", str(pid)]).strip() or 0)
        except ValueError:
            break
    return out


def has_live_connection(pid):
    """Un serveur avec une connexion ÉTABLIE est en train de servir quelqu'un."""
    out = sh(["lsof", "-a", "-p", str(pid), "-i", "-P", "-n"], timeout=15)
    return "ESTABLISHED" in out


# ============================ DÉCISION ======================================

def find_zombies(procs, protect, dry):
    """Serveurs de dev orphelins, inactifs, vieux et gros. Les 4 conditions.

    Orphelin (ppid == 1) veut dire : le terminal qui l'a lancé est mort. Un serveur
    lancé au premier plan ou avec & dans un shell ouvert a le shell pour parent —
    il n'est donc JAMAIS candidat. C'est ce qui rend la règle sûre.
    """
    found, killed = [], []
    ancetres = _ancestors()          # jamais se tirer une balle dans le pied
    for p in procs:
        cmd = p["cmd"]
        if p["pid"] in ancetres:                          continue
        if p["ppid"] != 1:                                continue
        if not DEV_SERVER.search(cmd):                    continue
        if NEVER_KILL.search(cmd):                        continue
        if any(pat in cmd for pat in protect):            continue
        if p["age_s"] < MIN_AGE_S:                        continue

        fp = footprint_mb(p["pid"])
        if fp is None or fp < MIN_FOOTPRINT_MB:           continue

        # Preuve d'inactivité : on échantillonne, on ne suppose pas.
        c0 = cpu_time_s(p["pid"])
        time.sleep(IDLE_SAMPLE_S)
        c1 = cpu_time_s(p["pid"])
        if c0 is None or c1 is None:                      continue
        delta = c1 - c0
        if delta > IDLE_MAX_CPU_S:                        continue
        if has_live_connection(p["pid"]):                 continue

        item = {"pid": p["pid"], "cmd": cmd[:160], "age_min": round(p["age_s"] / 60),
                "footprint_mb": round(fp), "cpu_delta_s": round(delta, 3),
                "raison": "serveur de dev orphelin, inactif et vieux"}
        found.append(item)
        if not dry:
            try:
                os.kill(p["pid"], 15)          # SIGTERM : on demande, on n'arrache pas
                time.sleep(3)
                try:
                    os.kill(p["pid"], 0)
                    item["resultat"] = "SIGTERM ignoré — laissé en vie, à voir à la main"
                except ProcessLookupError:
                    item["resultat"] = "arrêté proprement"
                    killed.append(item)
            except ProcessLookupError:
                item["resultat"] = "déjà mort"
            except PermissionError:
                item["resultat"] = "permission refusée"
        else:
            item["resultat"] = "dry-run"
    return found, killed


def find_reportable(procs, mem, cpu):
    """Ce qu'on SIGNALE sans y toucher. Le jugement revient à l'utilisateur ou à l'agent."""
    alerts = []
    if mem["compressed_gb"] > 5:
        alerts.append({"niveau": "warn", "sujet": "ram-compressee",
                       "msg": f"{mem['compressed_gb']} Go compressés — "
                              "ferme des onglets ou redémarre, ça ne redescend pas seul"})
    if mem["swap_mb"] > 2000:
        alerts.append({"niveau": "warn", "sujet": "swap",
                       "msg": f"{mem['swap_mb']} Mo de swap — la machine écrit sur le SSD"})
    if cpu["load15"] > cpu["ncpu"]:
        alerts.append({"niveau": "warn", "sujet": "charge",
                       "msg": f"charge 15 min {cpu['load15']} > {cpu['ncpu']} cœurs — file d'attente"})
    if cpu["uptime_days"] > 5:
        alerts.append({"niveau": "info", "sujet": "uptime",
                       "msg": f"{cpu['uptime_days']} jours sans redémarrage — "
                              "la mémoire compressée s'accumule"})

    # Doublons de capsule (cf. lesson electron-zombie-process-cleanup)
    caps = [p for p in procs if "claude-brain/capsule/node_modules/electron/dist" in p["cmd"]
            and "--type=" not in p["cmd"]]
    if len(caps) > 1:
        alerts.append({"niveau": "warn", "sujet": "capsule-doublon",
                       "msg": f"{len(caps)} instances de capsule — pids "
                              f"{[c['pid'] for c in caps]}"})

    # Orphelins gros mais hors périmètre de tir : on les nomme, on les laisse vivre.
    for p in procs:
        if p["ppid"] != 1 or p["age_s"] < MIN_AGE_S:      continue
        if NEVER_KILL.search(p["cmd"]) or DEV_SERVER.search(p["cmd"]): continue
        if not re.search(r"(python|node|ruby|java|deno|bun)", p["cmd"], re.I): continue
        fp = footprint_mb(p["pid"])
        if fp and fp > 500:
            alerts.append({"niveau": "info", "sujet": "orphelin-inconnu",
                           "msg": f"pid {p['pid']} · {round(fp)} Mo · "
                                  f"{p['cmd'][:90]} — orphelin non reconnu, NON touché"})
    return alerts


# ============================ SORTIE ========================================

def write_out(payload):
    os.makedirs(STATE, exist_ok=True)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(SNAPSHOT, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    with open(JOURNAL, "a") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    if payload["actions"] or payload["alertes"]:
        with open(LOG, "a") as f:
            f.write(f"\n[{payload['quand']}] compressé {payload['memoire']['compressed_gb']} Go · "
                    f"swap {payload['memoire']['swap_mb']} Mo · charge {payload['cpu']['load15']}\n")
            for a in payload["actions"]:
                f.write(f"  ⚑ TUÉ pid {a['pid']} ({a['footprint_mb']} Mo) — {a['cmd'][:90]}\n")
            for a in payload["alertes"]:
                f.write(f"  · [{a['niveau']}] {a['sujet']} : {a['msg']}\n")


def report():
    try:
        with open(SNAPSHOT) as f:
            d = json.load(f)
    except Exception:
        print("Aucune ronde enregistrée. Lance : python3 machiniste.py")
        return
    m, c = d["memoire"], d["cpu"]
    print(f"🔧 Machiniste — dernière ronde {d['quand']}")
    print(f"   RAM   compressée {m['compressed_gb']} Go · libre {m['free_gb']} Go · swap {m['swap_mb']} Mo")
    print(f"   CPU   charge {c['load1']} / {c['load5']} / {c['load15']} sur {c['ncpu']} cœurs")
    print(f"   Uptime {c['uptime_days']} j")
    if d["actions"]:
        print("   Actions :")
        for a in d["actions"]:
            print(f"     ⚑ pid {a['pid']} ({a['footprint_mb']} Mo) — {a.get('resultat')}")
    if d["alertes"]:
        print("   Signalements :")
        for a in d["alertes"]:
            print(f"     · [{a['niveau']}] {a['msg']}")
    if not d["actions"] and not d["alertes"]:
        print("   ✅ rien à signaler")


def main():
    if "--report" in sys.argv:
        return report()
    dry = "--dry-run" in sys.argv

    procs = scan_processes()
    mem, cpu = read_memory(), read_cpu()
    protect = load_protect()
    candidats, tues = find_zombies(procs, protect, dry)
    alertes = find_reportable(procs, mem, cpu)
    mem_apres = read_memory() if tues else mem

    payload = {
        "quand": now_iso(),
        "dry_run": dry,
        "memoire": mem,
        "memoire_apres": mem_apres,
        "libere_gb": round(mem["compressed_gb"] - mem_apres["compressed_gb"], 2),
        "cpu": cpu,
        "actions": candidats,
        "alertes": alertes,
    }
    write_out(payload)
    if dry or "--verbose" in sys.argv:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Un démon ne casse jamais la machine qu'il surveille : il sort 0, il note.
        try:
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            with open(LOG, "a") as f:
                f.write(f"[{now_iso()}] ERREUR machiniste : {e}\n")
        except Exception:
            pass
    sys.exit(0)
