#!/usr/bin/env python3
"""
plugin_manifest.py — the plugin half of the package cannot be checked by eye.

A hook whose path no longer exists does not fail loudly: Claude Code reports a
load error the user scrolls past, and the memory simply stops recording. That
is the worst failure mode this project has — silent, and invisible until you go
looking for a note that was never written.

So: every ${CLAUDE_PLUGIN_ROOT} path in hooks.json must point at a file that is
actually in the repo, both manifests must parse, and the plugin version must
match the latest tag — because Claude Code hands out updates on that string
alone, and a stale one means users sit on an old copy while every release note
says otherwise.

Run: python3 tests/plugin_manifest.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
MARKET = ROOT / ".claude-plugin" / "marketplace.json"
HOOKS = ROOT / "hooks" / "hooks.json"

PATH_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"'\s]+)")


def fail(msg):
    print(f"❌ {msg}")
    return 1


def latest_tag():
    """The newest vX.Y.Z on this branch, French tags excluded."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "tag", "--sort=-creatordate"],
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for t in out.split():
        if re.fullmatch(r"v\d+\.\d+\.\d+", t):
            return t
    return None


def main():
    errors = 0

    for f in (PLUGIN, MARKET, HOOKS):
        if not f.exists():
            errors += fail(f"missing: {f.relative_to(ROOT)}")
            continue
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors += fail(f"{f.relative_to(ROOT)} is not valid JSON: {e}")
    if errors:
        return 1

    plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
    market = json.loads(MARKET.read_text(encoding="utf-8"))

    # Every script a hook points at must exist.
    for rel in sorted(set(PATH_RE.findall(HOOKS.read_text(encoding="utf-8")))):
        rel = rel.rstrip('\\"')
        if not (ROOT / rel).exists():
            errors += fail(f"hooks.json points at a file that does not exist: {rel}")

    names = [p.get("name") for p in market.get("plugins", [])]
    if plugin.get("name") not in names:
        errors += fail(f"marketplace.json does not list the plugin {plugin.get('name')!r} "
                       f"(it lists {names})")

    # The version gate. publish.sh writes this field from the tag; if the two
    # ever part company, users stop receiving updates without a single error.
    # BEHIND is the failure; AHEAD is normal — publish.sh bumps the manifest and
    # commits it just before creating the tag, so between those two instants the
    # file is legitimately one version in front.
    tag = latest_tag()
    if tag:
        def parts(v):
            return tuple(int(x) for x in re.findall(r"\d+", v)[:3])
        if parts(plugin.get("version", "0")) < parts(tag):
            errors += fail(f"plugin.json version is {plugin.get('version')!r}, BEHIND the latest "
                           f"tag {tag}. Users would never be offered the update.")

    if errors:
        return 1
    print(f"✅ plugin manifests consistent — c-brain {plugin.get('version')}, "
          f"{len(set(PATH_RE.findall(HOOKS.read_text(encoding='utf-8'))))} hook script(s) present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
