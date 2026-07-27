---
name: le-cache-ment-apres-un-deploiement
description: Un déploiement annoncé « réussi » peut servir l'ancienne version — vérifier l'artefact servi, jamais le statut du build. Si un correctif « ne marche pas » alors que le code est bon.
metadata:
  type: lesson
  demo: true
---

Un tableau de bord qui affiche **SUCCESS** ne prouve qu'une chose : le build
s'est terminé. Il ne prouve pas que le nouveau code est celui qu'on te sert.

Entre les deux, il y a un cache d'images, un CDN, un service worker — chacun
capable de rendre l'ancienne version pendant des heures, sans erreur nulle part.

**Pourquoi :** le symptôme est trompeur au point d'envoyer chercher le bug dans
le code. On relit un correctif juste, on le réécrit, on doute de soi — alors
que le correctif n'a jamais été exécuté une seule fois.

**Comment l'appliquer :** ne jamais conclure sur le statut du build. Poser un
marqueur vérifiable dans l'artefact (numéro de version, date de build) et le
**lire depuis l'extérieur** avant de dire que c'est en ligne. Si le marqueur est
l'ancien, le problème n'est pas ton code.

Relié à [[comment-ce-tronc-fonctionne]] : c'est le type de fiche qui justifie
tout le reste — un piège compris une fois, jamais deux.

> Fiche de démonstration, installée par `brain demo`. `brain demo --remove` la
> retire. Remplace-la par la tienne dès que tu en as une vraie.
