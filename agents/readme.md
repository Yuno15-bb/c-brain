---
name: readme
description: Guide des 8 agents du système (distillateur, jardinier, architecte, challenger, synthétiseur, archiviste, mécanicien, machiniste) — rôles, lancement, seuils autonomes
metadata:
  type: reference
---

# 🤖 Agents du Claude Brain

Sous-agents Claude Code natifs qui entretiennent et nourrissent le tronc. Fichiers canoniques **versionnés ici** ; symlinkés dans `~/.claude/agents/` pour la découverte par Claude Code.

## Les agents

- **[distillateur](distillateur.md)** — crée le savoir : transforme les sessions brutes (`sessions/archive/`, transcripts) en fiches/leçons propres, ou met à jour l'existant. *Ne range pas l'arbre globalement* (c'est le jardinier).
- **[jardinier](jardinier.md)** — range l'arbre : déduplique, garantit que chaque fiche est dans `MEMORY.md`, tisse/répare les liens `[[...]]` **évidents**, masque les secrets, traite cohérence/utilité. *Ne crée pas de savoir.*
- **[architecte](architecte.md)** — cohésion **globale** : lit toute la topologie du graphe (`hooks/brain_topology.py`) pour tisser les liens **manquants**, relier les fiches isolées, raccrocher les îlots détachés, privilégier les ponts inter-domaines. *Vue d'ensemble, là où le jardinier range fiche par fiche.*
- **[challenger](challenger.md)** — met le savoir à l'épreuve : traque le périmé, le faux, le contredit, le survendu ; produit des doutes étayés (`state/challenges.json`). *Ne corrige rien — il doute.*
- **[synthetiseur](synthetiseur.md)** — savoir de second ordre : relie un thème transverse à travers plusieurs projets en un essai dense (`lessons/`). *Crée la vision d'ensemble qu'aucune fiche ne dit seule.*
- **[archiviste](archiviste.md)** — gère le froid : fraîcheur, péremption, archivage du poids mort (via `state/utility.json`). *Propose, ne supprime jamais.*
- **[mécanicien](mecanicien.md)** — répare l'infra machine : hooks, câblage, symlinks, capsule. *Jamais le contenu des fiches.*

> **Les 7 rôles = une équipe (séparation des pouvoirs).** Le distillateur *écrit*, le jardinier *range* (local), l'architecte *relie* (global), le challenger *doute*, le synthétiseur *synthétise*, l'archiviste *élague*, le mécanicien *répare l'infra*. Aucun ne fait le travail d'un autre — c'est ce qui garde le système sûr et auditable.

## Comment les lancer

Dans n'importe quelle session Claude Code, en langage naturel :
- « **lance le distillateur** sur ma dernière session » → capture ce qui mérite de rester.
- « **lance le jardinier** » → nettoie et range l'arbre.

Ou en les nommant explicitement comme sous-agents. Flux type après une grosse session :
1. `distillateur` extrait les fiches de la session,
2. `jardinier` vérifie qu'elles sont bien rangées, liées, et dans la carte.

## Réinstaller les symlinks (autre machine / après git clone)

```bash
mkdir -p ~/.claude/agents
# symlinke TOUS les agents (sinon les non-listés restent muets après un git clone)
for a in ~/claude-brain/agents/*.md; do
  [ "$(basename "$a")" = "readme.md" ] && continue
  ln -sf "$a" ~/.claude/agents/"$(basename "$a")"
done
```

## Évolutions possibles

- Régler `model:` (sonnet par défaut pour le coût ; passer à opus pour un jardinage/distillation plus fin).
- ~~Un agent « tisseur » dédié aux liens inter-projets~~ → **fait** : c'est l'[architecte](architecte.md) (2026-06-24).
- ~~Brancher l'architecte dans l'orchestrateur autonome pour une veille de cohésion périodique~~ → **fait** : `hooks/brain_upkeep.py` (2026-06-24).

## Seconde couche autonome — la veille de cohésion

Au-delà du duo SessionEnd `distillateur → jardinier`, une **seconde couche** entretient le tronc toute seule via `hooks/brain_upkeep.py`, appelé en fin de chaque maintenance :

1. **régénère les capteurs mécaniques** (gratuits, zéro LLM) : `brain_topology.py`, `brain_utility.py` (+ `coherence.json` accumulé) ;
2. chaque agent de veille n'est **éligible** que si **son capteur dépasse un seuil** (vrai travail) **et** que son **cooldown** (12 h) est respecté ;
3. on réveille **au plus UN agent par passage** (garantie de coût : ~1 run LLM en plus, seulement quand il y a matière), par priorité **challenger → architecte → archiviste → mécanicien** (`brain_upkeep.ORDER`).

Seuils : architecte (≥1 isolée OU ≥3 placements douteux OU ≥2 composantes OU ≥8 liens manquants) · challenger (≥1 **paire `(a,b)`** à arbitrer dans `coherence.json` — les notes d'arbitrage ne comptent pas) · archiviste (≥3 fiches en poids mort) · **mécanicien (≥1 défaut dans `doctor.json`)**. Sur la durée, toutes les dimensions finissent tendues à tour de rôle. Best-effort : si un agent de veille échoue (quota/login), la passe est sautée — aucune donnée perdue (≠ distillation). Debug à sec : `python3 hooks/brain_upkeep.py decide`.

> ⚠️ **Le mécanicien (`mecanicien`) EST branché en autonome** (depuis 2026-06-24, 1 réveil à ce jour). Il tourne en `sonnet` avec `--dangerously-skip-permissions` et les outils `Edit/Write/Bash` : il peut donc **modifier l'infra tout seul** quand `brain_doctor` signale un défaut. Sa mission (`brain_upkeep.TASKS`) le borne aux défauts listés par le docteur et lui interdit de toucher hooks/settings/symlinks sauf pointage explicite. C'est le seul agent de veille dont une passe ratée n'est pas rejouable à l'identique — le surveiller via `sessions/gardening.log`.

Reste optionnel : brancher le **synthétiseur** (pas de capteur — déclenché par densité thématique, pas par défaut).

**Garde mécanique post-jardinage** (zéro LLM) : `auto_maintain` relance `brain_doctor --json` juste après le jardinier et trace `[doctor] … post-jardinage: N defaut(s)` dans `sessions/gardening.log` si `N != 0`. Le jardinier ne peut plus être seul juge de sa propre passe.

**Invariants** : `python3 tests/invariants_brain.py` — capteurs qui redescendent, tolérance aux entrées legacy, doc↔code, modèle par agent. Lancé par `hooks/selftest.sh`.
