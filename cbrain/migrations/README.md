# Migrations

Un script par changement qui demande une adaptation chez l'utilisateur déjà
installé. Nommés `001-quelque-chose.sh`, joués **dans l'ordre**, **une seule
fois** (le journal est `~/.c-brain/state/migrations-appliquees.txt`).

## Les trois règles

1. **Jamais destructif sur le contenu.** `lessons/`, `projects/`, `meta/`,
   `life/`, `sessions/` ne se modifient pas ici. Une migration touche à
   l'installation, pas à la connaissance de quelqu'un.
2. **Idempotent quand même.** Le journal peut être perdu (restauration,
   nouvelle machine). Rejouer une migration ne doit rien casser.
3. **Échec = arrêt.** Un `exit != 0` interrompt la mise à jour et laisse
   `brain update --rollback` faire son travail. Mieux vaut s'arrêter net
   qu'avancer à moitié.

## Gabarit

```bash
#!/usr/bin/env bash
# 001-exemple.sh — <ce que ça adapte, et pourquoi c'était nécessaire>
set -euo pipefail

TRUNK="$HOME/claude-brain"

# Vérifier AVANT d'agir : c'est ce qui rend le rejeu inoffensif.
if [ -f "$TRUNK/state/vieux-fichier.json" ]; then
  mv "$TRUNK/state/vieux-fichier.json" "$TRUNK/state/nouveau-fichier.json"
  echo "  état renommé"
else
  echo "  rien à faire"
fi
```

Aucune migration à ce jour — le dossier attend la première vraie rupture.
