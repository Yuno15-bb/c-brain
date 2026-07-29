# Contribuer

Merci d'être passé. Ce dépôt a une forme qui ne se devine pas de l'extérieur, et
se tromper dessus coûte un patch refusé — donc c'est écrit ici avant tout le
reste.

## La seule chose à savoir d'abord

**`main` est une traduction. `fr` est la source.**

C Brain est extrait d'un tronc de connaissance réel, personnel et français. La
chaîne va dans un seul sens :

```
le Brain vivant de l'auteur
   │  sync.sh          liste blanche — refuse de tourner ailleurs que sur `fr`
   ▼
ce dépôt, branche `fr`
   │  generalize.py + rules.json     dépersonnalisation
   │  leakcheck.py                   21 marqueurs, bloquant
   ▼
   branche `main`                    traduite, à la main
   ▼
   publish.sh vX.Y.Z "message"       la seule voie autorisée vers un push
```

Ce qui en découle :

- **Sur `fr`, n'édite à la main rien sous `hooks/`, `agents/`, `capsule/`,
  `planet/`, `companion/`, `tests/`, ni le script `brain`.** `sync.sh` écrase
  ces fichiers depuis le Brain de l'auteur à la passe suivante, et ta
  modification disparaît sans laisser de trace. Ça passe par une règle dans
  `rules.json` à la place.
- **Sur `main`, l'édition directe est la bonne voie** — `main` est la
  traduction, elle n'a pas d'amont qui l'écrase.
- **Ouvre ta pull request sur `main`**, sauf si tu corriges spécifiquement la
  branche française.

## Avant d'ouvrir une pull request

```bash
python3 leakcheck.py             # doit être PROPRE — sinon il bloque la publication
python3 tests/plugin_manifest.py # les manifestes de plugin restent cohérents
```

La CI lance ces deux-là, plus une install / selftest / désinstallation complète
sur macOS et chaque migration rejouée deux fois. C'est un petit workflow, il
tourne en moins d'une minute — lis `.github/workflows/ci.yml` pour voir
exactement ce qui est affirmé.

## Ce qui fera refuser un patch

- **Un fichier moteur édité à la main sur `fr`.** Voir plus haut — ce n'est pas
  une préférence de style, la modification ne peut réellement pas survivre.
- **Tout ce qui fait téléphoner l'outil à la maison.** Zéro télémétrie, zéro
  analytics, zéro appel réseau au-delà de `git pull`. C'est une ligne dure, pas
  un réglage par défaut.
- **Tout ce qui écrit dans le tronc de l'utilisateur sans qu'on l'ait demandé.**
  Le tronc, c'est son travail. `uninstall.sh` le laisse debout ; `brain demo
  --remove` n'efface pas une fiche d'exemple que l'utilisateur a modifiée, parce
  qu'en la modifiant elle est devenue la sienne. Le nouveau code tient la même
  règle.
- **Une migration qui fait plus que migrer.** Une migration déplace. Le
  recâblage est le métier d'`install.sh`, et `update.sh` l'appelle de toute
  façon — dupliquer cette logique crée deux copies qui divergeront.

## Ce qui est vraiment bienvenu

- **La portabilité.** Aujourd'hui c'est macOS seulement : `launchd`, Electron,
  `open`. Un chemin Linux propre est un vrai travail et serait une vraie
  contribution.
- **Un deuxième agent CLI.** La boucle fermée est câblée sur les hooks de Claude
  Code. Le reste — tronc, agents, `brain`, planète, capsule — marche à la
  demande n'importe où.
- **Les trous de traduction.** Les commentaires des hooks sont encore
  partiellement français ; `english_only.py` ignore délibérément les
  commentaires, il ne les trouvera donc pas pour toi.
- **Tout ce que la CI aurait dû attraper et n'a pas attrapé.** Un test qui
  échoue en démontrant le trou vaut plus que le correctif.

## Style

Les messages de commit expliquent ici **pourquoi**, et disent ce qui a cassé et
comment ça a été trouvé — souvent longuement. Fais pareil si tu peux ; un « fix
bug » d'une ligne n'apprend rien au lecteur suivant qu'il ne voie déjà dans le
diff.

## Licence

En contribuant, tu acceptes que ta contribution soit sous licence
[Apache 2.0](LICENSE), comme le reste du projet.
