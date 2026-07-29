#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
# sync.sh — ~/claude-brain (Brain vivant de l'auteur, source de vérité) → dépôt C Brain.
#
# PRINCIPE : liste blanche. Ce qui n'est pas listé ici ne sort pas, point.
# Une liste noire laisserait passer par défaut ; un seul oubli = fuite de PII.
#
# Sens UNIQUE : ce script LIT ~/claude-brain et n'y écrit jamais rien.
#
# Usage :
#   ./sync.sh            copie effective
#   ./sync.sh --check    n'écrit rien, signale la divergence (sortie 1 si divergé)
set -euo pipefail

SRC="${CBRAIN_SRC:-$HOME/claude-brain}"
DEST="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="${CBRAIN_CLAUDE_DIR:-$HOME/.claude}"

MODE="copy"
[ "${1:-}" = "--check" ] && MODE="check"

# --itemize-changes dans les DEUX modes : le rapport doit dire ce qui a bougé,
# pas seulement ce qui aurait bougé.
RSYNC_FLAGS=(-a --delete --itemize-changes)
[ "$MODE" = "check" ] && RSYNC_FLAGS+=(--dry-run)

[ -d "$SRC" ] || { echo "❌ Source introuvable : $SRC"; exit 1; }
[ "$SRC" = "$DEST" ] && { echo "❌ Source et destination identiques."; exit 1; }

# --- EMPREINTE DE LA SOURCE ------------------------------------------------
# `--check` ne peut PAS comparer le paquet à la source : generalize.py réécrit
# les fichiers juste après la copie, donc ils diffèrent par construction et la
# comparaison serait rouge à jamais.
#
# La bonne question est « la SOURCE a-t-elle bougé depuis la dernière copie ? ».
# On y répond avec une empreinte des fichiers sources au moment du sync.
MANIFEST="$DEST/.sync-manifest"

empreinte_source() {
  {
    shasum -a 256 "$SRC/brain" "$CLAUDE_DIR/statusline.py" 2>/dev/null
    find "$SRC/hooks" "$SRC/agents" "$SRC/capsule" "$SRC/planet" \
         "$SRC/companion" "$SRC/tests" -type f \
         ! -path "*/node_modules/*" ! -name "*.pyc" ! -name ".DS_Store" \
         ! -name "graph.json" ! -name "desktop_sync.py" \
         ! -name "com.dylan.desktop-sync.plist.template" \
         ! -name "com.claudebrain.resume.plist" \
         ! -path "*/capsule/assets/*" 2>/dev/null \
      | sort | xargs shasum -a 256 2>/dev/null
  } | sed "s|$SRC/||; s|$CLAUDE_DIR/||" | sort -k2
}

if [ "$MODE" = "check" ]; then
  echo "🔄 C Brain — le Brain vivant a-t-il bougé depuis la dernière copie ?"
  if [ ! -f "$MANIFEST" ]; then
    echo "  ⚠️  aucune empreinte enregistrée — lance ./sync.sh une fois."
    exit 1
  fi
  DIFF="$(diff <(cat "$MANIFEST") <(empreinte_source) || true)"
  if [ -z "$DIFF" ]; then
    echo "  ✅ inchangé — le paquet est à jour."
    exit 0
  fi
  echo "  ⚠️  la source a changé :"
  printf '%s\n' "$DIFF" | grep -E '^[<>]' | awk '{print "      " $1 " " $3}' | sort -u | head -20
  echo
  echo "  → ./sync.sh pour reporter les changements, puis relis le diff git."
  exit 1
fi

DIVERGED=0
report() {  # report <étiquette> <sortie rsync>
  if [ -n "$2" ]; then
    DIVERGED=1
    echo "  ~ $1"
    printf '%s\n' "$2" | sed 's/^/      /'
  else
    echo "  = $1"
  fi
}

sync_dir() {  # sync_dir <sous-chemin> <exclusions...>
  local rel="$1"; shift
  local excludes=()
  for e in "$@"; do excludes+=(--exclude "$e"); done
  mkdir -p "$DEST/$rel"
  local out
  # ${a[@]+"${a[@]}"} : bash 3.2 (celui de macOS) traite un tableau vide comme
  # une variable non définie sous `set -u`. Cette forme le protège.
  out="$(rsync "${RSYNC_FLAGS[@]}" ${excludes[@]+"${excludes[@]}"} \
        "$SRC/$rel/" "$DEST/$rel/" 2>/dev/null || true)"
  report "$rel/" "$out"
}

