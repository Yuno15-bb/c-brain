#!/usr/bin/env python3
"""PreToolUse (Write|Edit|MultiEdit|NotebookEdit) — pose la pré-image du fichier.

Sans cette pré-image, un `Write` qui écrase un fichier existant apparaîtrait comme
« tout ajouté » : on perdrait l'AVANT, donc le seul truc qui rend le diff vérifiable.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    from companion_lib import (MAX_FILE_BYTES, ensure_dirs, read_hook_input,
                               snap_path, target_path)

    data = read_hook_input()
    sid = data.get("session_id")
    fpath = target_path(data.get("tool_input"))
    if not sid or not fpath:
        return

    ensure_dirs()
    dest = snap_path(sid, fpath)
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    if not os.path.exists(fpath):
        open(dest + ".new", "w").close()      # marqueur : fichier créé de zéro
        open(dest, "w").close()
        return
    try:
        if os.path.getsize(fpath) > MAX_FILE_BYTES:
            open(dest + ".big", "w").close()
            return
        shutil.copyfile(fpath, dest)
        for flag in (".new", ".big"):
            if os.path.exists(dest + flag):
                os.remove(dest + flag)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass          # un companion cassé ne doit JAMAIS gêner une session Claude
    sys.exit(0)
