// LES DIX MÉCANIQUES DE FLUIDE — rien que des constantes.
//
// POURQUOI CE FICHIER EXISTE, ALORS QUE CE SONT DIX NOMBRES
//   `palettes.js` n'a besoin que de ça pour dire quelle famille bouge comment.
//   Mais ces constantes vivaient dans `orbe.js`, qui importe Three.js — donc
//   toute page qui voulait seulement CONNAÎTRE LES COULEURS téléchargeait
//   1,27 Mo de moteur 3D avant de pouvoir en afficher une.
//   Invisible sur le bureau (tout est sur le disque), très visible sur un
//   téléphone en 4G : l'auteur a vu le fond teinté de l'orbe arriver « bien en
//   retard » — il attendait Three.
//   `orbe.js` les RÉEXPORTE : tout code qui les importait de là continue de
//   marcher, aucun appelant à modifier.
export const MECANIQUES = { houle:0, balayage:1, plaques:2, ebullition:3,
  ondeDeChoc:4, cellules:5, vortex:6, respiration:7, interference:8, eclats:9 };