sync_file() {  # sync_file <source absolue> <destination relative>
  # PAS de rsync ici. macOS 27 fournit openrsync, qui sur un fichier SEUL en
  # --dry-run signale toujours un transfert, même à contenu identique → fausse
  # divergence permanente en mode --check. `cmp` est déterministe.
  local src="$1" dst="$DEST/$2"
  if [ ! -f "$src" ]; then
    DIVERGED=1; echo "  ! $2 — source absente ($src)"; return
  fi
  if cmp -s "$src" "$dst" 2>/dev/null; then
    report "$2" ""
  else
    report "$2" ">f  contenu différent"
    # `[ … ] && { … }` en DERNIÈRE instruction renvoie 1 quand le test est faux :
    # sous `set -e`, ça tuait le script au 1ᵉʳ fichier divergent en mode --check,
    # SANS message — on croyait le reste à jour alors que rien n'avait été scanné.
    # Le `if/fi` + `return 0` explicite ferme le trou.
    if [ "$MODE" = "copy" ]; then
      mkdir -p "$(dirname "$dst")"
      cp -p "$src" "$dst"
    fi
  fi
  return 0
}

echo "🔄 C Brain — synchronisation depuis $SRC"
[ "$MODE" = "check" ] && echo "   (mode --check : rien n'est écrit)"
echo

# --- 1. CLI ---------------------------------------------------------------
sync_file "$SRC/brain" "brain"

# --- 2. Hooks -------------------------------------------------------------
# EXCLUS : desktop_sync.py + son plist (sauvegarde du Bureau de l'auteur vers SON
# GitHub — perso, et destructeur chez un tiers), et le .plist non-template qui
# porte /Users/mac en dur (seul le .template part).
#
# EXCLU AUSSI : hooks.json. Il n'existe QUE dans le paquet — c'est le manifeste
# de hooks du plugin Claude Code, pas un fichier du Brain vivant. rsync tourne
# avec --delete : sans cette exclusion, le premier sync venu l'effacerait, et
# le plugin cesserait d'enregistrer QUOI QUE CE SOIT sans une seule erreur.
sync_dir hooks \
  'desktop_sync.py' \
  'com.dylan.desktop-sync.plist.template' \
  'com.claudebrain.resume.plist' \
  'hooks.json' \
  '__pycache__' '*.pyc'

# --- 3. Agents ------------------------------------------------------------
sync_dir agents

# --- 4. Capsule -----------------------------------------------------------
# EXCLUS : node_modules (282 Mo, réinstallé par install.sh) et assets/ (7,4 Mo
# de poids MORT — vérifié le 2026-07-26 : le sprite est inline dans index.html,
# aucun fichier de assets/ n'est référencé par le code).
sync_dir capsule 'node_modules' 'assets'

# --- 5. Planète -----------------------------------------------------------
# EXCLU : graph.json — 1,4 Mo contenant le TEXTE INTÉGRAL des fiches, noms de
# clients compris. Régénéré à chaque lancement par graph_export.py.
sync_dir planet 'graph.json'

# --- 6. Companion ---------------------------------------------------------
sync_dir companion '__pycache__' '*.pyc'

# --- 7. Tests --------------------------------------------------------------
# EXCLUS : les tests propres au PAQUET (manifeste de plugin, anglais seul).
# Ils n'ont pas d'équivalent dans le Brain vivant ; --delete les emporterait.
sync_dir tests 'plugin_manifest.py' 'english_only.py' '__pycache__' '*.pyc'

# --- 8. Statusline (vit dans ~/.claude, pas dans le tronc) ----------------
sync_file "$CLAUDE_DIR/statusline.py" "statusline.py"

echo
# --- 9. Généralisation ----------------------------------------------------
# ENCHAÎNÉE, jamais optionnelle : la copie qui vient d'avoir lieu a RÉINTRODUIT
# les noms de l'auteur, de ses clients et de ses projets. Un sync sans
# généralisation laisse le paquet en état de fuite, et rien ne le signalerait
# avant le leakcheck.
echo "───"
python3 "$DEST/generalize.py"

# Empreinte écrite APRÈS la généralisation : elle atteste « voici l'état de la
# source que ce paquet reflète ». L'écrire avant laisserait croire le paquet à
# jour si la généralisation venait d'échouer.
empreinte_source > "$MANIFEST"

echo
echo "✅ Synchronisé et généralisé. Contrôle final : python3 leakcheck.py"
