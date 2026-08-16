# Sécurité

## Ce que ce logiciel fait réellement à ta machine

Ça vaut d'être dit franchement, parce que c'est la base honnête pour juger du
risque :

- **Il écrit à l'intérieur de `$HOME`.** `~/.c-brain/` (moteur et tronc),
  `~/.claude/` (fusion des réglages, barre d'état),
  `~/Library/LaunchAgents/com.claudebrain.*` (tâches planifiées), un lanceur sur
  le Bureau, et un raccourci `C Brain` dans ton dossier personnel qui pointe
  vers ton tronc (`--no-shortcut` le saute). `install.sh` consigne chacun de ces
  gestes dans un manifeste, et `uninstall.sh` les défait.
- **Il exécute du code sur ta machine automatiquement.** C'est le but : les
  hooks se déclenchent sur les événements de ton agent CLI, et deux tâches
  `launchd` tournent sur minuterie. Installe avec `--no-launchd` si tu préfères
  que rien ne tourne sans surveillance.
- **Il ne fait aucun appel réseau à part `git pull`.** Zéro télémétrie, zéro
  analytics, zéro rapport de plantage, zéro appel maison à l'installation.
- **Il se met à jour tout seul — dis-le-toi avant d'installer.** Depuis
  v1.28.0, chaque démarrage de session récupère les tags publiés et installe la
  dernière version, en arrière-plan. C'est du **code distant qui s'exécute sur
  ta machine sans que tu l'aies demandé** : c'est le compromis le plus lourd de
  ce paquet, et il est délibéré — un correctif que personne n'installe ne
  corrige rien. Ce qui le borne :
  - la mise à jour suit les **tags publiés**, jamais une branche de travail ;
  - le **selftest décide** : rouge, la version d'avant est remise
    automatiquement, et la session suivante te le dit ;
  - le **tronc n'est jamais touché** — seul `~/.c-brain/engine` est remplacé ;
  - `brain update --auto-off` rend le comportement d'avant (on signale, on
    n'installe pas). `--auto-on` le remet.

  Si tu veux inspecter avant que ça tourne, coupe l'automatique **dès
  l'installation** : `brain update --auto-off`.
- **Il lit tes fiches en local, et c'est comme ça qu'il marche.** Le rappel,
  l'index, le graphe et les agents ouvrent tous les fichiers — on ne peut pas
  retrouver une fiche sans en lire une. Ça se passe sur ta machine, et rien ne
  nous revient.
- **Ce qui quitte ta machine, c'est ce que ton prompt emporte.** Le hook de
  rappel ajoute le **nom, la description d'une ligne et le chemin** des deux ou
  trois fiches les plus pertinentes au prompt que tu t'apprêtes à envoyer — pas
  le corps des fichiers. Ce prompt part chez ton fournisseur de modèle, comme le
  reste de ton message. C Brain ne fait aucune requête de son côté, mais il
  serait faux de dire que rien de ton tronc ne voyage : ce qu'il met dans un
  prompt voyage avec le prompt. `brain doctor` montre ce que le hook injecterait ;
  retirer le hook `UserPromptSubmit` de `settings.json` l'arrête complètement.
- **Les agents sont le cas bruyant.** Quand tu lances `distillateur`,
  `jardinier` ou un autre, il lit des fiches entières et les envoie au
  fournisseur — c'est ce que tu lui as demandé de faire. Rien d'automatique
  là-dedans : c'est toi qui les démarres.

## Versions suivies

Les correctifs vont sur la dernière version publiée. Il n'y a pas de branche de
support long terme, et les anciens tags ne sont pas patchés — `brain update` te
fait avancer.

## Signaler une faille

**N'ouvre pas d'issue publique pour un problème de sécurité.**

Utilise le signalement privé de GitHub sur ce dépôt :
**Security → Report a vulnerability**. Ça arrive directement au mainteneur et
reste privé jusqu'au correctif.

Utile dans un signalement : ce qu'un attaquant peut faire, ce qu'il lui faut au
départ (accès local ? un dépôt malveillant ? une fiche fabriquée ?), et la plus
courte séquence qui le démontre.

Compte environ une semaine pour une première réponse. C'est un projet personnel,
pas un produit avec une équipe — ce chiffre est ce qu'un mainteneur seul peut
honnêtement promettre.

## Dans le périmètre

- Tout ce qui permet à **une fiche, un dépôt ou une charge utile de hook**
  d'exécuter du code que l'utilisateur n'a pas demandé.
- **Le traitement des chemins** dans `install.sh`, `uninstall.sh` et les
  migrations — ils déplacent des dossiers dans `$HOME`, et une erreur là coûte
  du travail réel.
- **`leakcheck.py` qui échoue en laissant passer** : c'est lui qui se tient
  entre un tronc personnel et un push public. Un moyen de lui faire passer un
  secret est une vulnérabilité, et l'une des plus intéressantes ici.
- **`merge_settings.py` qui corrompt ou perd des clés** dans
  `~/.claude/settings.json`.

## Hors périmètre

- Le fait que le moteur s'exécute sur ta machine par conception — voir plus haut.
- Tout ce qui suppose un attaquant ayant déjà accès en écriture à ton `$HOME` ;
  à ce stade il n'a pas besoin de C Brain.
- Les signalements visant la branche `fr` qui ne s'appliquent pas aussi à
  `main`, sauf si le défaut est spécifiquement dans la version française.
