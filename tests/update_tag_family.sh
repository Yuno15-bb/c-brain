#!/usr/bin/env bash
# C Brain — Copyright (c) 2026 Dylan Peellaert.
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
#
# update_tag_family.sh — la mise à jour ne doit JAMAIS changer la langue de
# l'utilisateur.
#
# POURQUOI CE TEST EXISTE. Les tags ne sont pas rangés par branche, donc
# `git tag -l 'v*'` rend d'un coup la famille anglaise et la française — et
# `sort -V` place `v1.18.0-fr` APRÈS `v1.18.0`. Prendre le maximum global
# faisait basculer une installation ANGLAISE sur l'arbre FRANÇAIS dès que la
# branche fr rattrapait son retard, sans la moindre erreur : le tag existe, le
# checkout réussit, et l'utilisateur trouve simplement son outil en train de
# parler une autre langue.
#
# C'est resté invisible aussi longtemps que `fr` traînait derrière. C'est
# exactement le genre de défaut qu'un test doit tenir, parce que rien d'autre
# ne le signalera.
#
# Le test construit un dépôt jetable avec la vraie topologie — deux branches
# qui divergent, chacune portant sa famille de tags — et vérifie qu'une
# installation de chaque famille se voit proposer SA propre dernière version.
#
# Lancement : bash tests/update_tag_family.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
FAILS=0

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

git init -q -b main "$T/engine"
cd "$T/engine"
# PAS une adresse plausible : leakcheck scanne ce dépôt à la recherche de
# motifs d'e-mail, et un bouche-trou qui en imite un ferait virer le garde-fou
# au rouge sur un fichier qui ne fuit rien. git accepte n'importe quelle chaîne.
git config user.email cbrain-test
git config user.name cbrain-test

echo base > f && git add f && git commit -qm base
git checkout -q -b fr && echo fr1 > f && git commit -qam fr1 && git tag -a v1.17.0-fr -m x
git checkout -q main && echo en1 > f && git commit -qam en1 && git tag -a v1.17.0 -m x
echo en2 > f && git commit -qam en2 && git tag -a v1.18.0 -m x
git checkout -q fr && echo fr2 > f && git commit -qam fr2 && git tag -a v1.18.0-fr -m x

# Le bug, démontré : le maximum global est le tag FRANÇAIS.
naif="$(git tag -l 'v*' | sort -V | tail -1)"
[ "$naif" = "v1.18.0-fr" ] || {
  echo "⚠️  la prémisse ne tient plus : le max global est '$naif', pas v1.18.0-fr"
}

# On charge les VRAIES fonctions depuis update.sh au lieu de les réécrire ici —
# une copie dans le test continuerait de passer après que le code livré a cassé.
ENGINE="$T/engine"
# STATE et FAMILLE_FICHIER sont chargés aussi : `family()` lit la famille
# ENREGISTRÉE avant d'en déduire une, et un banc qui l'omettait testait une
# version de la fonction que le script livré n'exécute jamais — exactement la
# dérive que cet `eval` existe pour éviter. Sans ça, sous `set -u`, la variable
# non définie tuait `family()` : le suffixe revenait vide, et le banc voyait une
# install FRANÇAISE se faire proposer l'arbre anglais.
STATE="$T/state"
mkdir -p "$STATE"
eval "$(sed -n '/^FAMILLE_FICHIER=/p;/^family() {/,/^}/p;/^latest_tag() {/,/^}/p' "$ROOT/cbrain/update.sh")"

check() {  # check <libellé> <checkout> <attendu>
  git -C "$ENGINE" checkout -q "$2"
  local got; got="$(latest_tag)"
  if [ "$got" = "$3" ]; then
    echo "  ✅ $1 → $got"
  else
    echo "  ❌ $1 → obtenu '$got', attendu '$3'"
    FAILS=$((FAILS + 1))
  fi
}

echo "▸ chaque installation se voit proposer sa propre famille"
check "install anglaise (sur v1.17.0)"   v1.17.0    v1.18.0
check "install française (sur v1.17.0-fr)" v1.17.0-fr v1.18.0-fr
check "clone frais de la branche fr"      fr         v1.18.0-fr
check "clone frais de la branche main"    main       v1.18.0

echo "▸ la famille ENREGISTRÉE l'emporte sur la famille déduite"
# La fin de la famille `-fr` (2026-08-13) repose entièrement là-dessus : une
# install française qui bascule en anglais reste posée sur un TAG `-fr`, donc la
# déduction la renverrait dans l'arbre français à la mise à jour suivante.
git -C "$ENGINE" checkout -q v1.17.0-fr
printf '' > "$STATE/tag-family"                 # enregistré : la famille nue
check_enregistre() {  # check_enregistre <libellé> <attendu>
  local got; got="$(latest_tag)"
  if [ "$got" = "$2" ]; then
    echo "  ✅ $1 → $got"
  else
    echo "  ❌ $1 → obtenu '$got', attendu '$2'"
    FAILS=$((FAILS + 1))
  fi
}
check_enregistre "tag -fr + anglais enregistré → anglais" v1.18.0
rm -f "$STATE/tag-family"
check_enregistre "fichier retiré → retour à la déduction" v1.18.0-fr

echo "▸ un dépôt sans aucun tag ne plante pas"
git -C "$ENGINE" tag -d $(git -C "$ENGINE" tag) >/dev/null 2>&1
if out="$(latest_tag)" && [ -z "$out" ]; then
  echo "  ✅ résultat vide, sortie 0"
else
  echo "  ❌ a planté ou renvoyé '$out' alors qu'aucun tag n'existe"
  FAILS=$((FAILS + 1))
fi

echo
if [ "$FAILS" -eq 0 ]; then
  echo "✅ la mise à jour garde chaque installation dans sa langue"
  exit 0
fi
echo "❌ $FAILS échec(s) — une mise à jour pourrait changer la langue d'un utilisateur"
exit 1
