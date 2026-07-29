# `skills/` — trois qui pilotent l'outil, aucun qui porte du savoir

Il y a ici deux sortes de skills, et c'est pour empêcher de les confondre que
ce fichier existe.

**Les skills qui pilotent C Brain** — `recall`, `distill`, `doctor` — sont
livrés avec lui. Ils sont la surface du produit, exactement la même catégorie
que la commande `brain` : ils manœuvrent l'outil et ne savent rien de toi. Sans
eux, installer le plugin donne à l'utilisateur des hooks qu'il ne voit pas et
aucune commande qu'il puisse taper.

**Les skills qui portent une méthode de travail** ne sont livrés avec rien, par
décision explicite. C'est de ça que parle la suite de ce fichier.

Un skill encode une méthode de travail : il cite tes clients, tes projets, ton
cadre, tes exemples de dosage. C'est ce qui le rend bon chez son auteur, et
inutilisable — voire indiscret — chez quelqu'un d'autre. Vérification faite sur
le jeu de skills d'origine : **20 sur 20** contenaient des marqueurs personnels.
Aucun n'était transférable tel quel.

Ce qui se transmet, ce n'est pas le skill. C'est **le standard qui le fabrique**.

**Forge tes skills dans `~/.claude/skills/`** — c'est le dossier que Claude
Code lit, et il t'appartient plutôt qu'à un outil.

> ⚠ Une version précédente de ce fichier disait « l'installeur y branche ce
> dossier ». C'est faux, et ça l'a toujours été : `install.sh` ne contient
> aucune référence à `skills/`. Qui suivait cette phrase forgeait ses skills
> dans le moteur, où rien ne les lit — ni erreur, ni avertissement, juste un
> skill qui ne se déclenche jamais. L'instruction est corrigée plus haut plutôt
> qu'effacée, parce que ce no-op silencieux est le mode de panne que ce projet
> doit sans cesse renommer.

---

## Le standard maison

Tout skill doit atteindre ces neuf points. En dessous, c'est un mémo générique,
pas un skill — et un mémo générique se déclenche mal et ne produit rien de bon.

| # | Exigence | Pourquoi |
|---|---|---|
| 1 | **Recherche best-in-class**, année courante | Un skill écrit de mémoire fige l'état de l'art d'il y a deux ans. |
| 2 | **Leçons transformées en règles exécutables** | « Attention aux caches » ne sert à rien ; « purge le SW avant de conclure » si. |
| 3 | **Direction artistique nommée** (si sortie visuelle) | Sans direction choisie, la sortie tombe dans le générique par défaut. |
| 4 | **Méthode ordonnée**, étapes non sautables | L'ordre *est* la compétence : anonymiser avant de contrôler, pas l'inverse. |
| 5 | **Standards chiffrés** | « plus rapide » est invérifiable ; « < 200 ms p95 » se prouve. |
| 6 | **Definition of Done auto-vérifiable** | Une case à cocher qu'on ne peut pas cocher de bonne foi sans avoir exécuté. |
| 7 | **Anti-patterns** explicites | Nommer ce qu'on refuse évite d'y revenir à chaque fois. |
| 8 | **Références sourcées** | Le lecteur doit pouvoir remonter à la source et te contredire. |
| 9 | **Description riche en déclencheurs ET exclusions** | C'est elle qui décide de l'auto-invocation. Sans exclusions, deux skills se marchent dessus. |

### Deux règles permanentes

1. **Tout nouveau skill passe par la forge** — la recette ci-dessus, appliquée
   intégralement. Pas de skill improvisé.
2. **Forge-sur-blocage** — une tâche qui réclame une compétence que ni tes skills
   ni tes ressources locales ne couvrent ne se bricole pas : on forge le meilleur
   skill possible pour ce besoin. Combler le trou une fois sert tous les projets
   suivants.

### La frontière skill / agent

C'est la distinction qui évite de tout empiler au même endroit :

- **Système autonome, trait permanent → agent.** Il tourne en tâche de fond, sans
  déclenchement, et il a des pouvoirs séparés. Les agents de C Brain vivent dans
  `agents/`.
- **Action ponctuelle, à la demande → skill.** Il s'invoque, il produit, il rend
  la main.

Repackager un agent en skill lui fait perdre son autonomie et la séparation des
pouvoirs. C'est une régression, pas une simplification.

### Déclenchement

Auto par description en défaut. Réserve les hooks déterministes aux skills
**critiques** — ceux dont l'oubli coûte cher (garde-fou d'écriture en production,
checklist de déploiement). Partout ailleurs, la description suffit.

---

## Écrire ton premier skill

```
~/.claude/skills/<nom>/SKILL.md
```

En-tête minimal, puis la méthode :

```markdown
---
name: <nom>
description: <ce que ça fait · QUAND le déclencher · quand NE PAS le déclencher>
---

# /<nom> — <la promesse en une ligne>

## Méthode (ordonnée, sans étape sautable)
1. …

## Standards encodés
- …

## Definition of Done
- [ ] …

## Anti-patterns
- …

## Références
- …
```

La `description` est la partie qui demande le plus de soin : c'est le seul
élément que Claude lit pour décider d'invoquer le skill ou non. Écris-y les mots
que *tu* emploieras réellement, et dis explicitement ce qui relève d'un autre
skill.
