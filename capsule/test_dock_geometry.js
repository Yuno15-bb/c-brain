// C Brain — capsule : les cas de Dock qu'on n'a pas sous la main.
//
// POURQUOI CE TEST. La machine de développement a UN écran, avec le Dock en
// bas. Tous les autres cas — masqué automatiquement, à gauche, à droite, sur un
// second écran, en haute densité — sont exactement ceux qui casseront chez
// quelqu'un d'autre, et aucun ne peut être reproduit sans changer les réglages
// de la personne qui travaille.
//
// La géométrie est pure : deux rectangles entrent, un côté et une épaisseur
// sortent. Elle se vérifie donc entièrement sur table.
//
// Lancer : node capsule/test_dock_geometry.js
const { dockGeometry, bosseDock, hauteurDockSousPoint, porteeDock, PORTEE,
        MARGE_VISIBLE, RAMPE_V } = require('./dock-geometry');

let echecs = 0;
function verif(nom, obtenu, attendu) {
  const a = JSON.stringify(attendu), o = JSON.stringify(obtenu);
  if (a === o) { console.log(`  ✅ ${nom}`); }
  else { console.log(`  ❌ ${nom}\n       attendu ${a}\n       obtenu  ${o}`); echecs++; }
}

// Un écran tel que `screen.getAllDisplays()` le rend : bounds = la dalle
// entière, workArea = ce que macOS laisse aux fenêtres.
const ecran = (bounds, workArea) => ({ bounds, workArea });

console.log('▸ le cas de cette machine, relevé le 2026-07-30');
// 1470×956, barre de menus 33 px, Dock en bas 57 px.
verif('Dock en bas',
  dockGeometry(ecran({ x:0, y:0, width:1470, height:956 },
                     { x:0, y:33, width:1470, height:866 })),
  { side:'bottom', size:57, visible:true });

console.log('▸ la barre de menus ne doit JAMAIS passer pour le Dock');
// Le seul retrait est en haut : c'est la barre de menus. Sans l'exclusion, le
// compagnon irait se coller sous l'horloge.
verif('barre de menus seule → aucun Dock',
  dockGeometry(ecran({ x:0, y:0, width:1470, height:956 },
                     { x:0, y:33, width:1470, height:923 })),
  { side:'bottom', size:0, visible:false });

console.log('▸ Dock masqué automatiquement : il n\'y a plus de sol');
verif('aucun retrait → pas de Dock visible',
  dockGeometry(ecran({ x:0, y:0, width:1470, height:956 },
                     { x:0, y:33, width:1470, height:919 })),
  { side:'bottom', size:0, visible:false });

console.log('▸ les côtés');
verif('Dock à gauche',
  dockGeometry(ecran({ x:0, y:0, width:1470, height:956 },
                     { x:64, y:33, width:1406, height:923 })),
  { side:'left', size:64, visible:true });
verif('Dock à droite',
  dockGeometry(ecran({ x:0, y:0, width:1470, height:956 },
                     { x:0, y:33, width:1406, height:923 })),
  { side:'right', size:64, visible:true });

console.log('▸ un second écran, dont l\'origine n\'est pas 0,0');
// Le piège des coordonnées : un écran à droite du principal commence à
// x=1470. Une soustraction qui oublie l'origine sort une épaisseur de Dock
// de 1470 px, et le compagnon part hors de l'écran.
verif('écran secondaire sans Dock',
  dockGeometry(ecran({ x:1470, y:0, width:1920, height:1080 },
                     { x:1470, y:0, width:1920, height:1080 })),
  { side:'bottom', size:0, visible:false });
verif('écran secondaire AVEC le Dock',
  dockGeometry(ecran({ x:1470, y:0, width:1920, height:1080 },
                     { x:1470, y:0, width:1920, height:1010 })),
  { side:'bottom', size:70, visible:true });

console.log('▸ le seuil : un liseré de quelques pixels n\'est pas un Dock');
// macOS laisse parfois 4 px au bord même Dock masqué. S'y poser dessus ferait
// flotter le compagnon au-dessus du vide, sans que rien ne l'explique.
verif('4 px → pas un Dock',
  dockGeometry(ecran({ x:0, y:0, width:1470, height:956 },
                     { x:0, y:33, width:1470, height:919 })),
  { side:'bottom', size:0, visible:false });
verif('8 px → c\'en est un',
  dockGeometry(ecran({ x:0, y:0, width:1470, height:956 },
                     { x:0, y:33, width:1470, height:915 })),
  { side:'bottom', size:8, visible:true });

// ── LA VAGUE ───────────────────────────────────────────────────────────────
// La magnification ne touche PAS workArea : aucune mesure d'écran ne la
// révèle. Ces cas-là sont donc les seuls garants du comportement — et ils
// tournent sans souris, ce qu'aucun test manuel ne permet.
const ECRAN = { bounds:{x:0,y:0,width:1470,height:956}, workArea:{x:0,y:33,width:1470,height:866} };
const DOCK  = { side:'bottom', size:57, visible:true };
const PREFS = { magnification:true, tile:37, large:128 };
const X = 735;                       // centre de la créature, écran centré
const SUR_LE_DOCK = 930;             // y du curseur quand il longe le Dock
const AILLEURS    = 500;             // y du curseur au milieu de l'écran
const h = (px, py=SUR_LE_DOCK) => hauteurDockSousPoint(DOCK, ECRAN, X, {x:px,y:py}, PREFS);

