#!/usr/bin/env python3
"""resume_pending — reprise autonome du backlog de distillation.

Lancé périodiquement (launchd, toutes les ~10 min). Si :
  - le quota est revenu (preflight_ok),
  - la file pending-distill.json n'est pas vide,
  - aucune maintenance ne tourne déjà (verrou libre),
alors il distille la session en attente la plus ancienne (une par passage).

→ Répond à : « page fermée + quota fini → ça reprend tout seul à la réinitialisation ? »
  OUI : sans rien ouvrir, dès que le quota se réinitialise, le backlog se vide.

Sort toujours 0. Ne fait rien (et ne coûte rien) si pas de travail / quota encore épuisé.
"""
import os, sys, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_maintain as am          # réutilise launch_agent + session_msg_count
try:
    import brain_guard as guard
except Exception:
    guard = None

QUEUE = os.path.join(am.BRAIN, "state", "pending-distill.json")
JOURNAL_RATTRAPAGE = os.path.join(am.BRAIN, "state", "rattrapage.json")

# --- Rattrapage de l'arriéré : les sessions qui n'ont jamais atteint la file ---
#
# Trois freins, parce qu'ici on dépense sur du travail que PERSONNE n'a demandé :
#   - un délai de garde : un transcript encore chaud peut être une session OUVERTE ;
#   - une cadence lente : l'arriéré dort depuis des semaines, il n'y a aucune
#     urgence à le vider en une heure — et un agent coûte ~1 $, à comparer aux
#     ~0,00003 $ de la sonde de crédit ;
#   - un plafond de tentatives : une session qui échoue en boucle s'abandonne
#     visiblement plutôt que de brûler du budget en silence.
GARDE_SESSION_OUVERTE = 2 * 3600     # transcript inactif depuis 2 h → session vraiment close
CADENCE_RATTRAPAGE = 3600            # au plus un rattrapage d'arriéré par heure
MIN_LIGNES_ARRIERE = 60              # substance exigée : > MIN_MSG (20) du flux courant
MAX_TENTATIVES = 2

RATTRAPAGE_EN_COURS = set()          # sid choisis par arriere_a_rattraper() sur ce passage


def _journal():
    try:
        return json.load(open(JOURNAL_RATTRAPAGE, encoding="utf-8"))
    except Exception:
        return {}


def note_rattrapage(sid):
    """Trace la tentative AVANT le lancement — sinon un agent qui meurt sans écrire
    ne compte pas, et la même session repart indéfiniment (le piège de la boucle
    morte, cf. [[un-delai-devine-ne-sait-pas-que-tu-as-recharge]])."""
    j = _journal()
    j[sid] = {"essais": j.get(sid, {}).get("essais", 0) + 1, "ts": time.time()}
    j["_dernier"] = time.time()
    try:
        json.dump(j, open(JOURNAL_RATTRAPAGE, "w", encoding="utf-8"))
    except Exception:
        pass


def arriere_a_rattraper():
    """La session orpheline la plus récente qu'on s'autorise à distiller, ou None.

    Réutilise `brain_audit.collect()` : c'est déjà lui qui sait croiser les
    transcripts du disque avec les distillées et la file. On ne redécoupe pas ce
    calcul, on le branche enfin sur une action."""
    j = _journal()
    if time.time() - (j.get("_dernier") or 0) < CADENCE_RATTRAPAGE:
        return None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import brain_audit
        candidats = brain_audit.collect()["post_infra"]     # déjà triés du + récent au + ancien
    except Exception:
        return None
    for t in candidats:
        if t["n"] < MIN_LIGNES_ARRIERE:
            continue
        if time.time() - t["mtime"] < GARDE_SESSION_OUVERTE:
            continue                                        # peut-être encore ouverte
        if j.get(t["sid"], {}).get("essais", 0) >= MAX_TENTATIVES:
            continue                                        # abandon visible, pas silencieux
        RATTRAPAGE_EN_COURS.add(t["sid"])
        return t["sid"]
    return None


def main():
    if guard is None:
        return
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        return                              # on est déjà un headless

    # Le gel des écrivains autonomes vit dans auto_maintain.main(), et ce chemin-ci
    # ne passe PAS par main() : il appelle launch_agent directement. Le gel était
    # donc contournable toutes les dix minutes par le launchd, sans que personne le
    # voie. Même erreur que [[desarmer-le-hook-ne-suffit-pas-la-session-voisine-
    # commite-aussi]] : un verrou posé chez UN appelant ne protège pas des autres.
    # La file continue de se remplir — rien n'est perdu, tout attend le dégel.
    if os.path.exists(os.path.join(am.BRAIN, "state", "FREEZE")):
        return

    # Les fiches au traitement INACHEVÉ, avant de regarder la file — sinon une fiche
    # à moitié écrite avec une file vide ne serait jamais vue (le retour anticipé
    # ci-dessous coupe le passage). Le contrôle ne lit que des fichiers locaux :
    # zéro token, ~20 ms sur 314 fiches. Il plafonne lui-même ses reprises.
    try:
        guard.reenfiler_inacheves()
    except Exception:
        pass

    try:
        pending = json.load(open(QUEUE, encoding="utf-8"))
    except Exception:
        pending = []

    # La file ne contient que ce qui y est ENTRÉ, c'est-à-dire les sessions dont le
    # SessionEnd s'est déclenché. Une session tuée net — crash, veille, terminal
    # fermé d'un coup — n'exécute aucun code, donc ne s'enfile jamais : le retour du
    # crédit ne la concerne pas, elle n'attend nulle part. Constaté le 2026-08-13 :
    # file vide, et pourtant 8 vraies sessions de travail (22/07 → 03/08) jamais
    # distillées. `brain audit` les affichait depuis des semaines — le savoir était
    # là, il n'était juste relié à AUCUNE action. Même motif que le blocage quota du
    # même jour : un capteur qui constate mais n'agit pas.
    if not pending:
        orphelin = arriere_a_rattraper()
        if not orphelin:
            return                          # rien en attente, rien d'orphelin
        pending = [orphelin]                 # traité comme le reste, une par passage

    if not guard.preflight_ok():
        return                              # quota toujours épuisé → on retentera au prochain tic

    if not guard.acquire_lock():
        return                              # une maintenance tourne déjà

    # on prend la plus ancienne de façon ATOMIQUE (flock) : sûr même si un
    # SessionEnd enfile une nouvelle session pile au même instant.
    sid = guard.dequeue_one() or pending[0]
    if not sid:                             # file vidée entre-temps par un autre process
        guard.release_lock()
        return
    if sid in RATTRAPAGE_EN_COURS:
        note_rattrapage(sid)                 # trace AVANT le lancement : une tentative = une trace
    n = am.session_msg_count(sid) or am.MIN_MSG
    am.launch_agent(sid, n, to_distill=True)   # le wrapper libère le verrou en fin de run


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
