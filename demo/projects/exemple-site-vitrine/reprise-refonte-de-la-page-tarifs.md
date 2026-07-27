---
name: reprise-refonte-de-la-page-tarifs
description: Point de reprise d'un chantier en cours — où on en est, ce qui est tranché, la prochaine action. Si tu reprends un projet après une coupure et que tu ne sais plus où tu en étais.
metadata:
  type: project
  demo: true
---

Exemple d'une fiche de **point de reprise** : celle qu'on relit en premier
quand on rouvre un projet trois semaines plus tard.

**État au 12 mars.** Nouvelle grille tarifaire en ligne sur la préproduction.
Les trois formules s'affichent, le comparatif tient sur mobile.

**Tranché — ne pas rouvrir.** Trois formules, pas quatre : la quatrième faisait
hésiter au lieu de rassurer. Prix affichés hors taxes, comme le reste du site.

**Ce qui reste.**

| # | À faire | Effort |
|---|---|---|
| 1 | Brancher le bouton « Nous contacter » sur le vrai formulaire | 30 min |
| 2 | Relire les mentions légales avec le comptable | à planifier |
| 3 | Passer en production | 15 min, après 1 et 2 |

**Piège rencontré.** Le comparatif paraissait cassé sur téléphone alors que le
CSS était juste : c'était une version en cache — voir
[[le-cache-ment-apres-un-deploiement]].

**Prochaine action concrète :** l'item 1. Tout le reste en dépend.

**Pourquoi cette fiche existe :** une reprise coûte cher parce qu'on redécide
des choses déjà décidées. Écrire ce qui est **fermé** vaut autant qu'écrire ce
qui reste.

Relié à [[comment-ce-tronc-fonctionne]].

> Fiche de démonstration, installée par `brain demo`. `brain demo --remove` la
> retire.