console.log('▸ la cloche');
verif('pile sous le curseur → plein gonflement', bosseDock(0), 1);
verif('au-delà de la portée → rien', bosseDock(PORTEE), 0);
verif('bien au-delà → rien', bosseDock(PORTEE + 300), 0);
verif('symétrique gauche/droite', bosseDock(-70), bosseDock(70));
// ⚠ ASSERTION RESSERRÉE. La première disait seulement « proche de 0 au bord » —
// et un simple cosinus la passait aussi. Elle ne distinguait donc pas la cloche
// voulue (cos², qui s'aplatit aux deux bouts) d'une pente presque droite. Le
// test était vert et ne prouvait rien : vérifié par mutation, remplacer cos²
// par cos ne faisait rougir personne.
// À mi-portée, cos² vaut exactement 0,5 là où cos vaut 0,707 : c'est ce point
// qui sépare les deux formes.
verif('à mi-portée, la cloche est à la moitié', Math.round(bosseDock(PORTEE / 2) * 1000) / 1000, 0.5);
verif('le bord s\'éteint en douceur', bosseDock(PORTEE - 1) < 0.001, true);

console.log('▸ la hauteur sous la créature');
verif('curseur dessus → Dock au maximum', h(X), 57 + (128 - 37));
verif('curseur loin sur le Dock → hauteur de repos', h(X + 400), 57);
// Le piège : survoler la CRÉATURE (100 pt plus haut) n'est pas survoler le Dock.
verif('curseur au milieu de l\'écran → aucune vague', h(X, AILLEURS), 57);
// ⚠ Distances exprimées en FRACTION DE LA PORTÉE, pas en points fixes. Écrites
// en dur (90 et 170) elles étaient calibrées pour une portée de 190 ; le jour
// où on l'a resserrée à ~85, les deux points sont tombés au-delà et le test a
// rougi pour une raison qui n'était pas le bug. Un test doit suivre le
// réglage, pas le figer.
const P = porteeDock(PREFS);
verif('la vague est monotone en s\'éloignant',
  h(X) > h(X + P * 0.35) && h(X + P * 0.35) > h(X + P * 0.75), true);
verif('portée calée sur les icônes, pas sur une constante',
  Math.round(P), Math.round(2.0 * 1.148 * PREFS.tile));
// Le défaut signalé : « je n'ai pas encore atteint la corbeille qu'il est déjà
// relevé ». Trois icônes de distance, ça ne doit RIEN faire.
verif('à trois icônes de distance → aucune vague',
  h(X + 3 * 1.148 * PREFS.tile), 57);

console.log('▸ l\'ENTRÉE VERTICALE : une rampe, jamais une marche');
// Le défaut signalé par l'utilisateur le 2026-07-31 : « quand je rapproche la souris du
// Dock côté poubelle ALORS QU'ELLE N'A PAS SURVOLÉ LE DOCK », le compagnon
// bondit. Deux fautes tenaient dans ce seul symptôme, et il faut un cas pour
// chacune — sinon corriger l'une laisse l'autre en place, l'air réparé.
const HAUT_RESERVE = 956 - 57;                    // 899 : la limite de workArea
const HAUT_VERRE   = HAUT_RESERVE + MARGE_VISIBLE; // 907 : là où le Dock se VOIT

// Faute n°1 — ça déclenchait sur le haut RÉSERVÉ, 8 pt au-dessus du verre.
// Ce cas rougit si quelqu'un remet le seuil sur workArea.
verif('au-dessus du verre → rien, même sous la limite réservée',
  h(X, HAUT_RESERVE + 2), 57);
verif('juste au-dessus du verre → toujours rien', h(X, HAUT_VERRE - 1), 57);

// Faute n°2 — le passage était binaire : 0 puis 91 d'un pixel à l'autre.
// On exige une VRAIE progression, pas seulement « ça finit par monter ».
const surLeVerre = (dy) => h(X, HAUT_VERRE + dy) - 57;
verif('sur le verre, la vague part de zéro', Math.round(surLeVerre(0)), 0);
verif('elle monte progressivement',
  surLeVerre(0) < surLeVerre(RAMPE_V * 0.5) && surLeVerre(RAMPE_V * 0.5) < surLeVerre(RAMPE_V), true);
verif('à mi-rampe elle est à la moitié',
  Math.round(surLeVerre(RAMPE_V / 2) / (128 - 37) * 1000) / 1000, 0.5);
verif('rampe finie → plein gonflement', surLeVerre(RAMPE_V), 128 - 37);
verif('plus bas dans le Dock → toujours le maximum', surLeVerre(RAMPE_V + 25), 128 - 37);
// ⚠ Le vrai garde-fou : AUCUN saut brutal sur toute la traversée. Un test qui
// ne regarde que trois points laisserait passer une marche placée entre eux.
let sautMax = 0;
for (let y = HAUT_VERRE - 30; y < HAUT_VERRE + 60; y++) {
  sautMax = Math.max(sautMax, Math.abs(h(X, y + 1) - h(X, y)));
}
verif('aucun bond : plus grand écart par point < 8 pt', sautMax < 8, true);

console.log('▸ ce qui doit désactiver la vague');
verif('magnification coupée → hauteur de repos',
  hauteurDockSousPoint(DOCK, ECRAN, X, {x:X,y:SUR_LE_DOCK}, {...PREFS, magnification:false}), 57);
verif('Dock masqué → rien à suivre',
  hauteurDockSousPoint({side:'bottom',size:0,visible:false}, ECRAN, X, {x:X,y:SUR_LE_DOCK}, PREFS), 0);
verif('Dock sur le côté → pas de vague verticale',
  hauteurDockSousPoint({side:'left',size:64,visible:true}, ECRAN, X, {x:X,y:SUR_LE_DOCK}, PREFS), 64);

console.log();
if (echecs === 0) { console.log('✅ géométrie ET vague : tous les cas tiennent'); process.exit(0); }
console.log(`❌ ${echecs} cas faux — le compagnon se poserait ou surferait mal`);
process.exit(1);
