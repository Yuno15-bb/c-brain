---
description: Transformer ce qui vient d'être compris en fiche C Brain — rangée dans la bonne zone, reliée à ce qui s'y rattache, indexée. À déclencher quand l'utilisateur dit « retiens ça », « note-le », « garde cette leçon », « distille la session », ou quand un problème non trivial vient d'être résolu et que le raisonnement serait sinon perdu.
---

# Distiller en fiche

Une session se termine et son raisonnement part avec elle, sauf si quelque
chose est écrit. Ceci l'écrit, dans la forme que le tronc attend.

## Ce qui mérite une fiche

Seulement ce qu'un lecteur futur ne pourrait pas re-déduire à bon compte :

- un défaut et **comment il a été trouvé**, pas seulement le correctif ;
- une décision, ses alternatives, et pourquoi elles ont perdu ;
- une contrainte qui ne se voit pas dans le code.

Pas : ce que le dépôt consigne déjà, ce qui ne vaut que pour cette
conversation, ni un résumé d'un travail lisible dans le diff.

## Forme

Un fait par fichier, dans `~/.c-brain/trunk/<zone>/<slug>.md` où la zone est
`lessons` (inter-projets), `projects/<nom>`, `meta` (façons de travailler) ou
`life`.

```markdown
---
name: <slug-court-en-kebab-case>
description: <une ligne — c'est là-dessus que le rappel classe, donc qu'elle DISE le fait>
metadata:
  type: reference
---

<le fait, énoncé pour être utile sans cette conversation>

Why: <ce qui le rend non évident>

How to apply: <le réflexe qu'il doit produire la prochaine fois>
```

Relie les fiches voisines par `[[leur-slug]]`. Relie généreusement — un lien
vers une fiche qui n'existe pas encore marque quelque chose à écrire, pas une
erreur.

## Ensuite

- Ajoute une ligne dans `MEMORY.md` : `- [Titre](chemin.md) — accroche`.
- **Vérifie d'abord qu'une fiche ne couvre pas déjà le sujet** et mets celle-là
  à jour. Deux fiches sur un même sujet, c'est ainsi qu'un tronc se met à mentir.
- Convertis les dates relatives en dates absolues. « Mardi dernier » pourrit.
