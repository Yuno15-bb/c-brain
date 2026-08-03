# Banc de vérification de l'orbe

Regarder le rendu, jamais le déduire du code. Ces scripts existaient dans `/tmp`
pendant la session du 2026-08-03 — ils y auraient disparu au prochain redémarrage,
alors qu'ils sont la seule façon honnête de juger une modification de l'orbe.

## Les scripts

| Script | Ce qu'il fait |
|---|---|
| `planche.cjs` | capture `orbe.html` état par état, sur un faux bureau coloré |
| `silhouette.cjs` | relève les bornes du mesh sur le canal alpha, état par état |
| `glisse.cjs` | prouve que `mousedown` au centre déplace la fenêtre, et qu'un coin ne fait rien |

Tous se lancent avec l'Electron du dossier parent :

```sh
cd ~/claude-brain/capsule
./node_modules/.bin/electron banc/planche.cjs
```

## Les pièges qui ont coûté du temps

- **Le verre ne se juge pas sur fond noir.** Un objet transparent y est
  indiscernable d'un objet opaque. `planche.cjs` pose donc un dégradé et du
  texte derrière — sans ça la planche ne prouve rien.
- **La démo de `~/Desktop/Orbe` rétrécit l'orbe à 69 px** dans une fenêtre de
  150 : sa mise en page réserve la place d'un panneau. On mesure sur
  `orbe.html`, la vraie page de la capsule.
- **Les bornes sortent en pixels d'ÉCRAN, pas en pixels CSS** : la capture est
  en retina 2×, donc une fenêtre de 150 rend un bitmap de 300. Les lire tels
  quels place un élément au double de la bonne distance.
- **Attendre 2,6 s après un changement d'état** : le fondu de mécanique dure
  1,4 s, et capturer avant donne une forme intermédiaire qui n'existe jamais.
- **Tuer par chemin complet ET vérifier le compte** avant toute mesure :
  `pgrep -f "claude-brain/capsule" | xargs kill -9` puis recompter. Un motif
  approximatif échoue en silence et on mesure une instance périmée.
