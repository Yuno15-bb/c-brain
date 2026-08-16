#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
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
# Usage : brain update [--check] [--rollback] [--force] [--auto]
set -euo pipefail

CB="$HOME/.c-brain"
ENGINE="$(cd "$CB/engine" 2>/dev/null && pwd -P)" || { echo "❌ Moteur introuvable ($CB/engine)."; exit 1; }
STATE="$CB/state"
APPLIED="$STATE/migrations-appliquees.txt"
PREVIOUS="$STATE/version-precedente"
mkdir -p "$STATE"

# ─── Mise à jour automatique ──────────────────────────────────────────────
# Fichiers d'état partagés avec `cbrain/check_update.py`, qui déclenche le mode
# `--auto` au démarrage de session.
AUTO=0
VERROU="$STATE/auto-update.lock"          # un dossier : `mkdir` est atomique
JOURNAL="$STATE/auto-update.log"
RESULTAT="$STATE/last-auto-update"        # lu, affiché puis effacé par le hook
ARRET_AUTO="$STATE/auto-update-off"

MODE="update"
for a in "$@"; do
  case "$a" in
    --check) MODE="check" ;;
    --rollback) MODE="rollback" ;;
    --force) MODE="force" ;;
    --auto) AUTO=1; MODE="update" ;;
    --auto-off) MODE="auto-off" ;;
    --auto-on)  MODE="auto-on" ;;
    --passer-en-anglais|--switch-en) MODE="switch" ;;
    *) echo "Usage : brain update [--check] [--rollback] [--force] [--auto|--auto-off|--auto-on] [--passer-en-anglais]"; exit 1 ;;
  esac
done

# ─── L'interrupteur ───────────────────────────────────────────────────────
# Il vient AVANT tout le reste, exprès : couper l'automatique ne doit dépendre
# ni du réseau, ni de l'état du dépôt, ni de rien qui puisse échouer. C'est la
# seule commande de ce fichier qui doit marcher même quand tout va mal.
if [ "$MODE" = "auto-off" ]; then
  mkdir -p "$STATE"; : > "$ARRET_AUTO"
  echo "✅ Mise à jour automatique COUPÉE."
  echo "   Le démarrage de session signalera les nouvelles versions sans les installer."
  echo "   Pour la remettre :  brain update --auto-on"
  exit 0
fi
if [ "$MODE" = "auto-on" ]; then
  rm -f "$ARRET_AUTO"
  echo "✅ Mise à jour automatique REMISE."
  echo "   Chaque démarrage de session installera la dernière version publiée."
  exit 0
fi

