#!/usr/bin/env python3
"""
english_only.py — guards the ONE thing nothing else watches: the translation.

`main` is English, `fr` is the French source, and the step between them is a
human reading a diff. That step has already failed four times in the open:
`brain status` answering "(pas de statut)", `brain review` answering "aucune
paire en attente", `brain selftest` printing "hors-tronc", and the planet
labelling a panel "⚠ avis du challenger" — each of them on a screen a user
looks at, each shipped in a release.

WHAT IT CHECKS, AND WHAT IT DELIBERATELY DOES NOT. Only text a USER can see:
string literals and HTML content. Not comments — the README says plainly that
hook comments are still being translated, and a check that fails on a known,
declared state is a check people learn to ignore.

SOME FRENCH IS THE FEATURE. Several patterns match the USER's notes, not this
codebase: resume-point markers, the challenger's verdicts, the tokenizer's
letter class. Dropping their French would quietly stop serving anyone who
writes in French. Those lines opt out where they live — an `i18n-ok` on the
line, or the word BILINGUAL in the comment just above — so the reason travels
with the code instead of rotting in a list at the top of this file.

The signal is the French accent. It is nearly absent from English (café, résumé
— both listed as allowed below), and it is present in almost every French
sentence long enough to be a UI string. A word list would be endless and would
false-positive on "la", "on", "site"; accents are cheap and precise.

Run: python3 tests/english_only.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ACCENTS = "àâäçéèêëîïôöùûüÿœÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒ"

# Files whose French is the subject, not a leak.
SKIP_FILES = {
    "docs/translation.md",   # documents the fr branch, quotes it
    "sync.sh",               # reads the author's living, French Brain
    "rules.json",            # the French→English rules themselves
    "generalize.py",         # ships the French patterns it rewrites
    "leakcheck.py",          # French markers are what it hunts for
    "tests/english_only.py",
}
SKIP_DIRS = {".git", "node_modules", "docs/media", "planet/media", "skeleton", "demo"}

# English words that legitimately carry an accent.
ALLOWED = re.compile(r"\b(caf[ée]|r[ée]sum[ée]|na[ïi]ve|expos[ée]|clich[ée])\b", re.I)

# A user-visible string: quoted literal, or text between HTML tags.
PATTERNS = [
    re.compile(r"'([^'\\\n]{4,})'"),
    re.compile(r'"([^"\\\n]{4,})"'),
    re.compile(r">([^<>{}\n]{4,})<"),
]

EXTS = {".py", ".sh", ".js", ".html", ".md", ""}


def visible_strings(text):
    for pat in PATTERNS:
        for m in pat.finditer(text):
            yield m.group(1)


def strip_comments(text, suffix):
    """Comments are out of scope — see the module docstring."""
    if suffix in (".py", ".sh", ""):
        return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    if suffix == ".js":
        return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//"))
    return text


OPT_OUT = re.compile(r"i18n-ok|BILINGUAL")


def opted_out(lines, line_no):
    """True when the line, or the comment block right above it, declares that its
    French is intentional. Six lines of reach: enough for a short paragraph of
    reasoning, short enough that an unrelated comment cannot cover a string."""
    lo = max(0, line_no - 7)
    return any(OPT_OUT.search(l) for l in lines[lo:line_no])


def main():
    bad = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if any(rel == d or rel.startswith(d + "/") for d in SKIP_DIRS):
            continue
        if rel in SKIP_FILES:
            continue
        if p.suffix not in EXTS:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = text.splitlines()
        body = strip_comments(text, p.suffix)
        for s in visible_strings(body):
            hit = [c for c in s if c in ACCENTS]
            if not hit or ALLOWED.search(s):
                continue
            line = text[: text.find(s)].count("\n") + 1
            if opted_out(lines, line):
                continue
            bad.append((rel, line, s.strip()[:90]))

    if bad:
        print(f"❌ {len(bad)} user-visible string(s) still French on this branch:\n")
        for rel, line, s in bad:
            print(f"  {rel}:{line}\n      {s}")
        print("\nTranslate them, or add the file to SKIP_FILES if its French is the point.")
        return 1

    print("✅ no French left in any user-visible string")
    return 0


if __name__ == "__main__":
    sys.exit(main())
