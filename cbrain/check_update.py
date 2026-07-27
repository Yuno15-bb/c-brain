#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert. Source-available, see LICENSE.
#   Running it is allowed. Redistributing or rebuilding from it is not.
"""Quiet update check, wired to SessionStart.

Three non-negotiable rules:
  · NEVER blocking — at worst it says nothing. A session must not wait on the
    network to start.
  · At most one check per 24 h (timestamp on disk).
  · It updates NOTHING on its own. It reports; the user decides.

That is deliberate: code installing itself unasked is an execution channel into
somebody else's machine. Reporting costs nothing.

Always exits 0.
"""

import os
import subprocess
import sys
import time

CB = os.path.expanduser("~/.c-brain")
STAMP = os.path.join(CB, "state", "last-update-check")
INTERVAL = 24 * 3600


def main():
    engine = os.path.join(CB, "engine")
    if not os.path.isdir(engine):
        return 0

    # Throttle by timestamp file, not a lock. If the check crashes the stamp is
    # written anyway — we do not want a loop retrying on every session.
    now = time.time()
    try:
        if now - os.path.getmtime(STAMP) < INTERVAL:
            return 0
    except OSError:
        pass
    try:
        os.makedirs(os.path.dirname(STAMP), exist_ok=True)
        open(STAMP, "w").write(str(now))
    except OSError:
        return 0

    try:
        r = subprocess.run(["bash", os.path.join(engine, "cbrain", "update.sh"), "--check"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return 0   # offline, git missing, slow link: stay quiet

    if r.returncode == 10:      # update.sh convention: a newer version exists
        tag = ""
        for line in r.stdout.splitlines():
            if "new version available" in line:
                tag = line.split(":")[-1].strip()
        print(f"<c-brain-update>A new version of C Brain is available"
              f"{' (' + tag + ')' if tag else ''}. "
              f"Run `brain update` whenever it suits you — your notes will not be touched."
              f"</c-brain-update>")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # a hook NEVER breaks a session
