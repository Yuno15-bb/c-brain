#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert. Source-available, see LICENSE.
#   Running it is allowed. Redistributing or rebuilding from it is not.
"""C Brain — leak check. The guard entitled to block a commit.

Adapted from an anonymization pipeline that already runs green on a public
portfolio build.

It does NOT re-read the source: it scans what will actually ship — the repo
itself, and its git history with --history. One surviving marker = red.

Usage:
  python3 leakcheck.py              scans the working tree
  python3 leakcheck.py --history    ALSO scans the whole git history

Exit 0 = clean · Exit 1 = leak detected.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# What must NEVER ship. Two families: real identities of third parties,
# and secrets. Both block the same way.
MARKERS = [
    ("client name",           r"DG\s*CHARPENTE|DG\s*Charpente"),
    ("client acronym",            r"\bDGC\b|\bdgc-"),
    ("client product",          r"BIG\s*GABY|\bGaby\b|\bgaby\b"),
    ("person — owner", r"\bDylan\b|\bDylanp\b"),
    ("person — manager", r"\bClarisse\b"),
    ("person — field tech",   r"\bLaurent\b"),
    ("person — director",    r"\bGabriel\b"),
    ("client surname",   r"\bRoume\b"),
    ("client city",         r"\bToulouse\b|\btoulousain"),
    ("client town",       r"\bCastanet-Tolosan\b|\bColomiers\b|\bBlagnac\b"
                                r"|\bTournefeuille\b|\bMURET\b"),
    ("local postcode",       r"\b31\d{3}\b"),
    ("personal programme",         r"Mission Locale|\bCEJ\b"),
    ("identified third party",         r"\b(GAILLOUSTE|TREMBLET|GAUBE|DELEST|MARRE|CHOUIALI"
                                r"|NAJMEDDINE|WILLHEM|AGESTIS|ALTRAD|FONCIA|SERCOB"
                                r"|PERSONAZ|RENOVAZ|CHAMAYOU|Barhoumi|Faouz|Merwan"
                                r"|Alexis|Joris)\b"),
    ("email address",            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("phone number",               r"(?<![\d.])0[1-9](?:[ .-]?\d{2}){4}(?![\d.])"),
    ("street address",         r"\b\d{1,3}\s+(?:rue|avenue|impasse|chemin|boulevard|route)\s+\w+"),
    ("personal path",        r"/Users/[A-Za-z0-9_.-]+/"),
    ("Anthropic key",           r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    ("GitHub token",            r"gh[pousr]_[A-Za-z0-9]{16,}"),
    ("JWT token",               r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    ("secret assigned in clear", r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}"),
]

# Two files necessarily CONTAIN the markers — that is their job:
# the checker (the list) and the generalization rules (the patterns to handle).
# Scanning them would be chasing our own tail.
SKIP_NAMES = {"leakcheck.py", "rules.json"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}

# NAMED exemptions, marker by marker. Never a whole folder:
# a broad exemption eventually covers a real leak.
#
# `docs/` = prose written and reviewed by hand. The owner keeps their name there,
# it is THEIR design doc. `LICENSE` names the copyright holder — that is what a
# licence IS; stripping it would make the file meaningless.
# Every other marker — clients, third parties, secrets, paths — still applies
# in both: only the owner's name is exempt.
EXEMPT = {"person — owner": ("docs/", "LICENSE")}

# Strings that look like an email without being one. A CLOSED list of exact
# literals — never a loosening of the pattern, which would reopen the door.
FALSE_POSITIVES = {
    "email address": ("git@github.com",),   # SSH syntax, not a person
}


def exempted(label: str, source: str) -> bool:
    # "history:docs/…" must be exempt just like "docs/…": same file, seen at
    # two different moments.
    src = source[len("history:"):] if source.startswith("history:") else source
    return any(src.startswith(p) for p in EXEMPT.get(label, ()))


def strip_diff_metadata(diff_text: str) -> str:
    """Drop git's own plumbing lines from a diff before scanning.

    They are structure, not content — and they produce real false positives:
    a blob-hash header like `index e855c2a..8ef0920 100644` matches the French
    phone-number pattern and blocked a publish. Filtering the metadata is
    correct; loosening the phone pattern would not be.
    """
    keep = []
    for line in diff_text.split("\n"):
        if line.startswith(("diff --git ", "index ", "--- ", "+++ ", "@@ ",
                            "new file mode ", "deleted file mode ",
                            "similarity index ", "rename from ", "rename to ",
                            "old mode ", "new mode ", "Binary files ")):
            continue
        keep.append(line)
    return "\n".join(keep)


def is_text(path: Path) -> bool:
    try:
        return b"\0" not in path.read_bytes()[:2048]
    except OSError:
        return False


def iter_files():
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file() or f.name in SKIP_NAMES:
            continue
        if SKIP_DIRS & set(f.relative_to(ROOT).parts):
            continue
        if is_text(f):
            yield f


def context(text, start, end, width=45):
    left = text[max(0, start - width):start].replace("\n", " ")
    right = text[end:end + width].replace("\n", " ")
    return f"…{left}⟦{text[start:end]}⟧{right}…"


def _on_a_copyright_line(text: str, pos: int) -> bool:
    """Is this match sitting on a copyright / licence notice line?

    The owner's name inside a copyright header is DELIBERATE — it is what makes
    a copied file carry its origin. What the marker is really hunting is the
    accidental mention ("the author's machine", "as requested by …"). Exempting
    the notice line keeps the hunt sharp instead of blunting the pattern.
    """
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    line = text[start:end if end != -1 else len(text)]
    return "Copyright (c)" in line or "All rights reserved" in line


def scan(label_source, text, compiled, leaks):
    for label, rx in compiled:
        if exempted(label, label_source):
            continue
        for m in rx.finditer(text):
            if m.group(0) in FALSE_POSITIVES.get(label, ()):
                continue
            if label == "person — owner" and _on_a_copyright_line(text, m.start()):
                continue
            leaks.append((label_source, label, context(text, m.start(), m.end())))


def main():
    with_history = "--history" in sys.argv
    compiled = [(label, re.compile(pattern)) for label, pattern in MARKERS]
    leaks = []

    files = list(iter_files())
    for path in files:
        scan(path.relative_to(ROOT).as_posix(),
             path.read_text(encoding="utf-8", errors="replace"), compiled, leaks)

    scanned = f"{len(files)} file(s)"

    if with_history:
        try:
            paths = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                                   capture_output=True, text=True, timeout=30).stdout.split()
        except (OSError, subprocess.SubprocessError):
            paths = []
            print("⚠️  Git history unreadable — scan limited to the working tree.")

        # PATH BY PATH, not one big blob. Two reasons:
        #  · exemptions (docs/, checker, rules) only apply if we know which
        #    file each line came from;
        #  · `--format=` strips commit headers, otherwise the "Author: First
        #    Last <mail>" line surfaces as a leak on every commit.
        n_hist = 0
        for rel in paths:
            if os.path.basename(rel) in SKIP_NAMES:
                continue
            try:
                d = subprocess.run(["git", "-C", str(ROOT), "log", "-p", "--all",
                                    "--format=", "--", rel],
                                   capture_output=True, text=True, timeout=60).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            if d:
                n_hist += 1
                scan(f"history:{rel}", strip_diff_metadata(d), compiled, leaks)
        if n_hist:
            scanned += f" + history of {n_hist} file(s)"

    print(f"🔍 Leak check — {scanned}, {len(MARKERS)} markers")

    if not leaks:
        print("\n✅ CLEAN — no sensitive marker. Commit allowed.")
        return 0

    by_label = {}
    for _, label, _ in leaks:
        by_label[label] = by_label.get(label, 0) + 1

    print(f"\n⛔ RED — {len(leaks)} leak(s). Nothing ships.\n")
    for label, count in sorted(by_label.items(), key=lambda kv: -kv[1]):
        print(f"   {count:>5}×  {label}")

    print("\n   Cases:")
    for path, label, ctx in leaks[:20]:
        print(f"     · [{label}] {path}\n       {ctx}")
    if len(leaks) > 20:
        print(f"     … and {len(leaks) - 20} more.")

    print("\n   → Fix at the source (generalize the file), not by loosening the markers.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
