#!/usr/bin/env bash
# install.sh — installe C Brain. Point d'entrée UNIQUE.
#
# Trois promesses, tenues par construction :
#   · IDEMPOTENT — relancer ne casse rien et ne duplique rien.
#   · NON DESTRUCTIF — tout ce qui existe déjà est sauvegardé avant d'être touché.
#   · RÉVERSIBLE — chaque geste est journalisé ; ./uninstall.sh les défait.
#
# Disposition installée :
#   ~/.c-brain/engine  → lien vers CE dépôt (le MOTEUR : du code, rien d'autre)
#   ~/.c-brain/trunk     → TON tronc (tes fiches). Jamais écrasé, jamais mis à jour.
#
# Usage : ./install.sh [--no-launchd] [--no-capsule] [--dry-run]
set -euo pipefail

ENGINE="$(cd "$(dirname "$0")" && pwd -P)"
TRUNK="$HOME/.c-brain/trunk"
CB="$HOME/.c-brain"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUPS="$CB/backups/$TS"
MANIFEST="$CB/manifest.txt"

DO_LAUNCHD=1; DO_CAPSULE=1; DRY=0
for a in "$@"; do
  case "$a" in
    --no-launchd) DO_LAUNCHD=0 ;;
    --no-capsule) DO_CAPSULE=0 ;;
    --dry-run)    DRY=1 ;;
    *) echo "Option inconnue : $a"; exit 1 ;;
  esac
done

say()  { echo "  $*"; }
step() { echo; echo "▸ $*"; }
warn() { echo "  ⚠️  $*"; }
die()  { echo; echo "❌ $*"; exit 1; }

# Journalise ce qu'on crée, pour que la désinstallation sache quoi défaire.
note() { [ "$DRY" = "1" ] || { mkdir -p "$CB"; echo "$1|$2" >> "$MANIFEST"; }; }

# Sauvegarde avant d'écraser. Le contenu de l'utilisateur ne disparaît jamais.
save() {
  [ -e "$1" ] || return 0
  [ "$DRY" = "1" ] && { say "(dry-run) sauvegarderait $1"; return 0; }
  mkdir -p "$BACKUPS"
  cp -R "$1" "$BACKUPS/$(basename "$1")" 2>/dev/null || true
  say "sauvegardé : $1 → $BACKUPS/"
}

run() { [ "$DRY" = "1" ] && { say "(dry-run) $*"; return 0; }; "$@"; }

# Pose un lien symbolique de façon idempotente : déjà bon → on ne touche à rien.
link() {  # link <cible> <lien>
  local target="$1" path="$2"
  if [ -L "$path" ] && [ "$(readlink "$path")" = "$target" ]; then
    say "= $path (déjà relié)"; return 0
  fi
  if [ -e "$path" ] || [ -L "$path" ]; then
    save "$path"
    run rm -rf "$path"
  fi
  run mkdir -p "$(dirname "$path")"
  run ln -s "$target" "$path"
  note link "$path"
  say "+ $path → $target"
}

echo "🧠 C Brain — installation"
echo "   moteur : $ENGINE"
echo "   tronc  : $TRUNK"
[ "$DRY" = "1" ] && echo "   (DRY-RUN : rien ne sera écrit)"

# ─── 0. Préalables ────────────────────────────────────────────────────────
step "Préalables"
[ "$(uname)" = "Darwin" ] || die "C Brain vise macOS (launchd, Electron, \`open\`)."
command -v python3 >/dev/null || die "python3 est requis (il fait tourner tous les hooks)."
say "python3 $(python3 -c 'import sys;print(".".join(map(str,sys.version_info[:3])))')"
command -v git >/dev/null || warn "git absent — \`brain update\` ne pourra pas tirer les mises à jour."

HAS_CLAUDE_CODE=0
[ -d "$HOME/.claude" ] && HAS_CLAUDE_CODE=1
if [ "$HAS_CLAUDE_CODE" = "0" ]; then
  warn "~/.claude absent : Claude Code ne semble pas installé."
  warn "C Brain s'installera quand même, mais SANS boucle automatique :"
  warn "les hooks (rappel, archivage, maintenance) sont propres à Claude Code."
  warn "Tu garderas la CLI \`brain\`, les agents, la planète et la capsule."
fi

