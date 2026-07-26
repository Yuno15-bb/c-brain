#!/usr/bin/env python3
"""C Brain — branchement des hooks dans ~/.claude/settings.json.

NON DESTRUCTIF, et c'est tout l'enjeu : ce fichier appartient à l'utilisateur.
Il peut déjà contenir son modèle, son thème, ses permissions, ses propres hooks.
On AJOUTE les nôtres, on ne réécrit jamais le reste.

Idempotent : l'appartenance se juge sur la commande exacte. Relancer n'ajoute
pas de doublon. Désinstaller ne retire QUE nos entrées.

Usage :
  python3 merge_settings.py install [--settings <chemin>]
  python3 merge_settings.py remove  [--settings <chemin>]
"""

import json
import os
import shutil
import sys
import time

HOME = os.path.expanduser("~")
DEFAULT_SETTINGS = os.path.join(HOME, ".claude", "settings.json")
BRAIN = os.path.join(HOME, "claude-brain")
CB = os.path.join(HOME, ".c-brain")

# (événement, matcher ou None, chemin du script, timeout, message d'état)
HOOKS = [
    ("SessionStart", None, "hooks/brain_anticipate.py --hook", 10, None),
    # Signale une nouvelle version, n'installe rien. Throttlé à 1×/24 h côté script.
    ("SessionStart", None, "@cbrain/check_update.py", 20, None),
    ("UserPromptSubmit", None, "hooks/inject_recall.py", 10, None),
    ("PostToolUse", "Write|Edit", "hooks/on_fiche_write.py", 15, None),
    ("PostToolUse", "Read", "hooks/track_read.py", 10, None),
    ("PostToolUse", "Write|Edit|MultiEdit|NotebookEdit",
     "companion/hooks/post_diff.py", 8, None),
    ("PreToolUse", "Write|Edit|MultiEdit|NotebookEdit",
     "companion/hooks/pre_snapshot.py", 5, None),
    ("SessionEnd", None, "hooks/archive_session.py", 30,
     "Archivage de la session dans le tronc..."),
    ("SessionEnd", None, "hooks/auto_maintain.py", 15,
     "Maintenance autonome du tronc (distille + range)..."),
    ("SessionEnd", None, "companion/hooks/session_close.py", 5, None),
]

# Ce qui identifie NOS commandes au moment de désinstaller. Deux racines :
# le tronc (~/claude-brain/...) et le moteur (~/.c-brain/engine/...).
MARKERS = ("claude-brain", ".c-brain")

# La statusline se COPIE dans ~/.claude, mais elle ne s'affiche que si elle est
# DÉCLARÉE ici. Copier le fichier sans écrire cette clé donnait une statusline
# installée et invisible — l'échec silencieux typique.
STATUSLINE_CMD = f"python3 {os.path.join(HOME, '.claude', 'statusline.py')}"


def command_for(script):
    """Deux origines possibles. Un script préfixé `@` vit dans le MOTEUR
    (spécifique à C Brain, absent du Brain d'origine) ; les autres vivent dans
    le tronc, où les symlinks les rendent visibles."""
    if script.startswith("@"):
        return f"python3 {os.path.join(CB, 'engine', script[1:])}"
    return f"python3 {os.path.join(BRAIN, script)}"


def load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"❌ {path} est un JSON invalide ({e}).\n"
                 f"   Répare-le à la main : on ne réécrit pas un fichier qu'on ne comprend pas.")


def backup(path, tag):
    if not os.path.exists(path):
        return None
    dest = f"{path}.bak-c-brain-{tag}"
    shutil.copy2(path, dest)
    return dest


def entries_of(settings, event):
    return settings.setdefault("hooks", {}).setdefault(event, [])


def install(settings):
    added = 0
    for event, matcher, script, timeout, status in HOOKS:
        cmd = command_for(script)
        groups = entries_of(settings, event)

        # Déjà branché ? On compare la commande exacte, pas la présence du fichier.
        if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
            continue

        hook = {"type": "command", "command": cmd, "timeout": timeout}
        if status:
            hook["statusMessage"] = status

        # On se greffe sur un groupe au matcher identique s'il existe (c'est la
        # forme attendue par Claude Code), sinon on en crée un.
        target = next((g for g in groups if g.get("matcher") == matcher), None)
        if target is None:
            target = {"hooks": []}
            if matcher:
                target["matcher"] = matcher
            groups.append(target)
        target["hooks"].append(hook)
        added += 1

    # Statusline : on ne l'impose QUE si l'utilisateur n'en a pas déjà une.
    # Écraser sa ligne d'état serait s'inviter sur son écran.
    if "statusLine" not in settings:
        settings["statusLine"] = {"type": "command", "command": STATUSLINE_CMD}
        added += 1
    return added


def remove(settings):
    dropped = 0
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        groups = hooks[event]
        for g in groups:
            before = len(g.get("hooks", []))
            g["hooks"] = [h for h in g.get("hooks", [])
                          if not any(m in h.get("command", "") for m in MARKERS)]
            dropped += before - len(g["hooks"])
        hooks[event] = [g for g in groups if g.get("hooks")]
        if not hooks[event]:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)

    # On ne retire la statusline que si c'est BIEN la nôtre. Si l'utilisateur
    # l'a remplacée par la sienne entre-temps, elle reste.
    if settings.get("statusLine", {}).get("command") == STATUSLINE_CMD:
        settings.pop("statusLine")
        dropped += 1
    return dropped


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("install", "remove"):
        sys.exit(__doc__)
    action = sys.argv[1]
    path = DEFAULT_SETTINGS
    if "--settings" in sys.argv:
        path = sys.argv[sys.argv.index("--settings") + 1]

    settings = load(path)
    tag = time.strftime("%Y%m%d-%H%M%S")
    n = install(settings) if action == "install" else remove(settings)

    if n == 0:
        print(f"   settings.json — rien à faire ({'déjà branché' if action == 'install' else 'rien de nôtre'})")
        return 0

    b = backup(path, tag)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")

    verb = "branché(s)" if action == "install" else "retiré(s)"
    print(f"   settings.json — {n} hook(s) {verb}" + (f" · sauvegarde : {os.path.basename(b)}" if b else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
