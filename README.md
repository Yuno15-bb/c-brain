# 🧠 C Brain

**Une mémoire qui grandit** pour les agents en ligne de commande.

Ton agent CLI est excellent dans une session, et amnésique entre deux. C Brain
lui donne un tronc de connaissance persistant : ce que tu comprends une fois est
distillé en fiche, rangé, relié, et **retrouvé automatiquement** la fois d'après —
depuis n'importe quel projet.

Plus le travail s'accumule, plus l'arbre devient utile. C'est l'inverse d'un
historique de conversation, qui ne fait que s'allonger.

---

## Ce que ça fait concrètement

| | |
|---|---|
| 🌳 **Un tronc** | tes leçons, projets, méthode — en markdown, chez toi, versionnable |
| 🔎 **Rappel automatique** | à chaque question, les fiches pertinentes sont injectées dans le contexte |
| 🤖 **8 agents** | ils distillent, rangent, relient, contestent, synthétisent, élaguent, réparent, surveillent la machine |
| 🔁 **Boucle fermée** | fin de session → archivage → distillation → rangement, sans rien demander |
| 🥚 **Une capsule** | petite fenêtre qui montre les agents travailler, en direct |
| 🪐 **Une planète** | ton savoir en globe 3D navigable, régénéré à chaque lancement |
| ⬆️ **Mises à jour** | le moteur se met à jour ; **tes fiches ne sont jamais touchées** |

## Installation

Colle ceci dans ton CLI :

```
Installe C Brain : clone <URL-DU-DÉPÔT> dans ~/dev/c-brain, lis son INSTALL.md,
puis exécute ./install.sh et montre-moi le résultat de la vérification finale.
```

Ou à la main : `git clone … && cd c-brain && ./install.sh`

Détails, prérequis et désinstallation : **[INSTALL.md](INSTALL.md)**.

## L'idée qui tient tout

```
~/.c-brain/engine  ← le MOTEUR. Du code. Se met à jour, se remplace, se jette.
~/.c-brain/trunk     ← le TRONC. Tes fiches. Ne bouge que quand TU écris.
```

Les deux ne se mélangent jamais. C'est ce qui permet à une mise à jour d'arriver
sans le moindre risque pour ton travail — et à `uninstall.sh` de tout retirer en
laissant ta connaissance intacte.

## Ce que ça ne fait pas

- **Ça n'envoie rien.** Aucune télémétrie, aucun appel réseau hors `git pull`.
- **Ça ne lit pas tes fiches**, sauf pour te les rendre.
- **Ça n'installe rien tout seul.** Une nouvelle version est *signalée* ; tu
  lances `brain update` quand ça t'arrange.
- **Ça ne livre aucun contenu.** Ton arbre démarre vide — voir
  [`skills/README.md`](skills/README.md) pour la philosophie : on transmet la
  méthode, pas le vécu de quelqu'un d'autre.

## Commandes

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

