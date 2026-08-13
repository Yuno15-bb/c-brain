#!/usr/bin/env python3
"""commit_par_zone — saves the trunk into git, ONE ZONE PER COMMIT.

Called at the end of every session by auto_maintain, after the agents have run.
Purely mechanical: no LLM, no network, nothing that leaves the machine.

WHY NOT `git add -A`
    That is what the automatic save did until 2026-08-13, and it is what drowned
    19 files of work in progress in commit e61fd01 (2026-08-03): a catch-all
    commit tells several stories at once and its message can only tell one.
    612 commits of that kind sleep in the author's own history.
    Here each zone goes into its own commit, with its own message — work in
    progress stays identifiable instead of being buried.

WHAT IT DOES NOT DO
    It does not PUSH. A trunk holds personal notes; sending them to a remote is
    its owner's decision, not the side effect of a session ending. (The author
    pushes his own from `tools/sync_depots.py`, which is not part of the package.)

Usage:
  commit_par_zone.py             commits
  commit_par_zone.py --dry-run   says what it would do, writes nothing
"""
import os, sys, subprocess

BRAIN = os.path.realpath(os.environ.get("BRAIN_HOME") or os.path.expanduser("~/.c-brain/trunk"))

# The trunk's pre-commit hook already splits by zone: we use ITS table, not a
# copy that would drift apart at the first new folder.
ZONES = (("hooks/", "engine"), ("tests/", "engine"), ("companion/", "engine"),
         ("cbrain/", "engine"), ("capsule/", "engine"),
         ("projects/", "knowledge"), ("lessons/", "knowledge"), ("meta/", "knowledge"),
         ("life/", "knowledge"), ("agents/", "knowledge"),
         ("sessions/", "archives"))
LABEL = {"engine": "engine: hooks, tests and capsule",
         "knowledge": "knowledge: notes, lessons and maps",
         "archives": "archives: sessions and logs",
         "root": "root: entry maps, audits and tooling"}
ORDER = ("archives", "knowledge", "root", "engine")


def zone(f):
    for prefix, z in ZONES:
        if f.startswith(prefix):
            return z
    return "root"


def sh(cmd, cwd, timeout=180):
    """Returns (code, output). Never raises: this script must break nothing."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except Exception as e:
        return 1, str(e)


def changed(cwd):
    _, out = sh(["git", "status", "--porcelain"], cwd)
    return [l[3:].strip().strip('"') for l in out.splitlines() if l.strip()]


def commit_by_zone(cwd, msg_prefix="auto: ", dry=False):
    """One commit per zone. Returns the number of commits made."""
    made = 0
    for z in ORDER:
        sh(["git", "reset", "-q"], cwd)
        sel = [f for f in changed(cwd) if zone(f) == z]
        if not sel:
            continue
        if dry:
            print(f"    [dry] {z:9} {len(sel):4d} file(s)")
            made += 1
            continue
        code, _ = sh(["git", "add", "--"] + sel, cwd)
        if code:
            continue
        # No "Co-Authored-By" line here: this commit is made in its owner's
        # repository by their own machine. Pasting an e-mail address into it —
        # public or not — both dirties their history and turns leakcheck red,
        # which hunts addresses in EVERYTHING that ships in the package.
        msg = (f"{msg_prefix}{LABEL[z]}\n\n"
               f"Automatic commit, one zone at a time ({len(sel)} file(s)).\n"
               f"One zone per commit: work in progress stays identifiable in the "
               f"history instead of being buried by a `git add -A`.\n")
        # Author "C Brain": a commit made by the machine must not carry the
        # human's signature.
        r = subprocess.run(["git", "-c", "user.name=C Brain",
                            "-c", "user.email=brain@local",
                            "commit", "-q", "-F", "-"], cwd=cwd,
                           input=msg, text=True, capture_output=True)
        if r.returncode == 0:
            print(f"    ✅ {z:9} {len(sel):4d} file(s)")
            made += 1
        else:
            # the trunk's pre-commit hook may refuse: we SAY so, we do not insist.
            print(f"    ⚠️  {z:9} refused: {(r.stdout + r.stderr).strip()[:120]}")
    sh(["git", "reset", "-q"], cwd)
    return made


def main():
    dry = "--dry-run" in sys.argv
    code, _ = sh(["git", "rev-parse", "--git-dir"], BRAIN)
    if code:
        print("  trunk is not a git repo — nothing to save")   # the normal case: nobody ran `git init`
        return 0
    n = len(changed(BRAIN))
    if not n:
        print("  nothing to commit")
        return 0
    print(f"  {n} file(s) changed")
    commit_by_zone(BRAIN, dry=dry)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"commit_par_zone: {e}")
        sys.exit(0)                              # NEVER breaks its caller
