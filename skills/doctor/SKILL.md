---
description: Contrôler la santé de l'installation C Brain et du tronc — liens morts, fiches non indexées, hooks cassés, état périmé. À déclencher quand le rappel semble ne rien renvoyer, quand les fiches ne se sauvegardent plus, quand l'utilisateur dit que C Brain « ne marche pas », ou avant de faire confiance au tronc pour quelque chose d'important.
---

# Contrôler le tronc et le câblage

Deux commandes, et elles répondent à des questions différentes. Lance les deux.

```bash
brain selftest    # le MOTEUR est-il bien câblé ? (hooks, liens, permissions)
brain doctor      # le TRONC est-il cohérent ? (liens [[...]] morts, orphelines, index)
```

## Lire le résultat

- **selftest rouge** → le problème est l'installation. Relance `install.sh` : il
  est idempotent et répare son propre câblage.
- **doctor rouge** → le problème est dans les fiches. Les liens `[[...]]` morts
  et les fiches absentes de `MEMORY.md` sont les deux qui coûtent au rappel.
- **Les deux verts mais le rappel ne renvoie rien** → c'est la requête, pas la
  machinerie. Essaie des termes plus étroits : le classement est lexical, il
  matche des mots, pas du sens.

## Ce qu'il ne faut pas conclure

Un hook silencieux n'est pas un hook sain. Si les fiches ne se sauvegardent pas
alors que les deux commandes sont vertes, vérifie que les hooks sont bien
enregistrés : un hook dont le chemin ne résout plus n'échoue pas bruyamment, il
arrête simplement d'enregistrer.