# ─── 1. Racine C Brain ────────────────────────────────────────────────────
step "Racine C Brain (~/.c-brain)"
run mkdir -p "$CB"
link "$ENGINE" "$CB/engine"
[ "$DRY" = "1" ] || { git -C "$ENGINE" describe --tags --always 2>/dev/null > "$CB/VERSION" || echo "sans-tag" > "$CB/VERSION"; }
say "version : $(cat "$CB/VERSION" 2>/dev/null || echo '?')"

# ─── 2. Le tronc ──────────────────────────────────────────────────────────
step "Tronc (~/.c-brain/trunk)"
if [ -d "$TRUNK" ]; then
  # Un tronc existe. S'il contient un VRAI dossier hooks/ (pas un lien), c'est
  # une installation antérieure autonome : on refuse de la démolir en silence.
  if [ -d "$TRUNK/hooks" ] && [ ! -L "$TRUNK/hooks" ]; then
    die "$TRUNK/hooks est un dossier RÉEL, pas un lien.
   Il y a déjà un Brain installé « à l'ancienne » ici. Je ne le remplace pas tout seul :
   ses fichiers pourraient être les tiens. Sauvegarde-le, puis relance :
     mv $TRUNK $TRUNK.avant-c-brain && ./install.sh"
  fi
  say "= tronc existant conservé (tes fiches ne sont pas touchées)"
else
  run mkdir -p "$TRUNK"
  run cp -R "$ENGINE/skeleton/." "$TRUNK/"
  note dir "$TRUNK"
  say "+ tronc créé depuis skeleton/ (vide, prêt à grandir)"
fi
run mkdir -p "$TRUNK/state" "$TRUNK/sessions/archive"

# ─── 3. Le moteur, relié dans le tronc ────────────────────────────────────
step "Moteur relié au tronc"
for d in hooks agents capsule planet companion tests; do
  link "$CB/engine/$d" "$TRUNK/$d"
done

# ─── 4. La commande `brain` ───────────────────────────────────────────────
step "Commande \`brain\`"
link "$CB/engine/brain" "$HOME/.local/bin/brain"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) say "~/.local/bin est dans le PATH" ;;
  *) warn "~/.local/bin n'est PAS dans ton PATH. Ajoute à ton ~/.zshrc :"
     warn "  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# ─── 5. Agents visibles par Claude Code ───────────────────────────────────
# Le piège nº1 : sans ce lien, les agents existent mais Claude Code ne les voit
# pas. Aucune erreur, juste une boucle autonome qui tourne à vide.
step "Agents visibles par l'agent CLI"
if [ "$HAS_CLAUDE_CODE" = "1" ]; then
  link "$TRUNK/agents" "$HOME/.claude/agents"
else
  say "(sauté — ~/.claude absent)"
fi

# ─── 6. Hooks + statusline ────────────────────────────────────────────────
step "Branchement des hooks"
if [ "$HAS_CLAUDE_CODE" = "1" ]; then
  if [ "$DRY" = "1" ]; then say "(dry-run) fusionnerait ~/.claude/settings.json"
  else
    # Pas de `save` ici : merge_settings.py ne sauvegarde QUE s'il écrit vraiment.
    # Sauvegarder à chaque passe empilerait une copie inutile à chaque relance.
    python3 "$ENGINE/merge_settings.py" install
    note settings "$HOME/.claude/settings.json"
  fi
  if [ -f "$ENGINE/statusline.py" ]; then
    save "$HOME/.claude/statusline.py"
    run cp "$ENGINE/statusline.py" "$HOME/.claude/statusline.py"
    note file "$HOME/.claude/statusline.py"
    say "+ statusline installée"
  fi
else
  say "(sauté — pas de Claude Code : C Brain fonctionnera à la demande)"
fi

# ─── 7. Capsule ───────────────────────────────────────────────────────────
step "Capsule (fenêtre Electron)"
capsule_ok() {  # Electron répond-il VRAIMENT ?
  local bin="$ENGINE/capsule/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
  [ -x "$bin" ] && "$bin" --version >/dev/null 2>&1
}

