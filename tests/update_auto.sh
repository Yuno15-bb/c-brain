#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_auto.sh — la mise à jour automatique fait-elle vraiment ce qu'elle dit ?
#
# POURQUOI ÇA EXISTE. Depuis v1.28.0, le démarrage de session n'annonce plus une
# nouvelle version : il l'INSTALLE, en arrière-plan, sans qu'on demande rien.
# C'est du code distant qui s'exécute sur la machine de quelqu'un. Trois
# promesses tiennent cette décision, et une promesse non testée n'est qu'une
# intention :
#   1. ça s'applique VRAIMENT (sinon on a juste retiré l'avis qui marchait) ;
#   2. ça ne bloque JAMAIS le démarrage d'une session ;
#   3. si la nouvelle version casse l'outil, ça REVIENT tout seul — parce qu'en
#      automatique personne ne lit l'écran.
#
# ⚠ CE FICHIER EST PROPRE AU PAQUET et vit dans `tests/`, synchronisé avec
# `rsync --delete` : il DOIT rester dans les exclusions de `sync_dir tests`.
# Écrit sans l'exclusion le 2026-08-16, il a été effacé par la synchro suivante.
#
# Frère de update_rollback.sh, même faux amont local, même raison : un test qui
# dépend du vrai GitHub échoue pour des motifs étrangers au code.
#
# Lancement : bash tests/update_auto.sh   (macOS : install.sh vise Darwin)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FAILS=0

