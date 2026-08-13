#!/usr/bin/env python3
"""
Hook SessionEnd du C Brain — maintenance AUTONOME complète (phase 2).
À la fin d'une session, en arrière-plan détaché, enchaîne :
  1. DISTILLER  : le distillateur extrait les fiches durables de la session finie
  2. RANGER     : le jardinier vide l'Inbox, déduplique, affine, optimise
  3. COMMIT     : versionné

Remplace maybe_garden.py (qui ne faisait que ranger). Ici on distille AUSSI,
automatiquement, sans rien déclencher à la main.

Garde-fous quotas/boucles :
  - anti-récursion : CLAUDE_BRAIN_GARDENING=1 (le headless ne se relance pas)
  - une distillation MAX par session (marqueur sessions/.distilled.json)
  - sessions triviales ignorées (< MIN_MSG messages)
  - ne spawn que s'il y a du travail (session substantielle non distillée OU Inbox pleine)
  - détaché : ne bloque jamais la fermeture de session

Sort toujours 0.
"""
import os, sys, re, json, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from brain_status import write_status
except Exception:
    def write_status(*a, **k): pass
try:
    import brain_guard as guard
except Exception:
    guard = None

BRAIN = os.path.realpath((os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk")))
MEMORY = os.path.join(BRAIN, "MEMORY.md")
SESS = os.path.join(BRAIN, "sessions")
INDEX = os.path.join(SESS, ".index.json")          # écrit par archive_session.py
DISTILLED = os.path.join(SESS, ".distilled.json")  # sessions déjà distillées
LOG = os.path.join(SESS, "gardening.log")
INBOX_HEADER = "## 🆕 Inbox — fiches à classer (auto)"
# Nom du dossier transcripts = $HOME avec "/" -> "-" (convention Claude Code) ; ne
# JAMAIS coder le nom d'utilisateur en dur (cf. [[restauration-machine-2026-07-22]]).
TRANSCRIPTS = os.path.join(os.path.expanduser("~/.claude/projects"), os.path.expanduser("~").replace(os.sep, "-"))
MANUAL_SAVES = os.path.join(BRAIN, "state", "manual-saves.jsonl")  # ledger posé par on_fiche_write
MIN_MSG = 20  # en dessous : session triviale, pas de distillation

def inbox_has_work():
    try:
        mem = open(MEMORY, encoding="utf-8").read()
    except Exception:
        return False
    if INBOX_HEADER not in mem:
        return False
    return bool(re.search(r'^\s*-\s*\[', mem.split(INBOX_HEADER, 1)[1], re.M))

def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def manual_saves_for(sid):
    """Fiches de savoir écrites À LA MAIN pendant la session `sid` (ledger posé par on_fiche_write).
    Sert à dire au distillateur de NE PAS recréer ce que Claude a déjà enregistré (anti-redondance).
    Best-effort : ledger absent/illisible → liste vide (le distillateur tourne normalement)."""
    out = []
    if not sid:
        return out
    try:
        for line in open(MANUAL_SAVES, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("sid") == sid and e.get("path") and e["path"] not in out:
                out.append(e["path"])
    except Exception:
        pass
    return out

def ensure_capsule():
    """Ouvre la capsule Tamagotchi si elle n'est pas déjà en cours (réveil des agents).

    Mode léger : si le fichier state/no-capsule existe, on ne relance rien.
    La capsule (Electron + son helper GPU) est le plus gros consommateur CPU
    de la machine au repos ; sur un MacBook Air sans ventilateur elle force
    WindowServer à recomposer l'écran en continu."""
    try:
        if os.path.exists(os.path.join(BRAIN, "state", "no-capsule")):
            return
        cap = os.path.join(BRAIN, "capsule")
        elec = os.path.join(cap, "node_modules", ".bin", "electron")
        if not os.path.exists(elec):
            return
        # le vrai process tourne sous .../node_modules/electron/dist/... (le .bin/electron
        # n'est qu'un symlink), donc on matche le chemin du projet, pas le symlink.
        r = subprocess.run(["pgrep", "-f", "c-brain/trunk/capsule/node_modules/electron"],
                           capture_output=True, text=True)
        if r.stdout.strip():
            return  # déjà ouverte
        env = dict(os.environ)
        # Sans ça, le lancement automatique ouvrait la V1 (la créature), pas
        # l'ORBE : seul un lancement manuel avec CAPSULE_SOLO=1 la montrait.
        env["CAPSULE_SOLO"] = "1"
        subprocess.Popen([elec, "."], cwd=cap, env=env,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        pass

def session_msg_count(sid):
    """Nombre de messages de la session. Source primaire = l'index écrit par
    archive_session.py. MAIS les deux hooks SessionEnd partent en parallèle :
    si l'archivage est lent/annulé, l'index ne contient pas encore la session
    (n=0) et la distillation des grosses sessions est sautée à tort.
    Fallback robuste à la course : on compte directement les lignes du .jsonl."""
    idx = load_json(INDEX, {})
    if sid in idx and isinstance(idx[sid], dict):
        n = idx[sid].get("n", 0)
        if n:
            return n
    # index muet (course de hooks) → compte direct dans le transcript brut
    if sid:
        path = os.path.join(TRANSCRIPTS, f"{sid}.jsonl")
        try:
            with open(path, "rb") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            pass
    return 0

def launch_agent(sid, n, to_distill):
    """Lance le headless de maintenance (distill+jardin OU jardin seul) et le câble
    à brain_guard. Suppose que le verrou est DÉJÀ pris par l'appelant.
    Réutilisé par le SessionEnd (main) et par l'auto-reprise (resume_pending)."""
    claude = shutil.which("claude")
    if not claude:
        # `claude` introuvable — cas typique sous launchd (PATH minimal /usr/bin:/bin, sans
        # ~/.local/bin). L'appelant (resume_pending) a DÉJÀ dé-filé la session : si on rend juste
        # le lock, elle est perdue (jamais distillée) → garantie « zéro perte » violée. On la
        # RÉ-ENFILE avant de rendre le lock ; un SessionEnd interactif (PATH complet) la rejouera.
        if guard is not None:
            if to_distill and sid:
                guard.enqueue(sid)
            guard.release_lock()
        return

    ensure_capsule()  # la capsule s'ouvre au réveil des agents

    # ARCHITECTURE SANS PARENT (optimisation « zéro perte ») : on n'instancie PLUS
    # un LLM parent qui se contente d'orchestrer en spawnant deux sous-agents — ce
    # parent ne faisait aucun travail intellectuel mais relisait à chaque tour les
    # résultats remontés des sous-agents (gros cache_read pur gâchis). Désormais le
    # shell séquence directement DEUX appels `claude -p --agent …` (le distillateur
    # PUIS le jardinier), et fait lui-même les pulses capsule + le commit (mécaniques,
    # zéro LLM). Même travail, même qualité, un contexte LLM en moins.
    py = sys.executable
    status_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_status.py")
    mark_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mark_distilled.py")
    guard_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_guard.py")
    upkeep_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_upkeep.py")
    embed_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_embed.py")
    embed2_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_embed2.py")
    graph_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph_export.py")
    coact_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coactivation.py")
    doctor_cli = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_doctor.py")
    cost = os.path.join(BRAIN, "sessions", "cost.jsonl")
    transcript = os.path.join(TRANSCRIPTS, f"{sid}.jsonl")

    # Les tâches : l'appel EST l'agent (via --agent), donc plus de « lance le
    # sous-agent X » — on lui donne directement sa mission. Consigne anti-gâchis :
    # ne pas relire un fichier déjà lu, ne pas committer (le shell s'en charge).
    distill_task = (
        f"Une session vient de se terminer (id={sid}, {n} messages, "
        f"transcript: {transcript}, note d'archive éventuelle dans sessions/archive/). "
        "Extrais les fiches/leçons DURABLES uniquement. ÉCONOMIE DE TOKENS IMPÉRATIVE : "
        "NE lis PAS le transcript en entier ; base-toi sur la note d'archive, au besoin "
        "grep + lis au plus ~60 lignes ciblées. Ne relis JAMAIS un fichier déjà lu. "
        "Si rien ne mérite de rester, ne crée rien. NE committe PAS (le shell s'en charge). "
        "Sois concis dans ton rapport."
    )
    # ANTI-REDONDANCE (option B) : les fiches que Claude a déjà écrites À LA MAIN pendant la session
    # ne doivent pas être recréées par le distillateur (sinon doublon transitoire + tokens gâchés). On
    # le lui dit explicitement ; il garde le filet pour le savoir NON sauvé.
    already = manual_saves_for(sid)
    if already:
        distill_task += (
            " IMPORTANT — Claude a DÉJÀ écrit/affiné ces fiches à la main pendant cette session : "
            + ", ".join(already) +
            ". NE LES RECRÉE PAS ; complète-les seulement s'il manque vraiment quelque chose, et "
            "n'extrais que le savoir DURABLE qu'elles ne couvrent pas encore."
        )
    garden_task = (
        "Vide l'Inbox de MEMORY.md, range chaque fiche dans la bonne carte "
        "(leçons dans lessons/INDEX.md, autres fiches dans MEMORY.md), "
        "déduplique, répare/tisse les liens [[...]], masque tout secret, affine. "
        "Ne relis pas inutilement un fichier déjà lu. NE committe PAS (le shell s'en "
        "charge). Sois concis dans ton rapport."
    )

    env = dict(os.environ)
    env["CLAUDE_BRAIN_GARDENING"] = "1"
    try:
        logf = open(LOG, "a")
    except Exception:
        logf = subprocess.DEVNULL

    write_status("busy", "distilling" if to_distill else "gardening",
                 "Waking the agents…", source="agent")

    state_dir = os.path.join(BRAIN, "state")
    dpf = os.path.join(state_dir, ".distill.txt")
    gpf = os.path.join(state_dir, ".garden.txt")
    try:
        os.makedirs(state_dir, exist_ok=True)
        open(dpf, "w", encoding="utf-8").write(distill_task)
        open(gpf, "w", encoding="utf-8").write(garden_task)
    except Exception:
        if guard is not None:
            guard.release_lock()
        return

    # Modèle PAR AGENT. Le distillateur est le seul étage créatif de la couche 1 : son
    # échec perd du savoir définitivement (le jardinage, lui, est mécanique et rejouable).
    # D'où sonnet pour distiller, haiku pour ranger. cf. brain_upkeep.MODEL, même logique.
    MODEL_L1 = {"distillateur": "sonnet", "jardinier": "haiku"}
    base = lambda m: (f'"{claude}" -p --model {m} --output-format json '
                      f'--dangerously-skip-permissions')
    pulse = lambda act, det: f'"{py}" "{status_cli}" busy {act} "{det}"'
    # commit MÉCANIQUE (pas de LLM) : auteur « C Brain », ne casse jamais si rien à committer.
    commit = (f'git -C "{BRAIN}" add -A && '
              f'git -C "{BRAIN}" -c user.name="C Brain" -c user.email=brain@local '
              f'commit -q -m "auto: maintenance ($(date \'+%Y-%m-%d %H:%M\'))" || true')

    # Garde anti-faux-positif (crash OS / SIGKILL du binaire `claude` AVANT d'écrire) :
    # `interpret` lit la DERNIÈRE ligne de cost.jsonl. Si claude meurt sans rien écrire,
    # cette dernière ligne est celle du run PRÉCÉDENT (peut-être un succès) → fausse
    # réussite → session marquée distillée sans l'être → savoir perdu. Parade : on compte
    # les lignes avant l'appel ; si aucune n'a été ajoutée, on injecte une ligne d'erreur
    # synthétique → `interpret` voit bien CE run, échoue, et ré-enfile la session.
    sentinel = ('{"is_error":true,'
                '"result":"claude exited without writing output (SIGKILL/crash?)"}')
    nlines = f"$(awk 'END{{print NR}}' \"{cost}\" 2>/dev/null || echo 0)"

    def agent_call(agent, pf):
        return [
            f'__N0={nlines}',
            f'{base(MODEL_L1.get(agent, "haiku"))} --agent {agent} "$(cat {pf})" '
            f'>> "{cost}" 2>> "{LOG}"',
            f'if [ "{nlines}" -le "$__N0" ]; then '
            f"printf '%s\\n' '{sentinel}' >> \"{cost}\"; fi",
        ]

    lines = []
    # HEARTBEAT capsule : pendant toute la passe, un fond rafraîchit `ts` toutes les 5 s
    # (un appel `claude -p` dure des minutes sans réécrire le statut → sans ça la capsule
    # clignote en idle au milieu du travail). Borné à 600 itér. (~50 min) en sécurité au
    # cas où le kill final n'aurait pas lieu, et tué explicitement juste avant `idle`.
    lines.append(f'( __i=0; while [ $__i -lt 600 ]; do "{py}" "{status_cli}" touch '
                 f'>/dev/null 2>&1; sleep 5; __i=$((__i+1)); done ) & __HB=$!')
    if to_distill:
        # 1) DISTILLER directement via --agent distillateur, puis interpréter le
        #    résultat (df=1 : ré-enfile la session si « Not logged in »/quota/crash).
        #    Le jardinage n'a lieu que si la distillation a RÉELLEMENT réussi.
        lines.append(pulse("distilling", "Distilling this session"))
        lines += agent_call("distillateur", dpf)
        lines.append(f'if "{py}" "{guard_cli}" interpret "{cost}" "{sid}" 1 ; then')
        lines.append(f'  "{py}" "{mark_cli}" "{sid}"')
        lines.append(f'  {pulse("gardening", "Organizing the tree")}')
        lines += ['  ' + l for l in agent_call("jardinier", gpf)]
        lines.append('fi')
    else:
        # Jardinage seul (Inbox pleine, pas de session à distiller).
        lines.append(pulse("gardening", "Organizing the tree"))
        lines += agent_call("jardinier", gpf)
        lines.append(f'"{py}" "{guard_cli}" interpret "{cost}" "{sid}" 0')
    # GARDE MÉCANIQUE post-jardinier (zéro LLM) : le jardinier est seul juge de sa propre
    # passe. brain_doctor recompte les défauts (liens morts, orphelins, frontmatter,
    # hors-carte, taille de MEMORY) JUSTE APRÈS lui, et trace le verdict dans gardening.log. Il ne corrige
    # rien — le mécanicien s'en charge plus tard, via son capteur. Ici on veut seulement
    # qu'une passe de jardinage qui dégrade l'arbre soit VISIBLE tout de suite, au lieu
    # d'attendre jusqu'à 12 h le prochain réveil du mécanicien.
    lines.append(f'"{py}" "{doctor_cli}" --json >/dev/null 2>&1')
    lines.append(
        f'''__D=$("{py}" -c 'import json;print(json.load(open("{BRAIN}/state/doctor.json"))["total"])' 2>/dev/null || echo -1); '''
        f'''if [ "$__D" != "0" ]; then echo "[doctor] $(date '+%F %T') post-jardinage: $__D defaut(s)" >> "{LOG}"; fi''')
    # SECONDE COUCHE (veille de cohésion) : après distill+jardin, régénère les capteurs
    # mécaniques (gratuit) et réveille AU PLUS un agent de veille (challenger / architecte
    # / archiviste) si son seuil est franchi et son cooldown respecté. brain_upkeep gère
    # seul priorité, cadence et coût (best-effort, ne perd aucune donnée s'il échoue).
    # brain_upkeep pulse lui-même l'activité capsule de l'agent qu'il réveille (ou rien).
    lines.append(f'"{py}" "{upkeep_cli}" run "{sid}"')
    # F4/O2 — rafraîchit l'index sémantique du recall (brain_embed `build` est
    # INCRÉMENTAL : il ne réencode que les fiches dont le contenu a changé, via hash).
    # Coût quasi nul, zéro LLM (modèle d'embeddings local), et le recall reste à jour
    # au lieu de tourner sur un index périmé. Placé après distill+jardin pour indexer
    # les fiches fraîches, juste avant le commit. IMPORTANT : brain_embed a besoin de
    # numpy/model2vec → on l'invoque avec le python du .venv (le python système des
    # hooks ne les a pas) ; absent → on saute silencieusement (|| true).
    venv_py = os.path.join(BRAIN, ".venv", "bin", "python")
    if os.path.exists(venv_py):
        # HF_HUB_OFFLINE=1 : le modèle d'embeddings est déjà en cache local → on évite
        # un aller-retour réseau HF Hub à chaque passe (plus rapide, marche hors-ligne).
        lines.append(f'HF_HUB_OFFLINE=1 "{venv_py}" "{embed_cli}" build >> "{LOG}" 2>&1 || true')
        # Étage 1 — recalcule la carte SÉMANTIQUE (state/embed2.json) à partir de l'index frais,
        # puis régénère planet/graph.json pour que la vue « sens » (touche S) reflète le contenu courant.
        lines.append(f'HF_HUB_OFFLINE=1 "{venv_py}" "{embed2_cli}" >> "{LOG}" 2>&1 || true')
    # Étage 2 — recalcule la mémoire de travail (chaleur d'usage + liens de co-activation) depuis les
    # logs de recall/lecture, AVANT graph_export (qui lit coactivation.json). Pur stdlib.
    lines.append(f'"{py}" "{coact_cli}" >> "{LOG}" 2>&1 || true')
    lines.append(f'"{py}" "{graph_cli}" >> "{LOG}" 2>&1 || true')
    # commit + idle + release : TOUJOURS, quoi qu'il arrive au-dessus.
    lines.append(pulse("committing", "Saving to git"))
    lines.append(commit)
    lines.append('kill "$__HB" >/dev/null 2>&1 || true')   # stoppe le heartbeat AVANT idle
    lines.append(f'"{py}" "{status_cli}" idle')
    lines.append(f'"{py}" "{guard_cli}" release')
    wrapper = "\n".join(lines)

    try:
        proc = subprocess.Popen(
            ["sh", "-c", wrapper],
            cwd=BRAIN, env=env,
            stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
            start_new_session=True,
        )
        # le hook qui détient le lock va mourir ; on y inscrit le PID du worker détaché
        # (vivant toute la passe) → une autre session voit un lock VIVANT et n'en lance pas 2.
        if guard is not None:
            try:
                guard.update_lock_pid(proc.pid)
            except Exception:
                pass
    except Exception:
        write_status("idle")
        if guard is not None:
            guard.release_lock()


def main():
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        return  # on EST déjà le headless de maintenance

    # GEL DES ÉCRIVAINS AUTONOMES (Phase 0 du RFC Brain V3, 2026-08-03).
    # Pendant la construction du Brain V3 hors production, le distillateur, le
    # jardinier et brain_upkeep continueraient à modifier le tronc — et depuis
    # que le commit automatique est coupé, ils le feraient SANS trace dans git.
    # Le lab travaillerait alors sur une base qui bouge sous lui, et le
    # rattrapage lab↔prod deviendrait impossible à raisonner.
    #
    # La file d'attente, elle, continue de se remplir (capture-only) : rien
    # n'est perdu, tout sera distillé après la bascule.
    #
    # Lever le gel : supprimer ~/.c-brain/trunk/state/FREEZE
    freeze = os.path.join(BRAIN, "state", "FREEZE")
    if os.path.exists(freeze):
        try:
            data = json.loads(sys.stdin.read() or "{}")
            sid = data.get("session_id")
            if sid:
                guard.enqueue(sid)  # capture-only : on note, on ne traite pas
        except Exception:
            pass
        return

    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        data = {}
    sid = data.get("session_id")

    distilled = set(load_json(DISTILLED, []))
    n = session_msg_count(sid) if sid else 0
    to_distill = bool(sid) and sid not in distilled and n >= MIN_MSG
    to_garden = inbox_has_work()

    if not (to_distill or to_garden):
        return  # rien à faire → aucun agent lancé

    claude = shutil.which("claude")
    if not claude:
        return

    # --- garde-fous tokens/compte (brain_guard) ---------------------------
    if guard is not None:
        if not guard.acquire_lock(sid):
            # Une maintenance tourne déjà (ex. plusieurs sessions fermées en même
            # temps : la 1re a pris le verrou). On ne double PAS (anti-corruption),
            # mais on ENFILE cette session pour qu'elle soit distillée ensuite —
            # sinon elle serait silencieusement perdue. Drainée par le prochain
            # SessionEnd ou par resume_pending (launchd, ~10 min).
            if to_distill:
                guard.enqueue(sid)
            return
        if not guard.preflight_ok():
            # quota épuisé (reset pas encore atteint) → on DIFFÈRE, jamais de crash
            if to_distill:
                guard.enqueue(sid)
            guard.release_lock()
            return
        # quota OK : on rejoue d'abord la session en attente la plus ancienne
        # (backlog accumulé pendant que le quota/login était KO), une par passage.
        # On la retire ATOMIQUEMENT (dequeue_one) : le reste de la file reste sur
        # DISQUE, jamais en mémoire. L'ancien drain_queue() vidait tout d'un coup
        # puis ré-enfilait le reste — un kill du process entre les deux engloutissait
        # tout le backlog (bug observé la nuit du 24/06, surface par `brain audit`).
        resume_sid = guard.dequeue_one()
        if resume_sid:
            if to_distill and resume_sid != sid:
                guard.enqueue(sid)               # session courante reportée d'un cran
            sid, to_distill = resume_sid, True
            n = session_msg_count(sid) or MIN_MSG

    launch_agent(sid, n, to_distill)

if __name__ == "__main__":
    try:
        # `--capsule` : ouvrir l'orbe SANS déclencher de maintenance. Appelé par le
        # hook SessionStart. Avant ça, ensure_capsule() n'avait qu'un seul appelant
        # (launch_agent, en FIN de session) : l'orbe ne s'ouvrait donc jamais pendant
        # qu'on travaille — 12 h de session sans jamais la voir (constat de l'auteur,
        # 2026-08-04). Elle s'efface toujours seule au repos, ce mode ne force rien.
        if "--capsule" in sys.argv:
            ensure_capsule()
        else:
            main()
    except Exception:
        pass
    sys.exit(0)