if [ "$DO_CAPSULE" = "0" ]; then say "(sauté — --no-capsule)"
elif ! command -v npm >/dev/null; then warn "npm absent — capsule non installée (le reste marche)."
elif [ "$DRY" = "1" ]; then say "(dry-run) installerait les dépendances de la capsule"
elif capsule_ok; then say "= capsule déjà opérationnelle"
else
  say "npm install (Electron, ~1 min)…"
  npm --prefix "$ENGINE/capsule" install --silent >/dev/null 2>&1 || true
  # `npm install` sort en SUCCÈS même quand le binaire Electron n'a pas été
  # extrait (archive tronquée par @electron/get — piège déjà rencontré). Se fier
  # au code de retour donnerait une capsule annoncée installée et incapable de
  # démarrer. On vérifie le binaire lui-même.
  if capsule_ok; then
    say "+ capsule opérationnelle ($("$ENGINE/capsule/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron" --version 2>/dev/null))"
  else
    warn "npm a rendu la main, mais le binaire Electron ne répond pas."
    warn "C'est un défaut connu de son téléchargeur, pas de C Brain. Remède :"
    warn "  rm -rf $ENGINE/capsule/node_modules/electron && npm --prefix $ENGINE/capsule install"
    warn "Tout le reste de C Brain fonctionne sans la capsule."
  fi
fi

# ─── 8. Tâches planifiées ─────────────────────────────────────────────────
step "Tâches planifiées (launchd)"
if [ "$DO_LAUNCHD" = "0" ]; then say "(sauté — --no-launchd)"
else
  run mkdir -p "$HOME/Library/LaunchAgents"
  for t in resume machiniste; do
    tpl="$ENGINE/hooks/com.claudebrain.$t.plist.template"
    [ -f "$tpl" ] || continue
    out="$HOME/Library/LaunchAgents/com.claudebrain.$t.plist"
    if [ "$DRY" = "1" ]; then say "(dry-run) générerait $out"; continue; fi
    # __HOME__ substitué ici : un chemin en dur dans un .plist est LE bug qui
    # casse silencieusement une installation sur une autre machine.
    sed "s|__HOME__|$HOME|g" "$tpl" > "$out"
    note file "$out"
    launchctl unload "$out" 2>/dev/null || true
    launchctl load "$out" 2>/dev/null && say "+ com.claudebrain.$t chargé" \
      || warn "com.claudebrain.$t généré mais non chargé (launchctl a refusé)"
  done
fi

# ─── 9. Lanceur de la planète ─────────────────────────────────────────────
step "Lanceur de la planète (Bureau)"
CMD="$HOME/Desktop/Planete-C-Brain.command"
if [ "$DRY" = "1" ]; then say "(dry-run) créerait $CMD"
elif [ -d "$HOME/Desktop" ]; then
  printf '#!/bin/bash\nexport PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"\nexec "%s/planet/launch.sh"\n' "$TRUNK" > "$CMD"
  chmod +x "$CMD"
  note file "$CMD"
  say "+ $CMD (double-clic → globe sur localhost:8765)"
else
  warn "~/Desktop introuvable — lanceur non créé. La planète reste accessible :"
  warn "  $TRUNK/planet/launch.sh"
fi

# ─── 10. Vérification ─────────────────────────────────────────────────────
step "Vérification"
if [ "$DRY" = "1" ]; then say "(dry-run) lancerait le selftest"
else
  if bash "$TRUNK/hooks/selftest.sh" >/tmp/c-brain-selftest.log 2>&1; then
    say "✅ selftest OK — tous les hooks sains"
  else
    warn "selftest en échec — détail : /tmp/c-brain-selftest.log"
    tail -5 /tmp/c-brain-selftest.log | sed 's/^/     /'
  fi
  python3 "$TRUNK/hooks/brain_doctor.py" --quiet >/dev/null 2>&1 \
    && say "✅ doctor — arbre cohérent" || say "ℹ️  doctor signale des points à voir (\`brain doctor\`)"
fi

echo
echo "✅ C Brain installé."
echo
echo "   brain status     où en est le tronc"
echo "   brain recall <q> chercher dans ta mémoire"
echo "   brain doctor     santé de l'arbre"
echo "   brain selftest   revérifier l'installation"
echo
[ "$HAS_CLAUDE_CODE" = "1" ] \
  && echo "   Redémarre ta session CLI pour que les hooks prennent effet." \
  || echo "   Sans Claude Code : pas de boucle automatique, mais toute la CLI est là."
echo "   Désinstallation : $ENGINE/uninstall.sh"
