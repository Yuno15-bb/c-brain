#!/usr/bin/env bash
# 001-rename-user-dir.sh — ~/claude-brain devient ~/.c-brain/trunk.
#
# POURQUOI. Le dossier utilisateur d'un produit public s'appelait « claude-brain » :
# une marque Anthropic dans un nom que C Brain crée chez les gens, et un quatrième
# nom pour une seule chose (C Brain, c-brain, ~/claude-brain, ~/.c-brain/engine).
# Après : UNE racine, ~/.c-brain, avec le moteur et le tronc côte à côte.
#
#   avant                        après
#   ~/.c-brain/engine  (code)    ~/.c-brain/engine  (code, inchangé)
#   ~/claude-brain     (fiches)  ~/.c-brain/trunk   (fiches, déplacées ici)
#                                ~/claude-brain     → lien vers trunk (compatibilité)
#
# CE QU'ELLE NE FAIT PAS. Elle ne touche à aucune fiche, ne renomme rien DANS le
# tronc, ne relance aucun service. Le recâblage (liens du moteur, settings.json,
# plists launchd, lanceur du Bureau) est refait juste après par install.sh, que
# update.sh appelle systématiquement. Ici, on déplace — rien d'autre.
set -euo pipefail

OLD="$HOME/claude-brain"
NEW="$HOME/.c-brain/trunk"

say() { echo "  $*"; }

# ─── Cas 1 : déjà migré ───────────────────────────────────────────────────
# Le journal des migrations peut disparaître (restauration, machine neuve).
# Une migration rejouée doit être un non-événement, pas une erreur.
if [ -L "$OLD" ] && [ -d "$NEW" ]; then
  say "déjà migré — le tronc est en $NEW, $OLD est le lien de compatibilité"
  exit 0
fi

# ─── Cas 2 : rien à déplacer ──────────────────────────────────────────────
if [ ! -e "$OLD" ]; then
  if [ -d "$NEW" ]; then
    say "rien à déplacer — le tronc est déjà en $NEW"
  else
    say "aucun tronc trouvé — install.sh en créera un en $NEW"
  fi
  exit 0
fi

# ─── Cas 3 : collision ────────────────────────────────────────────────────
# Deux troncs réels, chacun avec des fiches. Fusionner à l'aveugle, ce serait
# décider à la place de l'utilisateur lequel gagne. On s'arrête : un arrêt net
# se répare, une fusion silencieuse se découvre trois semaines plus tard.
if [ -d "$NEW" ] && [ ! -L "$OLD" ]; then
  echo "❌ Deux troncs coexistent :"
  echo "     $OLD  ($(find "$OLD" -name '*.md' 2>/dev/null | wc -l | tr -d ' ') fiches)"
  echo "     $NEW  ($(find "$NEW" -name '*.md' 2>/dev/null | wc -l | tr -d ' ') fiches)"
  echo "   Je ne fusionne pas tout seul : ce sont tes notes."
  echo "   Choisis lequel garder, écarte l'autre, puis relance \`brain update\`."
  exit 1
fi

# ─── Le déplacement ───────────────────────────────────────────────────────
mkdir -p "$HOME/.c-brain"

# `mv` d'un dossier vers un dossier vide du MÊME volume : atomique, instantané,
# et il préserve le .git du tronc — donc tout l'historique des fiches.
mv "$OLD" "$NEW"
say "tronc déplacé : $OLD → $NEW"

# Lien de compatibilité. Il ne sert pas à C Brain (plus rien ne vise l'ancien
# chemin) mais à TOUT LE RESTE : le lien mémoire de l'agent CLI, les scripts
# perso de l'utilisateur, ses signets, un remote git noté quelque part. Sans
# lui, la migration casse des choses qu'aucun test d'ici ne connaît.
ln -s "$NEW" "$OLD"
say "lien de compatibilité posé : $OLD → $NEW"

# Contrôle exécuté, pas supposé : le lien doit résoudre sur un vrai dossier.
[ -d "$OLD/." ] || { echo "❌ $OLD ne résout pas après migration"; exit 1; }
say "vérifié — les deux chemins mènent au même tronc"