# ─── Préambule du mode automatique ────────────────────────────────────────
# POURQUOI CE MODE EXISTE. Jusqu'ici la mise à jour était un geste : le hook
# signalait, l'utilisateur tapait `brain update`. Personne ne tapait. Le moteur
# publié restait des semaines derrière celui de l'auteur, et le seul signe était
# une ligne au démarrage qu'on apprend à ne plus lire.
#
# Ce que ça change côté sûreté, dit franchement : du code venu du dépôt distant
# s'installe désormais SANS qu'on le demande. C'est un canal d'exécution. Trois
# contreparties, non négociables :
#   · `$ARRET_AUTO` (ou CBRAIN_NO_AUTO_UPDATE=1) rend le comportement d'avant —
#     on signale, on n'applique pas. La porte de sortie existe AVANT la porte
#     d'entrée.
#   · le selftest décide. En automatique personne ne regarde l'écran : une mise
#     à jour qui casse l'outil et le LAISSE cassé serait pire que pas de mise à
#     jour du tout. Donc rouge = retour arrière immédiat, par le script.
#   · rien ne bloque jamais une session — c'est le hook qui détache, ici on ne
#     fait que travailler en silence dans un journal.
if [ "$AUTO" = "1" ]; then
  if [ -e "$ARRET_AUTO" ] || [ -n "${CBRAIN_NO_AUTO_UPDATE:-}" ]; then exit 0; fi

  # Un verrou, parce que plusieurs sessions démarrent en même temps. `mkdir`
  # échoue si le dossier existe : c'est le test-et-pose atomique du shell, là où
  # `[ -f ] && touch` laisse une fenêtre entre les deux.
  # Verrou périmé : une machine qui s'endort ou une session tuée en plein milieu
  # laisserait le dossier pour toujours, et l'auto-update mourrait en silence —
  # exactement le genre de panne muette qu'on cherche à éviter.
  if ! mkdir "$VERROU" 2>/dev/null; then
    if [ -n "$(find "$VERROU" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
      rm -rf "$VERROU"; mkdir "$VERROU" 2>/dev/null || exit 0
    else
      exit 0                      # une autre session s'en occupe déjà
    fi
  fi
  trap 'rm -rf "$VERROU"' EXIT INT TERM

  # Tout ce que le script raconte part au journal : en automatique il n'y a pas
  # d'écran. Le journal est écrasé à chaque passage — on veut la dernière panne
  # lisible, pas un fichier qui grossit sans que personne n'y revienne.
  exec >"$JOURNAL" 2>&1
  echo "=== auto-update $(date '+%Y-%m-%d %H:%M:%S') ==="
fi

# Écrit le compte rendu que le hook affichera à la session SUIVANTE. Une seule
# ligne, deux champs : l'état, puis la version concernée.
resultat() { [ "$AUTO" = "1" ] && printf '%s\t%s\n' "$1" "$2" > "$RESULTAT"; return 0; }

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
# À quelle FAMILLE de tags appartient cette installation — anglaise (`v1.2.3`)
# ou française (`v1.2.3-fr`).
#
# ⚠ Ce n'est pas de la décoration, c'est un bug de bascule de langue.
# Les tags ne sont pas rangés par branche, donc `git tag -l 'v*'` rend les deux
# familles d'un coup — et `sort -V` place `v1.18.0-fr` APRÈS `v1.18.0`. Prendre
# le maximum global faisait donc basculer une installation ANGLAISE sur l'arbre
# FRANÇAIS dès que la branche fr rattrapait son retard, sans la moindre erreur :
# le tag existe, le checkout réussit, et l'utilisateur trouve simplement son
# outil en train de parler une autre langue. Ça n'est resté caché que tant que
# `fr` traînait derrière.
#
# Donc : lire la famille sur ce qui est installé, et ne jamais en sortir.
#
# Le seul cas que ça ne peut pas trancher, c'est un tag nu et un tag `-fr` sur
# le MÊME commit, où `--exact-match` en choisit un arbitrairement. Ça ne peut
# pas arriver ici : les deux branches divergent par construction, `main` étant
# la traduction de `fr`. Si elles convergeaient un jour, il faudrait une famille
# ENREGISTRÉE au lieu d'une famille déduite.
# ⚠ FAMILLE ENREGISTRÉE — posée le 2026-08-13 avec la fin de la famille `-fr`.
# La déduction ci-dessous lit la famille sur le tag INSTALLÉ. Elle est donc
# incapable d'enregistrer un choix : une installation française qui bascule en
# anglais retomberait sur `-fr` au moindre doute. Le fichier tranche, et il
# n'existe que si quelqu'un l'a écrit — personne ne bascule tout seul.
FAMILLE_FICHIER="$STATE/tag-family"

family() {
  local tag branch
  if [ -f "$FAMILLE_FICHIER" ]; then cat "$FAMILLE_FICHIER"; return; fi
  tag="$(git -C "$ENGINE" describe --tags --exact-match 2>/dev/null || true)"
  case "$tag" in
    *-fr) echo "-fr"; return ;;
    v*)   echo "";    return ;;
  esac
  # Pas posé sur un tag (clone frais, ou checkout détaché) : on retombe sur la
  # branche que suit le clone.
  branch="$(git -C "$ENGINE" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [ "$branch" = "fr" ] && echo "-fr" || echo ""
}