check() {  # check <code> <label> [detail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

[ "$(uname)" = "Darwin" ] || { echo "⤳ sauté : install.sh vise macOS"; exit 0; }

H="$(mktemp -d)"
# Le ménage attend la fin du travail détaché : effacer sous les pieds d'un
# processus qui écrit encore laisse « Directory not empty » et un HOME orphelin.
menage() { local n=0
  while [ -d "$H/.c-brain/state/auto-update.lock" ] && [ "$n" -lt 60 ]; do sleep 1; n=$((n+1)); done
  rm -rf "$H" 2>/dev/null || true; }
# CBRAIN_TEST_KEEP=1 garde le HOME de test pour l'autopsie. Sans ça, diagnostiquer
# un échec revient à relancer le banc en aveugle.
[ -n "${CBRAIN_TEST_KEEP:-}" ] || trap menage EXIT
[ -n "${CBRAIN_TEST_KEEP:-}" ] && echo "HOME de test conservé : $H"
export HOME="$H"

# Le hook part DÉTACHÉ : il rend la main avant que le travail soit fini. Tout ce
# qui suit doit donc attendre un observable, jamais « dormir un peu et espérer ».
#
# ⚠ ET IL FAUT ATTENDRE LE VERROU DEUX FOIS. Première écriture de ce banc :
# n'attendre que sa DISPARITION rendait la main immédiatement, parce que le
# processus détaché n'avait pas encore eu le temps de le POSER. Le banc mesurait
# l'état d'avant la mise à jour et le prenait pour le résultat — trois assertions
# rouges pour une seule cause, et aucune qui pointait la vraie.
# Attendre l'apparition PUIS la disparition, c'est attendre un travail ; attendre
# la seule absence, c'est confondre « pas encore commencé » et « déjà fini ».
attendre_fin() {  # attendre_fin [secondes]
  local n=0 max="${1:-180}" verrou="$H/.c-brain/state/auto-update.lock"
  while [ ! -d "$verrou" ] && [ "$n" -lt 15 ]; do sleep 1; n=$((n + 1)); done
  n=0
  while [ -d "$verrou" ] && [ "$n" -lt "$max" ]; do sleep 1; n=$((n + 1)); done
  sleep 1   # laisser le compte rendu atterrir après la levée du verrou
}

hook() { python3 "$H/.c-brain/engine/cbrain/check_update.py" 2>&1; }

echo "▸ amont local : une ancienne version, une nouvelle"
git clone -q "$ROOT" "$H/upstream"
cd "$H/upstream"
git config user.email cbrain-test
git config user.name cbrain-test
git checkout -q -B main
# On superpose l'ARBRE DE TRAVAIL : sans ça le test exerce le dernier commit et
# non le code qu'on vient d'écrire (cf. update_rollback.sh, même piège).
rsync -a --delete --exclude .git --exclude node_modules "$ROOT/" ./
git add -A
git diff --cached --quiet || git commit -q -m "test: working tree"
git tag -a v9.9.0 -m "test: old"

echo "new-version-marker" > UPDATE_MARKER
git add UPDATE_MARKER && git commit -q -m "test: new"
git tag -a v9.9.1 -m "test: new"

# ⚠ LES VERSIONS SUIVANTES SE CRÉENT AU MOMENT DE LEUR ACTE, jamais ici.
# Première écriture de ce banc : les trois tags étaient posés d'entrée, et le
# clone du moteur les emportait tous. `git fetch --tags` ne SUPPRIME pas un tag
# disparu de l'amont (il faudrait `--prune-tags`) : effacer v9.9.2 côté amont ne
# l'effaçait donc pas côté moteur, qui sautait directement sur la version cassée
# dès l'acte 2. Le banc mesurait un scénario qui n'était pas celui qu'il décrit.

echo "▸ installation de l'ANCIENNE version (v9.9.0)"
git clone -q "$H/upstream" "$H/engine-src"
cd "$H/engine-src"
git checkout -q v9.9.0
mkdir -p "$H/.claude"
printf '{"model": "opus"}\n' > "$H/.claude/settings.json"
"$H/engine-src/install.sh" --no-launchd --no-capsule --no-shortcut >"$H/install.log" 2>&1 \
  || { echo "❌ install échouée :"; tail -20 "$H/install.log"; exit 1; }
export PATH="$H/.local/bin:$PATH"

TRUNK="$H/.c-brain/trunk"
mkdir -p "$TRUNK/lessons"
printf -- "---\nname: mine\ndescription: \"ma fiche à moi\"\n---\ntravail que je ne peux pas perdre\n" \
  > "$TRUNK/lessons/mine.md"
NOTE_SUM="$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)"

echo
echo "▸ 1. le démarrage de session ne BLOQUE pas"
T0=$(date +%s)
SORTIE1="$(hook)"
T1=$(date +%s)
[ $((T1 - T0)) -le 5 ]
check $? "le hook rend la main en $((T1 - T0)) s (≤ 5)" "un démarrage de session attendait le réseau"
[ -z "$SORTIE1" ]
check $? "il n'annonce rien au premier passage" "obtenu : $SORTIE1"

echo
echo "▸ 2. et pourtant la mise à jour s'applique VRAIMENT, toute seule"
attendre_fin
[ -f "$H/.c-brain/engine/UPDATE_MARKER" ]
check $? "la nouvelle version est sur le disque, sans qu'on ait tapé quoi que ce soit" \
  "$(tail -5 "$H/.c-brain/state/auto-update.log" 2>/dev/null)"
[ "$(git -C "$H/.c-brain/engine" describe --tags --exact-match 2>/dev/null)" = "v9.9.1" ]
check $? "le moteur est sur v9.9.1"

echo
echo "▸ 3. le compte rendu arrive à la session SUIVANTE, et une seule fois"
SORTIE2="$(hook)"
printf '%s' "$SORTIE2" | grep -q "v9.9.1"
check $? "la session suivante annonce la version installée" "obtenu : $SORTIE2"
printf '%s' "$SORTIE2" | grep -q "tout seul"
check $? "elle dit que c'était automatique" "obtenu : $SORTIE2"
attendre_fin
SORTIE3="$(hook)"
[ -z "$SORTIE3" ]
check $? "elle ne le répète pas la fois d'après" "obtenu : $SORTIE3"

echo
echo "▸ 4. l'interrupteur coupe vraiment"
attendre_fin
brain update --auto-off >/dev/null 2>&1
( cd "$H/upstream" && echo "encore-plus-neuf" > AUTRE_MARQUEUR \
  && git add AUTRE_MARQUEUR && git commit -q -m "test: newer" && git tag -a v9.9.2 -m "test: newer" )
SORTIE4="$(hook)"
sleep 3
[ ! -f "$H/.c-brain/engine/AUTRE_MARQUEUR" ]
check $? "coupé, il n'installe plus rien"
printf '%s' "$SORTIE4" | grep -q "v9.9.2"
check $? "mais il SIGNALE encore la version disponible" "obtenu : $SORTIE4"

echo
echo "▸ 5. une version qui casse l'outil est défaite toute seule"
brain update --auto-on >/dev/null 2>&1
rm -f "$H/.c-brain/state/last-auto-update"
# La version CASSÉE : son selftest sort rouge. C'est le seul moyen de prouver le
# retour arrière automatique — le simuler par un drapeau prouverait le drapeau.
( cd "$H/upstream" \
  && printf '#!/usr/bin/env bash\necho "selftest volontairement cassé"\nexit 1\n' > hooks/selftest.sh \
  && git add hooks/selftest.sh && git commit -q -m "test: broken selftest" \
  && git tag -a v9.9.3 -m "test: broken" )
hook >/dev/null
attendre_fin
[ "$(git -C "$H/.c-brain/engine" describe --tags --exact-match 2>/dev/null)" = "v9.9.1" ]
check $? "le moteur est REVENU sur v9.9.1" "il est resté sur une version dont le selftest est rouge"
SORTIE5="$(hook)"
printf '%s' "$SORTIE5" | grep -qi "revenu\|retour"
check $? "et la session suivante le dit franchement" "obtenu : $SORTIE5"

echo
echo "▸ 6. pendant les cinq actes, la fiche de l'utilisateur n'a pas bougé"
[ -f "$TRUNK/lessons/mine.md" ]; check $? "la fiche existe toujours"
[ "$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)" = "$NOTE_SUM" ]
check $? "identique à l'octet" "une mise à jour automatique a réécrit le travail de l'utilisateur"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ la mise à jour automatique s'applique, se coupe, se défait, et ne touche aucune fiche"
  exit 0
fi
echo "❌ $FAILS échec(s) sur le chemin automatique"
exit 1
