# 🧠 C Brain

[![CI](https://github.com/Yuno15-bb/c-brain/actions/workflows/ci.yml/badge.svg?branch=fr)](https://github.com/Yuno15-bb/c-brain/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Yuno15-bb/c-brain?sort=semver&color=6b8afd)](https://github.com/Yuno15-bb/c-brain/releases/latest)
[![Licence](https://img.shields.io/github/license/Yuno15-bb/c-brain?color=8a8f98)](LICENSE)
[![Plateforme](https://img.shields.io/badge/plateforme-macOS-8a8f98)](#compatibilité)

> 🇫🇷 Ceci est la **branche française**. La version anglaise, celle que tout le
> monde installe par défaut, est sur [`main`](https://github.com/Yuno15-bb/c-brain).

**C Brain transforme chaque session avec ton agent CLI en mémoire réutilisable —
distillée en fiche, rangée, reliée, et rendue automatiquement la fois où ça
compte. Depuis n'importe quel projet, et sans quitter ta machine.**

Ton agent est excellent dans une session et amnésique entre deux. Tu résous
quelque chose lundi, tu le réexpliques jeudi. C Brain est la partie qui se
souvient.

Plus le travail s'accumule, plus l'arbre devient utile — l'inverse d'un
historique de conversation, qui ne fait que s'allonger.

---

## Ce que ça fait concrètement

**La mémoire elle-même** — c'est ça le produit, et ça suffit :

| | |
|---|---|
| 🌳 **Un tronc** | tes leçons, projets, méthode — en markdown, chez toi, versionnable |
| 🔎 **Rappel automatique** | à chaque question, les fiches pertinentes sont injectées dans le contexte |
| 🤖 **8 agents** | ils distillent, rangent, relient, contestent, synthétisent, élaguent, réparent, surveillent la machine |
| 🔁 **Boucle fermée** | fin de session → archivage → distillation → rangement, sans rien demander |
| ⬆️ **Mises à jour** | le moteur se met à jour ; **tes fiches ne sont jamais touchées** |

**Et deux façons de le regarder**, qui sont des extensions et s'installent à
part — `./install.sh --core-only` laisse les deux de côté :

| | |
|---|---|
| 🥚 **Une capsule** | petite fenêtre Electron qui montre les agents travailler, en direct |
| 🪐 **Une planète** | ton savoir en globe 3D navigable, régénéré à chaque lancement |

### Il est bon à quel point, ce rappel ?

Mesuré, pas affirmé — `tests/recall_benchmark.py`, sur un corpus synthétique où
trouver la réponse veut dire choisir **une** fiche parmi ~120 qui partagent son
sujet et l'essentiel de son vocabulaire :

| fiches | P@1 | P@3 | MRR | hors sujet dans ce qu'il injecte | par prompt |
|---|---|---|---|---|---|
| 100 | 0,94 | 0,98 | 0,96 | 35 % | 5 ms |
| 1000 | 0,79 | 0,93 | 0,86 | 24 % | 47 ms |
| 5000 | 0,46 | 0,83 | 0,64 | 39 % | — |

Il tient jusqu'à environ mille fiches et se dégrade nettement au-delà. Publié
ici parce qu'un outil de mémoire qui refuse de dire à quel point il se souvient
demande une confiance qu'il n'a pas gagnée. La CI tient ces chiffres comme des
seuils.

## Installation

**En plugin Claude Code** — la voie courte, et celle qui se met à jour toute
seule (elle installe la version **anglaise** : le plugin suit `main`) :

```
/plugin marketplace add Yuno15-bb/c-brain
/plugin install c-brain@c-brain
```

Ça te donne toute la mémoire : le tronc, le rappel automatique, les huit agents,
la commande `brain`, et trois commandes que tu peux taper — `/c-brain:recall`,
`/c-brain:distill`, `/c-brain:doctor`. Le tronc `~/.c-brain/trunk` est créé à ta première
session, et on te le dit. Ça n'installe **pas** la capsule, la planète ni les
tâches planifiées — un plugin ne peut pas installer un service d'arrière-plan,
et prétendre le contraire te laisserait avec une fenêtre qui ne s'ouvre jamais.

**L'install complète, en français** — tout ce qui précède, plus la capsule, la
planète et la maintenance sans surveillance. Colle ceci dans ton CLI :

```
Installe C Brain : clone https://github.com/Yuno15-bb/c-brain dans ~/dev/c-brain
sur la branche fr, lis son INSTALL.md, puis exécute ./install.sh et montre-moi
le résultat de la vérification finale.
```

Ou à la main : `git clone -b fr … && cd c-brain && ./install.sh`

**La mémoire et rien d'autre** — pas de fenêtre Electron, pas de globe 3D, pas
de tâche de fond :

```bash
./install.sh --core-only
```

Détails, prérequis et désinstallation : **[INSTALL.md](INSTALL.md)**.

## L'idée qui tient tout

```
~/.c-brain/engine  ← le MOTEUR. Du code. Se met à jour, se remplace, se jette.
~/.c-brain/trunk     ← le TRONC. Tes fiches. Ne bouge que quand TU écris.
```

Les deux ne se mélangent jamais. C'est ce qui permet à une mise à jour d'arriver
sans le moindre risque pour ton travail — et à `uninstall.sh` de tout retirer en
laissant ta connaissance intacte.

Le point de `~/.c-brain` le **cache dans le Finder**. L'installation pose donc
un raccourci `C Brain` dans ton dossier personnel, tagué en rouge, qui ouvre ton
tronc — une mémoire qu'on ne peut pas voir est une mémoire à laquelle on ne
touche jamais (`--no-shortcut` si tu n'en veux pas).

<p align="center">
  <img src="docs/media/where-it-lands.png" alt="Un dossier personnel dans le Finder : les habituels Applications, Bureau, Documents, Téléchargements, Films, Musique et Images — plus un dossier C Brain tagué en rouge, désigné par une flèche" width="900">
</p>

## Ce que ça ne fait pas

- **Ça ne fait aucune requête de son côté.** Aucune télémétrie, aucun appel
  réseau hors `git pull`. Ce qui voyage, c'est ce que tes prompts emportent
  déjà : le hook de rappel ajoute le nom, la description et le chemin de deux ou
  trois fiches à un prompt que tu envoyais de toute façon, et les agents que tu
  lances lisent des fiches entières. Les deux partent chez ton fournisseur de
  modèle, comme le reste de ton message. [`SECURITY.md`](SECURITY.md) dit
  précisément où passe la ligne.
- **Ça n'installe rien tout seul.** Une nouvelle version est *signalée* ; tu
  lances `brain update` quand ça t'arrange.
- **Ça ne livre aucun contenu.** Ton arbre démarre vide — voir
  [`skills/README.md`](skills/README.md) pour la philosophie : on transmet la
  méthode, pas le vécu de quelqu'un d'autre.

## Les extensions

Aucune des deux ci-dessous n'est le produit. Ce sont des façons de le *regarder*
— agréables, facultatives, et entièrement sautées par `./install.sh --core-only`.
L'installation en plugin ne les met jamais en place, parce qu'un plugin ne peut
pas installer un service d'arrière-plan.

### La capsule

<p align="center">
  <img src="docs/media/capsule.webp" alt="La capsule : une petite fenêtre qui parcourt tous les états des agents — distillation, jardinage, rangement, correction, cartographie, architecture, contestation, archivage, synthèse, audit, commit, puis retour au repos" width="190">
</p>
<p align="center"><sub>À sa taille réelle — les onze états qu'elle peut te montrer, puis le repos.</sub></p>

### La planète

Ton savoir en globe 3D, régénéré à chaque lancement depuis les fiches. Les
continents sont les domaines, les arcs sont les liens `[[...]]` que les agents
ont tissés. Survoler une fiche allume ses connexions ; un double-clic l'épingle.

<p align="center">
  <img src="docs/media/planet.webp" alt="La planète de connaissance : le globe tourne, le curseur se pose sur une fiche, ses arcs de liens s'allument et un panneau s'ouvre montrant la région de la fiche, ses sept connexions, sa description et le chemin de son fichier" width="900">
</p>

## Commandes

<p align="center">
  <img src="docs/media/recall.png" alt="Terminal : brain demo pose trois fiches, brain recall les classe par pertinence, brain demo --remove les retire" width="820">
</p>

```bash
brain status          où en est le tronc
brain recall <mot>    chercher dans ta mémoire
brain doctor          santé de l'arbre (liens morts, incohérences)
brain review          audit global du tronc
brain next            tes points de reprise
brain selftest        vérifier l'installation
brain update          mettre à jour le moteur  (--check · --rollback)
brain version         version installée
```

## Compatibilité

**macOS.** launchd, Electron et `open` sont utilisés.

**Linux n'est pas encore supporté, et l'écart est plus petit qu'il n'y paraît.**
En lisant le code plutôt qu'en devinant : macOS n'est supposé qu'à **quatre
endroits** — le contrôle de plateforme d'`install.sh`, les gabarits `launchd`, le
lanceur `.command` du Bureau, et le tag Finder `xattr`. Claude Code n'est supposé
que dans **un** fichier, `merge_settings.py`. Tout le reste — tronc, rappel,
agents, CLI `brain`, hooks — est déjà du Python et du shell portables.

C'est donc un cœur portable avec deux adaptateurs minces, pas un produit macOS.
L'ordre prévu : **des unités `systemd` à la place de `launchd`, une entrée
`.desktop` à la place du `.command`, pas de tag Finder, et `--core-only` comme
forme par défaut sous Linux.** Aucune date là-dessus : dire quels quatre endroits
doivent changer est plus utile qu'une promesse.

**Claude Code** pour l'expérience complète : c'est lui qui déclenche les hooks
(rappel, archivage, maintenance autonome, ligne d'état). Avec un autre agent CLI,
C Brain s'installe et fonctionne **à la demande** — tronc, agents, `brain`,
planète, capsule — mais sans boucle automatique. L'installeur le détecte et te le
dit plutôt que de faire semblant.

## Pour les curieux

- [`docs/cadrage-c-brain.md`](docs/cadrage-c-brain.md) — le design-doc : le
  problème, les alternatives rejetées, les pièges rencontrés et comment ils ont
  été refermés.
- `sync.sh` + `rules.json` + `leakcheck.py` — la chaîne qui extrait ce moteur
  d'un Brain réel sans en laisser fuir une ligne de vécu.

## Licence

**Apache 2.0** — voir [LICENSE](LICENSE).

Tu peux l'utiliser, l'étudier, le modifier, le redistribuer et construire dessus,
y compris commercialement. La licence inclut une clause de brevets, et demande
seulement de conserver l'attribution et d'indiquer tes modifications.

Tout ce que tu écris avec — tes notes, ton tronc, tes skills — t'appartient, et
cette licence n'en revendique rien.