# Le tag le plus récent de la famille de CETTE installation, par ordre de
# version et non alphabétique : sans `-V`, v10 passerait avant v9.
latest_tag() {
  local suffix rx
  suffix="$(family)"
  if [ -n "$suffix" ]; then rx='^v[0-9]+\.[0-9]+\.[0-9]+-fr$'
  else                      rx='^v[0-9]+\.[0-9]+\.[0-9]+$'; fi
  # `|| true` : sans tag correspondant, `grep` sort 1, et sous `set -e` +
  # `pipefail` ça tuerait le script une ligne avant le contrôle de résultat
  # vide qui, lui, gère déjà le cas proprement.
  git -C "$ENGINE" tag -l 'v*' | grep -E "$rx" | sort -V | tail -1 || true
}

# ─── Fin de la famille française ──────────────────────────────────────────
#
# POURQUOI CE BLOC EXISTE. `fr` a cessé d'être un produit le 2026-08-13 :
# `publish.sh` y refuse tout tag. Or `latest_tag()` filtre PAR FAMILLE — une
# installation `-fr` ne verra donc jamais un tag nu, et `brain update` lui
# répondra « déjà à jour (v1.27.0-fr) » jusqu'à la fin des temps. Pas « la
# famille s'arrête », pas « voici la suite » : un vert qui ment, et invisible
# depuis chez l'auteur.
#
# Or le `update.sh` d'une install figée est figé lui aussi : AUCUN correctif
# futur ne peut l'atteindre. Le seul canal qui reste est une dernière release
# `-fr` — celle-ci — dont le CONTENU porte la bascule. Une install à
# v1.27.0-fr voit v1.28.0-fr par sa propre logique de famille, l'installe
# normalement, et se retrouve avec ce bloc en place.
#
# La bascule n'est jamais automatique : elle CHANGE LA LANGUE de l'outil, et
# c'est exactement le bug que `tests/update_tag_family.sh` existe pour tenir.
# On informe, l'utilisateur décide.
version_nue() {   # la version la plus récente de la famille NUE, ou vide
  git -C "$ENGINE" tag -l 'v*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1 || true
}

fin_de_famille() {   # affiche l'avis si la famille -fr est close pour cette install
  [ "$(family)" = "-fr" ] || return 0
  # ⚠ LA BONNE QUESTION est « ma famille a-t-elle encore quelque chose pour moi ? »,
  #   pas « la famille anglaise est-elle plus récente ? ». Une install à
  #   v1.27.0-fr qui a encore v1.28.0-fr devant elle n'est PAS en fin de famille :
  #   lui parler de bascule la ferait sortir d'un arbre encore vivant.
  [ "$(latest_tag)" = "$CUR" ] || return 0
  local nue cur_nu
  nue="$(version_nue)"
  [ -n "$nue" ] || return 0                     # aucune famille nue → rien à proposer
  cur_nu="${CUR%-fr}"
  echo
  echo "  ℹ️  $CUR est la DERNIÈRE version française — la famille s'arrête ici."
  if [ "$cur_nu" != "$nue" ] && \
     [ "$(printf '%s\n%s\n' "$cur_nu" "$nue" | sort -V | tail -1)" = "$nue" ]; then
    echo "      Une version plus récente existe déjà en anglais : $nue"
  else
    echo "      La suite est publiée en anglais seulement (dernière en date : $nue)."
  fi
  echo "      Tes fiches ne bougent pas : seule la langue du MOTEUR change."
  echo "      → brain update --passer-en-anglais"
}

if [ "$MODE" = "switch" ]; then
  mkdir -p "$STATE"
  : > "$FAMILLE_FICHIER"            # famille nue = suffixe vide, choix ENREGISTRÉ
  echo "✅ Famille anglaise enregistrée. Mise à jour en cours…"
  MODE="update"
fi

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
  fin_de_famille                    # « à jour » dans une famille close doit le DIRE
  exit 0
fi

echo "  nouvelle version disponible : $NEW"

