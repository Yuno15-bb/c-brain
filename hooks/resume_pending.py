#!/usr/bin/env python3
"""resume_pending — reprise autonome du backlog de distillation.

Run periodically (launchd, roughly every 10 min). If:
  - le quota est revenu (preflight_ok),
  - la file pending-distill.json n'est pas vide,
  - no maintenance is already running (the lock is free),
alors il distille la session en attente la plus ancienne (une par passage).

→ Answers: "window closed + quota exhausted → does it resume by itself on reset?"
  YES: without opening anything, the backlog drains as soon as the quota resets.

Always exits 0. Does nothing (and costs nothing) with no work, or while the quota is still spent.
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_maintain as am          # reuses launch_agent + session_msg_count
try:
    import brain_guard as guard
except Exception:
    guard = None

QUEUE = os.path.join(am.BRAIN, "state", "pending-distill.json")


def main():
    if guard is None:
        return
    if os.environ.get("CLAUDE_BRAIN_GARDENING") == "1":
        return                              # we are already a headless run

    try:
        pending = json.load(open(QUEUE, encoding="utf-8"))
    except Exception:
        pending = []
    if not pending:
        return                              # rien en attente

    if not guard.preflight_ok():
        return                              # quota still spent → retry on the next tick

    if not guard.acquire_lock():
        return                              # maintenance is already running

    # take the oldest one ATOMICALLY (flock): safe even if a SessionEnd queues
    # a new session at the very same moment.
    sid = guard.dequeue_one()
    if not sid:                             # queue drained meanwhile by another process
        guard.release_lock()
        return
    n = am.session_msg_count(sid) or am.MIN_MSG
    am.launch_agent(sid, n, to_distill=True)   # the wrapper releases the lock at the end of the run


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
