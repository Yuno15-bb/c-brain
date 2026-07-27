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

TRUNK="$HOME/.c-brain/trunk"

# Vérifier AVANT d'agir : c'est ce qui rend le rejeu inoffensif.
if [ -f "$TRUNK/state/vieux-fichier.json" ]; then
  mv "$TRUNK/state/vieux-fichier.json" "$TRUNK/state/nouveau-fichier.json"
  echo "  état renommé"
else
  echo "  rien à faire"
fi
```

## Migrations écrites

| # | Script | Ce qu'elle adapte |
|---|---|---|
| 001 | `001-rename-user-dir.sh` | `~/claude-brain` → `~/.c-brain/trunk`, plus un lien de compatibilité à l'ancien emplacement. |

**001 en deux mots.** Le dossier utilisateur portait une marque Anthropic dans
un produit public, et faisait un quatrième nom pour une seule chose. Après :
une racine unique, `~/.c-brain`, moteur et tronc côte à côte.

Elle ne fait que **déplacer**. Le recâblage (liens du moteur, `settings.json`,
plists launchd, lanceur du Bureau) est refait juste derrière par `install.sh`,
que `update.sh` appelle de toute façon. Une migration qui recâblerait aussi
dupliquerait cette logique — et les deux copies divergeraient.

Le lien de compatibilité reste en place **définitivement**. Il ne sert plus à
C Brain, mais à tout ce que C Brain ne connaît pas : le lien mémoire de l'agent
CLI, les scripts personnels, un chemin noté quelque part.