# D'OÙ VIENT LE CODE. Une mise à jour remplace le moteur — elle fera tourner du
# code sur cette machine à la session suivante. Nommer une version, ce n'est pas
# nommer une source : un remote peut être changé par quiconque peut écrire dans
# la config git du moteur, et un tag peut être déplacé. Donc l'URL d'origine et
# le commit exact sont affichés AVANT d'appliquer quoi que ce soit, parce que
# c'est ce qu'une personne aurait besoin de vérifier.
#
# C'est de la divulgation, pas de la vérification. Les tags ne sont pas signés
# (voir SECURITY.md) ; ce qui suit te permet de regarder, pas à la machine de
# refuser.
REMOTE_URL="$(git -C "$ENGINE" remote get-url origin 2>/dev/null || echo "inconnu")"
TARGET_SHA="$(git -C "$ENGINE" rev-parse --short "$NEW" 2>/dev/null || echo "inconnu")"
echo "  depuis : $REMOTE_URL"
echo "  commit : $TARGET_SHA"
if [ "$MODE" = "check" ]; then
  echo "  → \`brain update\` pour l'installer."
  exit 10   # 10 = « une mise à jour existe », lisible par un script
fi

# ─── Application ──────────────────────────────────────────────────────────
# Un moteur modifié à la main = travail de quelqu'un. On ne l'écrase pas.
if ! git -C "$ENGINE" diff --quiet || ! git -C "$ENGINE" diff --cached --quiet; then
  echo "❌ Le moteur a des modifications locales non commitées."
  echo "   Range-les (git stash / git commit) avant de mettre à jour."
  # En automatique, ce n'est pas une panne : c'est un refus délibéré d'écraser le
  # travail de quelqu'un. Mais il doit se VOIR, sinon l'installation décroche
  # version après version pendant que le démarrage reste silencieux.
  resultat "bloquee" "$NEW"
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

# ⚠ REMETTRE LE MOTEUR PROPRE — sans ça, `brain update` marche UNE FOIS.
#
# Mesuré le 2026-08-16 : `install.sh` lance `npm install` dans la capsule, et npm
# RÉÉCRIT `capsule/package-lock.json`. Le moteur se retrouve avec une
# modification non commitée… que le contrôle ci-dessus refuse. La deuxième mise
# à jour répondait donc « ❌ modifications locales » et TOUTES les suivantes
# aussi. Panne définitive, sur une machine où personne ne soupçonne d'avoir
# touché quoi que ce soit. La cause de fond (lock incohérent avec package.json)
# est corrigée dans rules.json ; cette ligne est le filet, pour le prochain
# fichier généré qu'on n'a pas vu venir.
#
# Restaurer est SANS RISQUE ici, et c'est le contrôle plus haut qui le garantit :
# il a exigé un arbre propre AVANT de commencer. Tout ce qui est sale à cet
# instant a donc été produit par l'installeur lui-même, jamais par l'utilisateur.
# `checkout -- .` ne touche que les fichiers SUIVIS : `node_modules/` et le reste
# du non-suivi restent en place.
if ! git -C "$ENGINE" diff --quiet; then
  say "l'installeur a modifié des fichiers du moteur — remise à l'état de $NEW"
  git -C "$ENGINE" checkout -- . 2>/dev/null || warn "restauration partielle du moteur"
fi

if bash "$HOME/.c-brain/trunk/hooks/selftest.sh" >/tmp/c-brain-update-selftest.log 2>&1; then
  echo
  echo "✅ Mis à jour en $NEW — selftest vert. Tes fiches n'ont pas été touchées."
  resultat "ok" "$NEW"
else
  echo
  warn "selftest en ÉCHEC après mise à jour (/tmp/c-brain-update-selftest.log)"
  if [ "$AUTO" = "1" ]; then
    # ⚠ LA DIFFÉRENCE ENTRE LES DEUX MODES EST ICI, et c'est la seule qui compte.
    # À la main, conseiller le retour arrière suffit : quelqu'un lit l'écran.
    # En automatique, ce conseil ne serait lu par personne — l'outil resterait
    # cassé jusqu'à ce que l'utilisateur s'en aperçoive tout seul, sans savoir
    # que c'est une mise à jour qu'il n'a pas demandée qui l'a cassé. Donc on
    # revient, tout de suite, et on le DIT à la session suivante.
    warn "mode automatique : retour à $CUR"
    git -C "$ENGINE" checkout -q "$CUR" || true
    bash "$ENGINE/install.sh" >/dev/null 2>&1 || warn "install.sh a signalé un problème au retour"
    resultat "retour-arriere" "$NEW"
  else
    warn "Retour arrière conseillé :  brain update --rollback"
  fi
  exit 1
fi
