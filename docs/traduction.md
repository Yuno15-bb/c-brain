# Deux branches, un moteur

`main` est en **anglais**. `fr` est en **français**, et c'est la branche sur
laquelle le moteur est extrait.

```
~/claude-brain (français)  ──sync.sh──▶  fr  ──traduction──▶  main (anglais)
     le Brain vivant                                    ce que les gens installent
```

## Pourquoi ce sens et pas l'autre

Le Brain source est écrit en français : ses hooks, les prompts de ses agents,
ses commentaires. `sync.sh` copie depuis lui et `generalize.py` le réécrit avec
des règles qui **matchent des chaînes françaises**. Ni l'un ni l'autre ne peut
tourner contre des fichiers anglais.

L'anglais ne peut donc pas être la cible du sync. Il en dérive, un cran plus loin.

## Le garde-fou

`./sync.sh` **refuse de tourner sur `main`**. Sans ce garde-fou, un seul sync
écraserait en silence chaque fichier traduit par son original français — et rien
ne l'attraperait : aucun test ne lit de la prose. Seul un lecteur le
remarquerait, bien plus tard.

```
❌ ./sync.sh tourne sur la branche `fr`, pas sur `main`.
```

`CBRAIN_ALLOW_SYNC_ON_MAIN=1` le force, pour le cas rare où tu sais pourquoi.

## Ce que le sync ne prend PAS

Trois fichiers vivent **uniquement dans le paquet** et sont exclus du sync,
parce que `rsync --delete` les effacerait à la première passe :

| Fichier | Pourquoi il n'est pas dans le Brain vivant |
|---|---|
| `hooks/hooks.json` | manifeste de hooks du plugin Claude Code |
| `tests/plugin_manifest.py` | vérifie les manifestes du paquet |
| `tests/english_only.py` | surveille la traduction, sur `main` seulement |

C'est le pire défaut possible ici : un `hooks.json` effacé ne plante pas, le
plugin **arrête simplement d'enregistrer**.

## Enchaînement quand le Brain évolue

```bash
git checkout fr
./sync.sh                  # copie + généralisation, français
python3 leakcheck.py       # doit être vert
git commit -am "sync : <ce qui a bougé>"

git checkout main
git diff fr@{1} fr -- .    # ce qui a réellement changé
# porter ces changements, traduits, sur main
python3 leakcheck.py --history
./publish.sh v1.2.0 "..."
```

Lis le diff avant de traduire. La plupart des syncs déplacent une poignée de
lignes ; un `git merge fr` aveugle ramènerait tout l'arbre français sur `main`.

## Tags

| Branche | Tags | Qui l'installe |
|---|---|---|
| `main` | `v1.2.0` | tout le monde, par défaut |
| `fr` | `v1.2.0-fr` | les francophones qui le demandent |

⚠ **Ceci a d'abord été écrit à l'envers, et c'était un vrai bug.** Le texte
précédent affirmait que chaque install restait dans sa langue « tant que chaque
clone suit sa propre branche ». Ce raisonnement ne tient pas : `update.sh` n'a
jamais regardé la moindre branche. Il lançait
`git tag -l 'v*' | sort -V | tail -1`, et **les tags ne sont pas rangés par
branche** — il voyait donc les deux familles d'un coup. Comme `sort -V` place
`v1.18.0-fr` **après** `v1.18.0`, le maximum global était le tag français, et
une installation anglaise aurait basculé sur l'arbre français dès que `fr`
rattrapait son retard. Aucune erreur : le tag existe, le checkout réussit,
l'outil se met simplement à parler une autre langue.

Ça n'est resté invisible que parce que `fr` traînait huit versions derrière.
La remettre à niveau est ce qui l'a armé.

`update.sh` lit désormais la famille sur ce qui est installé — le suffixe du tag
posé, ou la branche suivie quand il n'y en a pas — et filtre la liste des tags
avant de trier. `tests/update_tag_family.sh` construit un dépôt jetable avec les
deux branches et le tient en CI.
