# Installer C Brain

## La façon courte : demande-le à ton agent

Colle ceci dans ton CLI (Claude Code ou un autre agent en ligne de commande) :

```
Installe C Brain : clone <URL-DU-DÉPÔT> dans ~/dev/c-brain, lis son INSTALL.md,
puis exécute ./install.sh et montre-moi le résultat de la vérification finale.
```

C'est tout. L'agent clone, installe, et te rend le compte-rendu du selftest.

## La façon manuelle

```bash
git clone <URL-DU-DÉPÔT> ~/dev/c-brain
cd ~/dev/c-brain
./install.sh
```

Options : `--dry-run` (n'écrit rien, montre ce qui serait fait) ·
`--no-launchd` (pas de tâches planifiées) · `--no-capsule` (pas d'Electron).

---

## Ce que l'installation fait — et ne fait pas

Deux emplacements, et la séparation est le cœur du système :

```
~/.c-brain/engine  → lien vers ce dépôt. Du CODE, rien d'autre. Se met à jour.
~/.c-brain/trunk     → TON tronc. Tes fiches. Jamais écrasé, jamais mis à jour.
```

L'installeur :

- crée ton tronc **vide** s'il n'existe pas (il ne touche à rien s'il existe) ;
- relie le moteur dans le tronc par liens symboliques ;
- pose la commande `brain` dans `~/.local/bin` ;
- rend les agents visibles par ton CLI ;
- **ajoute** ses hooks à `~/.claude/settings.json` sans toucher au reste — ton
  modèle, ton thème, tes propres hooks sont conservés, et une sauvegarde est
  écrite avant toute modification ;
- installe la capsule et les tâches planifiées, sauf si tu les refuses ;
- pose un lanceur de la planète sur le Bureau ;
- **vérifie son propre travail** (`selftest` + `doctor`) et te montre le résultat.

Il ne supprime rien, n'envoie rien sur le réseau, et ne lit aucune de tes données.

## Dépôt privé : s'authentifier une fois

C Brain est distribué sur invitation. Sans identifiants git, le clone **et** les
mises à jour échouent — la mise à jour automatique note alors « impossible de
récupérer les versions distantes » dans `~/.c-brain/state/auto-update.log` et
réessaie à la session suivante, sans jamais bloquer ta session.

Le plus simple, une seule fois :

```bash
gh auth login          # puis : gh auth setup-git
```

Ou en SSH : ajoute ta clé à ton compte GitHub et clone via
`git@github.com:…` plutôt que `https://…`.

## Prérequis

| Requis | Pour quoi |
|---|---|
| macOS | launchd, Electron, `open` |
| `python3` | tous les hooks et la CLI |
| `git` | les mises à jour |
| `npm` *(optionnel)* | la capsule Electron — le reste marche sans |

## Si tu n'utilises pas Claude Code

C Brain s'installe quand même, et te donne le tronc, les agents, la CLI `brain`,
la planète et la capsule.

**Ce que tu n'auras pas** : la boucle automatique. Le rappel au début d'une
session, l'archivage à la fin, la maintenance autonome passent par les hooks de
`~/.claude/settings.json`, qui sont propres à Claude Code. Ailleurs, C Brain
fonctionne **à la demande** : `brain recall`, `brain status`, agents invoqués
explicitement. L'installeur le détecte et te le dit — il ne fait pas semblant.

## Premiers gestes

Ton tronc part **vide**, et un tronc vide ne montre rien. Commence par le
remplir d'exemples, le temps de comprendre la boucle :

```bash
brain demo                     # pose 3 fiches d'exemple
brain recall cache déploiement # ce que le rappel retrouve, et pourquoi
brain demo --remove            # les retire, sans laisser de trace
```

Les trois fiches montrent les trois types utiles — une **leçon**, une fiche de
**méthode**, un **point de reprise** de projet — et sont reliées entre elles,
pour que le graphe ait quelque chose à afficher.

`--remove` ne touche pas à une fiche que tu aurais modifiée : elle a cessé
d'être un exemple à la première ligne que tu y as écrite.

Ensuite, au quotidien :

```bash
brain status          # où en est le tronc
brain recall <mot>    # chercher dans ta mémoire
brain doctor          # santé de l'arbre
brain selftest        # revérifier l'installation
```

Puis ouvre `~/.c-brain/trunk/MEMORY.md` : c'est l'index chargé au début de chaque
session, et le format des fiches y est expliqué. Ton arbre grandit avec le
travail, pas avant.

## Désinstaller

```bash
~/dev/c-brain/uninstall.sh
```

**Ton tronc et tes fiches ne sont jamais supprimés.** Sont retirés : les hooks
C Brain (le reste de `settings.json` intact), les liens du moteur, la commande
`brain`, le lanceur du Bureau, les tâches planifiées. Les sauvegardes restent
dans `~/.c-brain/backups/`.
