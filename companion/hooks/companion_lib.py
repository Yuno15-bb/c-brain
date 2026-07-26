#!/usr/bin/env python3
"""Socle commun des hooks du Companion (suivi live des modifs, rendu dans la barre).

Contraintes non négociables :
  - stdlib seule (Python 3.9 sur la machine cible) ;
  - JAMAIS bloquant : tout est enveloppé côté appelant, un échec est silencieux ;
  - JAMAIS de secret affiché : les fichiers sensibles sont signalés, pas montrés.
"""

import hashlib
import json
import os
import re
import sys
import time

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, ".claude", "companion")
SESSIONS = os.path.join(BASE, "sessions")   # <sid>.jsonl : le flux d'événements
SNAP = os.path.join(BASE, "snap")           # pré-images posées par PreToolUse
AGG = os.path.join(BASE, "agg")             # totaux par session, pour la barre

MAX_DIFF_LINES = 500        # au-delà, on tronque : inutile de stocker un pavé
MAX_FILE_BYTES = 2_000_000  # au-delà, on ne diffe pas (binaire, bundle, asset)

# --- Secrets : liste noire de chemins, puis de lignes ------------------------
SECRET_PATH = re.compile(
    r"(^|/)(\.env(\.|$)|secrets?/|\.pem$|\.key$|id_rsa|credentials|"
    r"\.npmrc$|\.netrc$|service.?account.*\.json$)", re.I)
SECRET_LINE = re.compile(
    r"(?i)(secret|token|passwd|password|api[_-]?key|access[_-]?key|bearer|"
    r"private[_-]?key|client[_-]?secret|sk-[A-Za-z0-9]|ghp_|xox[baprs]-)")


def now():
    return time.time()


def ensure_dirs():
    for d in (SESSIONS, SNAP, AGG):
        os.makedirs(d, exist_ok=True)


def read_hook_input():
    """Lit le JSON du hook sur stdin. Renvoie {} si illisible."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def target_path(tool_input):
    """Chemin du fichier visé, quel que soit l'outil d'édition."""
    if not isinstance(tool_input, dict):
        return None
    for key in ("file_path", "notebook_path", "path"):
        p = tool_input.get(key)
        if isinstance(p, str) and p.strip():
            return os.path.abspath(os.path.expanduser(p))
    return None


def snap_path(sid, fpath):
    h = hashlib.sha1(fpath.encode("utf-8")).hexdigest()[:16]
    return os.path.join(SNAP, sid, h)


def is_secret_path(fpath):
    return bool(SECRET_PATH.search(fpath))


def mask_line(line):
    """Masque la VALEUR d'une ligne sensible, garde la clé (utile au diagnostic)."""
    if not SECRET_LINE.search(line):
        return line
    m = re.match(r"^([+\-\s]?\s*[\w\.\-\[\]\"']{0,60}?\s*[:=]\s*)(.+)$", line)
    if m:
        return m.group(1) + "••• masqué"
    return (line[:1] if line[:1] in "+- " else "") + "••• ligne masquée"


def append_event(sid, event):
    """Ajoute un événement au flux de la session. Append-only : jamais de réécriture
    en bloc du fichier (cf. leçon file-reecrite-en-bloc-apres-await-perd-les-ecritures)."""
    ensure_dirs()
    event.setdefault("ts", now())
    path = os.path.join(SESSIONS, sid + ".jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path


def project_name(cwd):
    if not cwd:
        return "?"
    cwd = cwd.rstrip("/")
    base = os.path.basename(cwd)
    return base or cwd


# --- Plus aucune fenêtre ----------------------------------------------------
# Le suivi est rendu par ~/.claude/statusline.py (2e ligne, via status_part.py) :
# INTÉGRÉ à la session, tout en bas, en permanence. L'ancrage d'une fenêtre Electron
# à la fenêtre Terminal a été retiré — une fenêtre flottante finit toujours par
# recouvrir ce qu'on veut lire, et deux sessions donnaient deux panneaux illisibles.
