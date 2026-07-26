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
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_maintain as am          # réutilise launch_agent + session_msg_count
try:
    import brain_guard as guard
except Exception:
    guard = None

QUEUE = os.path.join(am.BRAIN, "state", "pending-distill.json")


def main():
    if guard is None:
        return
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        return                              # on est déjà un headless

    try:
        pending = json.load(open(QUEUE, encoding="utf-8"))
    except Exception:
        pending = []
    if not pending:
        return                              # rien en attente

    if not guard.preflight_ok():
        return                              # quota toujours épuisé → on retentera au prochain tic

    if not guard.acquire_lock():
        return                              # une maintenance tourne déjà

    # on prend la plus ancienne de façon ATOMIQUE (flock) : sûr même si un
    # SessionEnd enfile une nouvelle session pile au même instant.
    sid = guard.dequeue_one()
    if not sid:                             # file vidée entre-temps par un autre process
        guard.release_lock()
        return
    n = am.session_msg_count(sid) or am.MIN_MSG
    am.launch_agent(sid, n, to_distill=True)   # le wrapper libère le verrou en fin de run


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
