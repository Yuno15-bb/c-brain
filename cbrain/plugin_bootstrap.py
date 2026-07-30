#!/usr/bin/env python3
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""
plugin_bootstrap.py — fait exister le tronc quand C Brain arrive en PLUGIN.

Installer le plugin, ce n'est pas lancer install.sh. Personne n'a créé
~/.c-brain, personne n'a lié le moteur dans le tronc, et personne n'a posé la
commande `brain` où que ce soit. Ceci tourne en premier à chaque SessionStart
et rend la disposition vraie.

POURQUOI IL TOURNE À CHAQUE FOIS, et pas une seule. ${CLAUDE_PLUGIN_ROOT} se
déplace à chaque mise à jour du plugin — l'ancien dossier est gardé une ou deux
semaines puis ramassé. Un lien écrit une fois pourrirait en symlink mort le
lendemain d'une mise à jour, et tous les hooks échoueraient sur un « fichier
introuvable » que personne ne lit. Donc chaque session repointe les liens vers
là où le plugin vit MAINTENANT. C'est une poignée d'appels stat(), et il
n'écrit rien quand tout concorde déjà.

CE QU'IL NE FERA PAS. Il ne touche jamais une fiche, ne remplace jamais un
vrai dossier par un lien (un dossier hooks/ réel signale une installation
autonome plus ancienne — ce sont les fichiers de quelqu'un, et les deux
dispositions ne doivent pas fusionner en silence), et sort toujours 0. Un outil
de mémoire qui casse la session qu'il est censé aider est pire que pas de
mémoire du tout.
"""
import json
import os
import shutil
import sys

HOME = os.path.expanduser("~")
CB = os.path.join(HOME, ".c-brain")
TRUNK = os.path.join(CB, "trunk")
LIES = ("hooks", "agents", "capsule", "planet", "companion", "tests")

# Le dossier propre au plugin. Claude Code le fournit ; quand il est absent,
# c'est qu'on tourne à la main depuis un clone, et l'emplacement de ce fichier
# est la réponse.
ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or \
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def relier(cible, chemin):
    """Lien symbolique idempotent. Renvoie True s'il a réellement écrit."""
    if os.path.islink(chemin):
        if os.readlink(chemin) == cible:
            return False
        os.unlink(chemin)
    elif os.path.exists(chemin):
        return False        # un vrai dossier : le contenu de quelqu'un, pas le nôtre
    os.symlink(cible, chemin)
    return True


def main():
    neuf = not os.path.isdir(TRUNK)
    if neuf:
        squelette = os.path.join(ROOT, "skeleton")
        os.makedirs(CB, exist_ok=True)
        if os.path.isdir(squelette):
            shutil.copytree(squelette, TRUNK)
        else:
            os.makedirs(TRUNK, exist_ok=True)

    for d in ("state", os.path.join("sessions", "archive")):
        os.makedirs(os.path.join(TRUNK, d), exist_ok=True)

    relier(ROOT, os.path.join(CB, "engine"))
    for d in LIES:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            relier(src, os.path.join(TRUNK, d))

    # La version qu'une installation en plugin peut réellement annoncer. Sans
    # ce fichier, `brain version` répond « (version inconnue) » à tous ceux qui
    # sont arrivés par la marketplace — et la version est la première chose
    # qu'on demande quand quelque chose ne va pas. install.sh l'écrit ; rien
    # d'autre ne le faisait.
    try:
        manifeste = os.path.join(ROOT, ".claude-plugin", "plugin.json")
        with open(manifeste, encoding="utf-8") as f:
            version = json.load(f).get("version")
        if version:
            with open(os.path.join(CB, "VERSION"), "w", encoding="utf-8") as f:
                f.write(f"{version} (plugin)\n")
    except Exception:
        pass                       # jamais de quoi casser une session

    if neuf:
        # Dit une seule fois, la session où le tronc apparaît — et dit là où un
        # nouvel utilisateur regarde vraiment, pas dans un README qu'il n'a pas
        # ouvert. Un tronc vide qui n'explique rien, c'est là qu'on abandonne.
        #
        # ⚠ Il ne PROMET PAS le raccourci `C Brain`. Ce dossier est créé par
        # install.sh, qu'une installation en plugin ne lance jamais — donc la
        # première phrase lue par un utilisateur de la marketplace pointait
        # vers quelque chose qui n'existait pas. On donne le chemin à la
        # place, parce que le chemin, lui, est vrai.
        print("🧠 C Brain : ton tronc est prêt dans ~/.c-brain/trunk — de simples "
              "fichiers markdown, les tiens.\n"
              "   Essaie : brain demo · brain recall cache · brain demo --remove")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                       # ne jamais casser une session
        print(f"amorçage c-brain sauté : {e}", file=sys.stderr)
    sys.exit(0)
