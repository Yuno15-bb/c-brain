#!/usr/bin/env python3
"""
plugin_bootstrap.py — makes the trunk exist when C Brain arrives as a PLUGIN.

Installing the plugin is not running install.sh. Nobody created ~/.c-brain,
nobody linked the engine into the trunk, and nobody put the `brain` command
anywhere. This runs first on every SessionStart and makes the layout true.

WHY IT RUNS EVERY TIME, not once. ${CLAUDE_PLUGIN_ROOT} moves whenever the
plugin updates — the old directory is kept for a couple of weeks and then
collected. A link written once would rot into a dangling symlink the day after
an update, and every hook would fail with a file-not-found nobody can read. So
each session re-points the links at wherever the plugin lives NOW. It is a
handful of stat() calls and writes nothing when everything already agrees.

WHAT IT WILL NOT DO. It never touches a note, never replaces a real directory
with a link (a real hooks/ folder means an older standalone install — that is
someone's files, and the two layouts must not be silently merged), and always
exits 0. A memory tool that breaks the session it is trying to help is worse
than no memory at all.
"""
import os
import shutil
import sys

HOME = os.path.expanduser("~")
CB = os.path.join(HOME, ".c-brain")
TRUNK = os.path.join(CB, "trunk")
LINKED = ("hooks", "agents", "capsule", "planet", "companion", "tests")

# The plugin's own directory. Claude Code sets this; when it is absent we are
# being run by hand from a clone, and the file's own location is the answer.
ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def relink(target, path):
    """Idempotent symlink. Returns True when it actually wrote something."""
    if os.path.islink(path):
        if os.readlink(path) == target:
            return False
        os.unlink(path)
    elif os.path.exists(path):
        return False        # a real directory: someone's content, not ours
    os.symlink(target, path)
    return True


def main():
    fresh = not os.path.isdir(TRUNK)
    if fresh:
        skeleton = os.path.join(ROOT, "skeleton")
        os.makedirs(CB, exist_ok=True)
        if os.path.isdir(skeleton):
            shutil.copytree(skeleton, TRUNK)
        else:
            os.makedirs(TRUNK, exist_ok=True)

    for d in ("state", os.path.join("sessions", "archive")):
        os.makedirs(os.path.join(TRUNK, d), exist_ok=True)

    relink(ROOT, os.path.join(CB, "engine"))
    for d in LINKED:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            relink(src, os.path.join(TRUNK, d))

    if fresh:
        # Said once, on the session where the trunk appears — and said where a
        # first-time user is actually looking, not in a README they have not
        # opened. An empty trunk that explains nothing is where people give up.
        print("🧠 C Brain: your trunk is ready at ~/.c-brain/trunk (a `C Brain` "
              "shortcut in your home folder opens it).\n"
              "   Try: brain demo · brain recall cache · brain demo --remove")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                       # never break a session
        print(f"c-brain bootstrap skipped: {e}", file=sys.stderr)
    sys.exit(0)
