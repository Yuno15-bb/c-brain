#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# plugin_install.sh — le chemin que prend réellement un inconnu.
#
# POURQUOI IL EXISTE. La CI prouvait qu'`install.sh` marche, et `install.sh`
# c'est le chemin LONG — cloner le dépôt, lancer un script, récolter des jobs
# launchd et une fenêtre Electron. Qui arrive par la marketplace prend l'autre :
# Claude Code recopie le plugin dans un cache et lance `plugin_bootstrap.py` au
# SessionStart. Ce chemin-là n'était exécuté par rien.
#
# Il n'était pas cassé, mais il était FAUX de deux façons invisibles de
# l'extérieur, et les deux sur le premier écran que voit un nouveau venu :
#   · la ligne d'accueil promettait un raccourci `C Brain` dans le dossier
#     personnel. Ce dossier est créé par install.sh, qu'une installation en
#     plugin ne lance jamais.
#   · `brain version` répondait « (version inconnue) », parce que seul
#     install.sh écrivait le fichier VERSION — et la version est la première
#     chose qu'on demande quand quelque chose ne va pas.
#
# Aucun des deux n'aurait fait échouer un test. Les deux étaient lus, une fois,
# par chaque personne qui l'installait.
#
# Lancer : bash tests/plugin_install.sh
set -uo pipefail

RACINE="$(cd "$(dirname "$0")/.." && pwd -P)"
ECHECS=0

verif() {  # verif <code-de-sortie> <libellé> [détail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; ECHECS=$((ECHECS + 1)); fi
}

H="$(mktemp -d)"
trap 'rm -rf "$H"' EXIT

# Claude Code recopie le plugin dans un dossier de cache au lieu de le lancer
# depuis le dépôt : le montage fait pareil. Le lancer depuis le dépôt masquerait
# tout chemin qui ne se résout que parce qu'il se trouve à côté d'un .git.
P="$H/plugin-cache/c-brain"
mkdir -p "$(dirname "$P")"
rsync -a --exclude .git --exclude node_modules "$RACINE/" "$P/"

export HOME="$H"
export CLAUDE_PLUGIN_ROOT="$P"

echo "▸ première session : le tronc doit apparaître"
SORTIE="$(python3 "$P/cbrain/plugin_bootstrap.py" 2>&1)"
[ -d "$H/.c-brain/trunk" ];              verif $? "le tronc existe"
[ -f "$H/.c-brain/trunk/MEMORY.md" ];    verif $? "l'index est là"
[ -L "$H/.c-brain/engine" ];             verif $? "le moteur est lié"
[ -L "$H/.c-brain/trunk/hooks" ];        verif $? "les hooks sont liés dans le tronc"
[ -L "$H/.c-brain/trunk/agents" ];       verif $? "les agents sont liés dans le tronc"

echo "▸ ce qu'il dit doit être vrai"
printf '%s' "$SORTIE" | grep -q "~/.c-brain/trunk"
verif $? "la ligne d'accueil nomme l'endroit où le tronc est vraiment"
# La promesse qui n'était pas tenue. Si le raccourci est de nouveau mentionné
# ici, ce doit être parce que quelque chose sur ce chemin le crée.
if printf '%s' "$SORTIE" | grep -qi "raccourci"; then
  [ -e "$H/C Brain" ]
  verif $? "un raccourci promis existe" "la première ligne lue par un nouveau venu pointe vers rien"
else
  echo "  ✅ rien n'est promis que ce chemin ne crée pas"
fi

echo "▸ les commandes qu'un utilisateur de plugin peut taper"
V="$(HOME="$H" "$P/bin/brain" version 2>&1)"
printf '%s' "$V" | grep -qv "inconnue"
verif $? "brain version répond quelque chose" "reçu : $V"
printf '%s' "$V" | grep -q "$(python3 -c "import json;print(json.load(open('$P/.claude-plugin/plugin.json'))['version'])")"
verif $? "et ça correspond au manifeste" "reçu : $V"

HOME="$H" "$P/bin/brain" demo >/dev/null 2>&1
HOME="$H" "$P/bin/brain" recall cache déploiement 2>/dev/null | grep -q "cache"
verif $? "le rappel renvoie quelque chose sur le tronc de démo"

echo "▸ chaque session après la première est un non-événement"
SORTIE2="$(python3 "$P/cbrain/plugin_bootstrap.py" 2>&1)"
[ -z "$SORTIE2" ];                       verif $? "il ne dit rien la deuxième fois" "affiché : $SORTIE2"
[ -d "$H/.c-brain/trunk/lessons" ];      verif $? "il n'a pas effacé le tronc"

echo "▸ un vrai dossier hooks/ appartient à une install plus ancienne, on n'y touche pas"
rm "$H/.c-brain/trunk/hooks"
mkdir -p "$H/.c-brain/trunk/hooks"
touch "$H/.c-brain/trunk/hooks/son-propre-fichier.py"
python3 "$P/cbrain/plugin_bootstrap.py" >/dev/null 2>&1
[ -f "$H/.c-brain/trunk/hooks/son-propre-fichier.py" ]
verif $? "un vrai dossier n'est jamais remplacé par un lien"

echo "▸ et il n'emporte jamais la session avec lui"
CLAUDE_PLUGIN_ROOT="/chemin/inexistant" python3 "$P/cbrain/plugin_bootstrap.py" >/dev/null 2>&1
verif $? "il sort 0 même pointé vers rien"

echo
if [ "$ECHECS" -eq 0 ]; then
  echo "✅ le chemin plugin marche, et ne dit que des choses vraies"
  exit 0
fi
echo "❌ $ECHECS échec(s) sur le chemin que prend la plupart des nouveaux venus"
exit 1
