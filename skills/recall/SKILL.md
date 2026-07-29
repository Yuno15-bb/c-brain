---
description: Chercher dans le tronc C Brain les fiches pertinentes sur un sujet, et lire celles qui comptent. À déclencher quand l'utilisateur demande ce qu'il sait déjà sur quelque chose, veut retrouver une décision passée, dit « on avait déjà résolu ça ? », « qu'est-ce que j'ai sur X », « regarde mes fiches », ou quand une tâche sent le problème déjà tranché une fois.
---

# Rappeler ce que le tronc sait déjà

Retrouver ce qui est connu avant de le re-résoudre.

## Comment

Lance le rappel, top 5, et lis ce qui remonte :

```bash
brain recall "$ARGUMENTS"
```

Si `brain` n'est pas sur le PATH, le plugin l'embarque — appelle-le directement :
`"${CLAUDE_PLUGIN_ROOT}/bin/brain" recall "$ARGUMENTS"`.

Chaque résultat donne un score, un nom de fiche et un chemin relatif au tronc
(`~/.c-brain/trunk`). **Ouvre celles qui dépassent le bruit et lis-les vraiment** —
le classement est lexical : il dit où regarder, jamais ce qui est vrai.

## Ensuite

- Dis ce que les fiches établissent, et cite chacune par son chemin pour qu'on
  puisse te contredire.
- Dis franchement quand rien de pertinent n'est remonté. Une réponse assurée
  assemblée depuis trois fiches faiblement pertinentes est pire que « le tronc
  n'a rien là-dessus » — la première ressemble à de la mémoire et n'en est pas.
- N'écris jamais dans une fiche comme effet de bord d'une lecture.

## Échelle

Le rappel tient bien jusqu'à environ mille fiches et se dégrade au-delà
(`tests/recall_benchmark.py` publie les chiffres). Sur un gros tronc, préfère
plusieurs requêtes étroites à une seule large.
