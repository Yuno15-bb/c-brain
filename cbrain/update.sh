#!/usr/bin/env bash
# update.sh — met à jour le MOTEUR. Ne touche jamais au TRONC.
#
# Ce que ça fait :
#   1. récupère les tags publiés,
#   2. bascule sur le plus récent (jamais sur `main` : une branche de travail
#      n'a pas à s'installer chez quelqu'un),
#   3. joue les migrations non encore appliquées,
#   4. rejoue install.sh (idempotent) pour propager les nouveautés,
#   5. vérifie, et propose le retour arrière si ça casse.
#
# Ce que ça NE fait PAS : lire, modifier ou envoyer une seule de tes fiches.
#
# Usage : brain update [--check] [--rollback] [--force]
set -euo pipefail

CB="$HOME/.c-brain"
ENGINE="$(cd "$CB/engine" 2>/dev/null && pwd -P)" || { echo "❌ Moteur introuvable ($CB/engine)."; exit 1; }
STATE="$CB/state"
APPLIED="$STATE/migrations-appliquees.txt"
PREVIOUS="$STATE/version-precedente"
mkdir -p "$STATE"

MODE="update"
for a in "$@"; do
  case "$a" in
    --check) MODE="check" ;;
    --rollback) MODE="rollback" ;;
    --force) MODE="force" ;;
    *) echo "Usage : brain update [--check] [--rollback] [--force]"; exit 1 ;;
  esac
done

say()  { echo "  $*"; }
warn() { echo "  ⚠️  $*"; }

command -v git >/dev/null || { echo "❌ git est requis pour les mises à jour."; exit 1; }
git -C "$ENGINE" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "❌ Le moteur n'est pas un dépôt git — il a été copié, pas cloné."
  echo "   Reclone-le pour bénéficier des mises à jour."
  exit 1; }

current() { git -C "$ENGINE" describe --tags --exact-match 2>/dev/null || git -C "$ENGINE" rev-parse --short HEAD; }

# Le tag le plus récent au sens des versions, pas au sens alphabétique :
# sans `-V`, v10 passerait avant v9.
latest_tag() { git -C "$ENGINE" tag -l 'v*' | sort -V | tail -1; }

# ─── Retour arrière ───────────────────────────────────────────────────────
if [ "$MODE" = "rollback" ]; then
  [ -f "$PREVIOUS" ] || { echo "❌ Aucune version précédente enregistrée."; exit 1; }
  target="$(cat "$PREVIOUS")"
  echo "⏪ Retour à $target"
  git -C "$ENGINE" checkout -q "$target"
  bash "$ENGINE/install.sh" >/dev/null 2>&1 || warn "install.sh a signalé un problème"
  echo "✅ Revenu à $target. Tes fiches n'ont pas bougé."
  exit 0
fi

# ─── État distant ─────────────────────────────────────────────────────────
CUR="$(current)"
echo "🔄 C Brain — version installée : $CUR"

# --force : le dépôt distant fait autorité sur les tags. L'utilisateur n'en crée
# jamais — sans ça, un seul tag republié côté auteur fait échouer le fetch
# (« would clobber existing tag ») et BLOQUE toutes les mises à jour suivantes,
# en affichant « pas de réseau ». Panne silencieuse et définitive.
if ! FETCH_ERR="$(git -C "$ENGINE" fetch --tags --force 2>&1)"; then
  # Hors ligne, dépôt inaccessible, tag distant déplacé… Ce n'est pas bloquant,
  # mais on ne raconte pas « pas de réseau » quand la cause est autre : un
  # diagnostic faux coûte plus cher qu'un message un peu long.
  say "impossible de récupérer les versions distantes — on réessaiera plus tard."
  [ -n "$FETCH_ERR" ] && printf '%s\n' "$FETCH_ERR" | head -3 | sed 's/^/     /'
  exit 0
fi

NEW="$(latest_tag)"
[ -n "$NEW" ] || { say "aucune version publiée pour l'instant."; exit 0; }

if [ "$CUR" = "$NEW" ] && [ "$MODE" != "force" ]; then
  say "déjà à jour ($NEW)."
  exit 0
fi

echo "  nouvelle version disponible : $NEW"
if [ "$MODE" = "check" ]; then
  echo "  → \`brain update\` pour l'installer."
  exit 10   # 10 = « une mise à jour existe », lisible par un script
fi

# ─── Application ──────────────────────────────────────────────────────────
# Un moteur modifié à la main = travail de quelqu'un. On ne l'écrase pas.
if ! git -C "$ENGINE" diff --quiet || ! git -C "$ENGINE" diff --cached --quiet; then
  echo "❌ Le moteur a des modifications locales non commitées."
  echo "   Range-les (git stash / git commit) avant de mettre à jour."
  exit 1
fi

echo "$CUR" > "$PREVIOUS"
git -C "$ENGINE" checkout -q "$NEW"
say "moteur passé en $NEW"

# ─── Migrations ───────────────────────────────────────────────────────────
# Numérotées, jouées une seule fois, jamais destructrices sur le contenu.
touch "$APPLIED"
for m in "$ENGINE"/cbrain/migrations/*.sh; do
  [ -e "$m" ] || continue
  name="$(basename "$m")"
  grep -qxF "$name" "$APPLIED" && continue
  # ${name} avec accolades, obligatoire : collé à un caractère UTF-8, bash sur
  # macOS l'avale dans le NOM de la variable (« name… : unbound variable ») et
  # tue la mise à jour en plein milieu, juste après le checkout.
  say "migration ${name}…"
  if bash "$m"; then
    echo "$name" >> "$APPLIED"
  else
    warn "migration $name en échec — arrêt. \`brain update --rollback\` pour revenir."
    exit 1
  fi
done

# ─── Réinstallation + vérification ────────────────────────────────────────
say "réinstallation (idempotente)…"
bash "$ENGINE/install.sh" >/tmp/c-brain-update.log 2>&1 || warn "install.sh a signalé un problème (/tmp/c-brain-update.log)"

if bash "$HOME/claude-brain/hooks/selftest.sh" >/tmp/c-brain-update-selftest.log 2>&1; then
  echo
  echo "✅ Mis à jour en $NEW — selftest vert. Tes fiches n'ont pas été touchées."
else
  echo
  warn "selftest en ÉCHEC après mise à jour (/tmp/c-brain-update-selftest.log)"
  warn "Retour arrière conseillé :  brain update --rollback"
  exit 1
fi
