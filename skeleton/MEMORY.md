# 🌳 Mon tronc de connaissance

> **Index chargé au démarrage de chaque session.** Ce fichier est la carte de
> l'arbre — une ligne par fiche, jamais le contenu des fiches. Une fiche écrite
> en session atterrit ici, puis le jardinier la range et tisse ses liens.

Ce tronc est **vide** : c'est le tien. Il grandit avec le travail, pas avant.

## Organisation

- **`lessons/`** — leçons transverses. Le vrai or : ce qu'un projet t'a appris et
  qui servira aux autres. Une leçon = un piège compris une fois, jamais deux.
- **`projects/<projet>/`** — un dossier par projet : contexte distillé, décisions,
  points de reprise.
- **`meta/`** — ta façon de travailler : conventions, standards, méthode.
- **`life/`** — hors-code : objectifs, contraintes, situation personnelle.
- **`sessions/`** — archive brute des sessions. Couche froide, sans perte.
- **`state/`** — état interne des hooks et des agents. Pas de la connaissance.

## Format d'une fiche

```markdown
---
name: mon-piege-appris
description: <une ligne — c'est elle qui décide si la fiche remonte au rappel>
metadata:
  type: lesson
---

Le fait, court et vérifiable.

**Pourquoi :** ce qui le rend non évident.
**Comment l'appliquer :** la règle exécutable qui en découle.

Relié à [[une-autre-fiche]].
```

- Les liens `[[nom-de-fiche]]` construisent le graphe. Lie généreusement : un lien
  vers une fiche qui n'existe pas encore n'est pas une erreur, c'est une note
  de ce qu'il reste à écrire.
- La `description` est ce que le rappel lit pour juger la pertinence. Soigne-la
  plus que le titre.

## Index

*(vide — tes premières fiches apparaîtront ici)*
