#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_rollback.sh — une mise à jour qu'on ne peut pas défaire n'en est pas une.
#
# POURQUOI ÇA EXISTE. `brain update` remplace le moteur, joue les migrations et
# rejoue l'installeur, sur une machine où l'utilisateur garde des fiches qu'il
# ne peut pas perdre. Tout ça est testable et rien ne l'était : la CI prouvait
# que la PREMIÈRE install marche, jamais la seconde, et jamais le retour.
#
# Il tourne contre un faux amont LOCAL, pas GitHub. Un test qui dépend du vrai
# distant échoue quand un tag bouge ou que le réseau hoquette, et un test qui
# échoue pour des raisons étrangères au code est un test qu'on apprend à ignorer.
#
# Les deux choses à prouver, par ordre de ce que ça coûte de se tromper :
#   1. les fiches de l'utilisateur survivent à une mise à jour ET à un retour —
#      un outil de mémoire qui perd la mémoire en changeant de version n'a
#      aucune raison d'exister ;
#   2. le moteur bouge vraiment, et revient vraiment.
#
# Lancement : bash tests/update_rollback.sh   (macOS : install.sh vise Darwin)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FAILS=0

check() {  # check <label> <condition-as-exit-code> [detail]
  if [ "$1" = "0" ]; then echo "  ✅ $2"; else echo "  ❌ $2${3:+  — $3}"; FAILS=$((FAILS + 1)); fi
}

[ "$(uname)" = "Darwin" ] || { echo "⤳ sauté : install.sh vise macOS"; exit 0; }

H="$(mktemp -d)"
trap 'rm -rf "$H"' EXIT
export HOME="$H"

echo "▸ construction d'un amont local à deux versions"
git clone -q "$ROOT" "$H/upstream"
cd "$H/upstream"
git config user.email cbrain-test
git config user.name cbrain-test
git checkout -q -B main

# ⚠ On superpose l'ARBRE DE TRAVAIL au clone. `git clone` copie l'historique
# commité : sans ça, le test exerce en silence le dernier commit au lieu du code
# sur le disque — ce qu'il faisait, et c'est ainsi que cette ligne est née : une
# mutation volontairement introduite dans update.sh laissait la suite totalement
# verte. Un test qui lit un autre code que celui qu'on modifie ne prouve rien.
rsync -a --delete --exclude .git --exclude node_modules "$ROOT/" ./
git add -A
git diff --cached --quiet || git commit -q -m "test: working tree"

# L'ANCIENNE version, c'est l'arbre de travail. La NOUVELLE ajoute un marqueur
# qu'on peut chercher — preuve que le moteur a bougé, et non qu'il l'annonce.
git tag -a v9.9.0 -m "test: old" 2>/dev/null || { echo "❌ v9.9.0 existe déjà"; exit 1; }
echo "new-version-marker" > UPDATE_MARKER
git add UPDATE_MARKER && git commit -q -m "test: new"
git tag -a v9.9.1 -m "test: new"

echo "▸ installation de l'ANCIENNE version"
git clone -q "$H/upstream" "$H/engine-src"
cd "$H/engine-src"
git checkout -q v9.9.0
mkdir -p "$H/.claude"
printf '{"model": "opus"}\n' > "$H/.claude/settings.json"
"$H/engine-src/install.sh" --no-launchd --no-capsule --no-shortcut >"$H/install.log" 2>&1 \
  || { echo "❌ install échouée :"; tail -20 "$H/install.log"; exit 1; }
export PATH="$H/.local/bin:$PATH"

TRUNK="$H/.c-brain/trunk"
# Une fiche écrite par l'utilisateur. Elle doit rester intacte à chaque étape.
mkdir -p "$TRUNK/lessons"
printf -- "---\nname: mine\ndescription: \"ma fiche à moi\"\n---\ntravail que je ne peux pas perdre\n" \
  > "$TRUNK/lessons/mine.md"
NOTE_SUM="$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)"

[ "$(brain version 2>/dev/null | tr -d '[:space:]')" ] || true
echo "  installée : $(git -C "$H/.c-brain/engine" describe --tags --exact-match 2>/dev/null)"

echo "▸ brain update --check annonce la version sans l'appliquer"
brain update --check >"$H/check.log" 2>&1; rc=$?
grep -q "v9.9.1" "$H/check.log"; check $? "--check nomme la nouvelle version" "$(tail -2 "$H/check.log")"
[ "$rc" = "10" ]; check $? "--check sort en 10 (une mise à jour existe)" "obtenu $rc"
[ ! -f "$H/.c-brain/engine/UPDATE_MARKER" ]; check $? "--check n'a rien appliqué"

# D'OÙ, exactement. Une mise à jour fait tourner du code sur cette machine ;
# nommer une version n'est pas nommer une source. Les deux lignes sont vérifiées
# parce qu'une divulgation que personne ne contrôle est une divulgation qu'un
# remaniement supprime en silence — elle ne casse rien en partant.
grep -q "depuis :.*upstream" "$H/check.log"
check $? "--check dit de quel remote viendrait le code" "$(tail -4 "$H/check.log")"
grep -qE "commit : [0-9a-f]{7,}" "$H/check.log"
check $? "--check nomme le commit exact vers lequel il irait" "$(tail -4 "$H/check.log")"

echo "▸ brain update déplace le moteur"
brain update >"$H/update.log" 2>&1 || { echo "❌ mise à jour échouée :"; tail -20 "$H/update.log"; FAILS=$((FAILS+1)); }
[ -f "$H/.c-brain/engine/UPDATE_MARKER" ]; check $? "la nouvelle version est vraiment sur le disque" "$(tail -3 "$H/update.log")"
[ "$(git -C "$H/.c-brain/engine" describe --tags --exact-match 2>/dev/null)" = "v9.9.1" ]
check $? "le moteur annonce le nouveau tag"
# ⚠ Le fichier s'appelle `version-precedente` ici et `previous-version` sur
# `main` : la traduction a renommé jusqu'aux fichiers d'état. Écrit en dur
# plutôt que déduit, pour que le jour où l'un des deux bouge, ce test le dise.
[ "$(cat "$H/.c-brain/state/version-precedente" 2>/dev/null)" = "v9.9.0" ]
check $? "la version précédente a été enregistrée" "le retour n'aurait nulle part où aller"

echo "▸ brain update --rollback remet en place"
brain update --rollback >"$H/rollback.log" 2>&1 || { echo "❌ retour arrière échoué :"; tail -20 "$H/rollback.log"; FAILS=$((FAILS+1)); }
[ ! -f "$H/.c-brain/engine/UPDATE_MARKER" ]; check $? "la nouvelle version a disparu du disque"
[ "$(git -C "$H/.c-brain/engine" describe --tags --exact-match 2>/dev/null)" = "v9.9.0" ]
check $? "le moteur est revenu sur l'ancien tag"

echo "▸ et pendant tout ça, les fiches n'ont pas bougé"
[ -f "$TRUNK/lessons/mine.md" ]; check $? "la fiche existe toujours"
[ "$(shasum -a 256 "$TRUNK/lessons/mine.md" | cut -d' ' -f1)" = "$NOTE_SUM" ]
check $? "la fiche est identique à l'octet" "une mise à jour ou un retour a réécrit le travail de l'utilisateur"

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ mise à jour et retour arrière marchent, et aucun ne touche une fiche"
  exit 0
fi
echo "❌ $FAILS échec(s) sur le chemin mise à jour / retour"
exit 1
