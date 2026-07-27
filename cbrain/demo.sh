#!/usr/bin/env bash
# demo.sh — trois fiches d'exemple, posées puis retirées à la demande.
#
# POURQUOI. Le point d'abandon nº1 d'un outil de mémoire, c'est le premier
# écran : on installe, on tape `brain status`, on voit du vide, on désinstalle.
# Un tronc vide ne montre ni à quoi ressemble une fiche, ni ce que le rappel
# sait retrouver, ni pourquoi les liens comptent. Ces trois fiches le montrent —
# et s'en vont proprement quand elles ont servi.
#
# Usage :
#   brain demo            pose les fiches
#   brain demo --remove   les retire
#   brain demo --status   dit où elles en sont
set -euo pipefail

ENGINE="${CBRAIN_ENGINE:-$HOME/.c-brain/engine}"
TRUNK="${CBRAIN_TRUNK:-$HOME/.c-brain/trunk}"
SRC="$ENGINE/demo"

# Bornes du bloc d'index. Écrire entre deux bornes plutôt qu'« à la fin » : le
# retrait redevient une opération exacte, même si l'utilisateur a écrit dessous.
BEGIN="<!-- c-brain:demo:début -->"
END="<!-- c-brain:demo:fin -->"

say()  { echo "  $*"; }
warn() { echo "  ⚠️  $*"; }

[ -d "$SRC" ]   || { echo "❌ fiches de démonstration introuvables ($SRC)"; exit 1; }
[ -d "$TRUNK" ] || { echo "❌ tronc introuvable ($TRUNK)"; exit 1; }

# Chemins relatifs des fiches, dérivés du dossier source — jamais listés à la
# main. Une liste en dur se désynchronise du contenu au premier ajout, et le
# retrait laisse alors des orphelines que plus rien ne connaît.
notes() { (cd "$SRC" && find . -name '*.md' | sed 's|^\./||' | sort); }

# Une fiche est-elle restée telle qu'on l'a posée ?
untouched() {  # untouched <chemin relatif>
  cmp -s "$SRC/$1" "$TRUNK/$1"
}

index_block() {
  echo "$BEGIN"
  echo "*(fiches de démonstration — \`brain demo --remove\` pour les retirer)*"
  echo
  while read -r rel; do
    name=$(sed -n 's/^name: *//p' "$SRC/$rel" | head -1)
    desc=$(sed -n 's/^description: *//p' "$SRC/$rel" | head -1 | cut -c1-90)
    echo "- [$name]($rel) — $desc"
  done < <(notes)
  echo "$END"
}

drop_block() {  # retire le bloc de MEMORY.md, s'il y est
  local mem="$TRUNK/MEMORY.md"
  [ -f "$mem" ] || return 0
  python3 - "$mem" "$BEGIN" "$END" <<'PY'
import re, sys
path, begin, end = sys.argv[1:4]
text = open(path, encoding="utf-8").read()
# \n* de part et d'autre : sans ça, chaque pose/retrait laisse une ligne vide
# de plus, et le fichier gonfle d'un blanc à chaque cycle.
new = re.sub(r"\n*" + re.escape(begin) + r".*?" + re.escape(end) + r"\n*",
             "\n", text, flags=re.S)
if new != text:
    open(path, "w", encoding="utf-8").write(new)
PY
}

case "${1:-install}" in

  --status)
    n=0; modified=0
    while read -r rel; do
      if [ -f "$TRUNK/$rel" ]; then
        n=$((n + 1))
        untouched "$rel" || modified=$((modified + 1))
      fi
    done < <(notes)
    if [ "$n" = "0" ]; then
      say "aucune fiche de démonstration posée (\`brain demo\` pour les poser)"
    else
      say "$n fiche(s) de démonstration posée(s)$([ "$modified" -gt 0 ] && echo ", dont $modified modifiée(s) par toi")"
    fi
    ;;

  --remove)
    removed=0; kept=0
    while read -r rel; do
      dst="$TRUNK/$rel"
      [ -f "$dst" ] || continue
      # Une fiche modifiée n'est plus une fiche de démonstration : c'est du
      # travail. On la laisse. Effacer le contenu de quelqu'un « parce qu'on
      # l'avait posé » est exactement ce qu'un outil de mémoire ne fait jamais.
      if untouched "$rel"; then
        rm -f "$dst"
        removed=$((removed + 1))
      else
        warn "gardée (tu l'as modifiée) : $rel"
        kept=$((kept + 1))
      fi
    done < <(notes)
    # Sous-dossiers de projet devenus vides. `-mindepth 1` est obligatoire :
    # sans lui, un tronc dont `projects/` finit vide verrait `projects/`
    # lui-même effacé — on aurait retiré une démonstration en emportant un
    # dossier de la structure.
    find "$TRUNK/projects" -mindepth 1 -type d -empty -delete 2>/dev/null || true
    drop_block
    say "$removed fiche(s) retirée(s)$([ "$kept" -gt 0 ] && echo ", $kept gardée(s)")"
    [ "$kept" = "0" ] && say "l'index est nettoyé — le tronc est à toi"
    ;;

  install|"")
    posed=0; skipped=0
    while read -r rel; do
      dst="$TRUNK/$rel"
      if [ -f "$dst" ] && ! untouched "$rel"; then
        warn "existe déjà et diffère, non écrasée : $rel"
        skipped=$((skipped + 1))
        continue
      fi
      mkdir -p "$(dirname "$dst")"
      cp "$SRC/$rel" "$dst"
      posed=$((posed + 1))
    done < <(notes)

    mem="$TRUNK/MEMORY.md"
    drop_block   # d'abord retirer l'ancien bloc : relancer ne doit pas empiler
    { [ -f "$mem" ] && cat "$mem"; echo; index_block; } > "$mem.tmp" && mv "$mem.tmp" "$mem"

    say "$posed fiche(s) posée(s)$([ "$skipped" -gt 0 ] && echo ", $skipped ignorée(s)")"
    echo
    say "Essaie maintenant :"
    say "  brain recall cache déploiement    ← ce que le rappel retrouve"
    say "  brain status                      ← l'état du tronc"
    say "  brain demo --remove               ← quand tu n'en as plus besoin"
    ;;

  *)
    echo "Usage : brain demo [--remove|--status]"
    exit 1
    ;;
esac
