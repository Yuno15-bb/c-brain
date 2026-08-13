#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# uninstall.sh — défait ce que install.sh a fait, et RIEN d'autre.
#
# Règle absolue : **ton tronc n'est jamais supprimé**. Tes fiches sont ton
# travail, pas une dépendance de C Brain. Le tronc perd ses liens vers le
# moteur, il garde tout son contenu.
#
# Usage : ./uninstall.sh [--yes] [--purge-engine]
set -euo pipefail

TRUNK="$HOME/.c-brain/trunk"
CB="$HOME/.c-brain"
MANIFEST="$CB/manifest.txt"

ASSUME_YES=0; PURGE_ENGINE=0
for a in "$@"; do
  case "$a" in
    --yes) ASSUME_YES=1 ;;
    --purge-engine) PURGE_ENGINE=1 ;;
    *) echo "Option inconnue : $a"; exit 1 ;;
  esac
done

say() { echo "  $*"; }

echo "🧠 C Brain — désinstallation"
echo
echo "  Sera retiré :"
echo "    · les hooks C Brain de ~/.claude/settings.json (le reste du fichier intact)"
echo "    · les liens du moteur dans $TRUNK (hooks, agents, capsule, planet, companion, tests)"
echo "    · ~/.local/bin/brain, le lanceur du Bureau, les tâches launchd"
echo
echo "  Sera CONSERVÉ :"
echo "    · $TRUNK et TOUTES tes fiches"
echo "    · les sauvegardes dans $CB/backups/"
echo

if [ "$ASSUME_YES" = "0" ]; then
  printf "  Continuer ? [o/N] "
  read -r ans
  case "$ans" in o|O|y|Y) ;; *) echo "  Annulé."; exit 0 ;; esac
fi

# ─── 1. Hooks ─────────────────────────────────────────────────────────────
echo
echo "▸ Hooks"
if [ -f "$HOME/.claude/settings.json" ] && [ -f "$CB/engine/merge_settings.py" ]; then
  python3 "$CB/engine/merge_settings.py" remove
else
  say "(settings.json ou merge_settings.py absent — rien à faire)"
fi

# ─── 2. Tâches planifiées ─────────────────────────────────────────────────
echo
echo "▸ Tâches planifiées"
for t in resume machiniste; do
  p="$HOME/Library/LaunchAgents/com.claudebrain.$t.plist"
  if [ -f "$p" ]; then
    launchctl unload "$p" 2>/dev/null || true
    rm -f "$p"
    say "- com.claudebrain.$t"
  fi
done

# ─── 3. Liens ─────────────────────────────────────────────────────────────
# On ne supprime QUE des liens symboliques. Si c'est devenu un vrai dossier,
# c'est du contenu — on n'y touche pas.
echo
echo "▸ Liens du moteur"
for d in hooks agents capsule planet companion tests; do
  p="$TRUNK/$d"
  if [ -L "$p" ]; then rm -f "$p"; say "- $p"
  elif [ -e "$p" ]; then say "! $p n'est pas un lien — laissé en place (c'est du contenu)"; fi
done
for p in "$HOME/.claude/agents" "$HOME/.local/bin/brain"; do
  if [ -L "$p" ]; then rm -f "$p"; say "- $p"; fi
done

# ─── 4. Divers ────────────────────────────────────────────────────────────
echo
echo "▸ Divers"
[ -f "$HOME/Desktop/Planete-C-Brain.command" ] && { rm -f "$HOME/Desktop/Planete-C-Brain.command"; say "- lanceur du Bureau (ancien .command)"; }
# Le lanceur est devenu un bundle d'application le 2026-08-14 — un DOSSIER, donc
# `rm -f` passe à côté sans rien dire. Un désinstalleur qui laisse un lanceur sur
# le Bureau laisse croire que l'outil est encore installé, et son icône pointe
# sur un tronc qu'on vient peut-être de délier.
[ -d "$HOME/Desktop/Planète C Brain.app" ] && { rm -rf "$HOME/Desktop/Planète C Brain.app"; say "- lanceur du Bureau (Planète C Brain.app)"; }
# Le raccourci vers le tronc — retiré SEULEMENT s'il pointe encore chez nous.
# Réorienté par l'utilisateur, il est devenu le sien : on n'y touche pas.
SHORTCUT="$HOME/C Brain"
if [ -L "$SHORTCUT" ] && [ "$(readlink "$SHORTCUT")" = "$TRUNK" ]; then
  rm -f "$SHORTCUT"; say "- $SHORTCUT"
elif [ -e "$SHORTCUT" ]; then
  say "! $SHORTCUT n'est pas notre raccourci — laissé en place"
fi
# …et le tag qu'on a posé sur le dossier. Cosmétique, mais on l'a ajouté, on le reprend.
xattr -d com.apple.metadata:_kMDItemUserTags "$TRUNK" 2>/dev/null && say "- tag Finder sur le tronc" || true
# Règle déterministe : si le fichier est IDENTIQUE à celui du moteur, il est de
# nous → on le retire. S'il diffère, c'est celui de l'utilisateur (préexistant
# ou retouché depuis) → on n'y touche pas.
SL="$HOME/.claude/statusline.py"
if [ -f "$SL" ]; then
  if [ -f "$CB/engine/statusline.py" ] && cmp -s "$SL" "$CB/engine/statusline.py"; then
    rm -f "$SL"; say "- ~/.claude/statusline.py (c'était la nôtre, à l'octet près)"
  else
    say "! ~/.claude/statusline.py diffère de la nôtre — laissée en place (c'est la tienne)"
  fi
fi

# ─── 5. Moteur ────────────────────────────────────────────────────────────
echo
echo "▸ Moteur"
if [ "$PURGE_ENGINE" = "1" ]; then
  rm -f "$CB/engine" "$MANIFEST" "$CB/VERSION"
  say "- références au moteur retirées (le dépôt cloné, lui, reste sur le disque)"
else
  say "= $CB conservé (sauvegardes + version). --purge-engine pour l'effacer."
fi

echo
echo "✅ Désinstallé. $TRUNK et tes fiches sont intacts."
echo "   Sauvegardes : $CB/backups/"
