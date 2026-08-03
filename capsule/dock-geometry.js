// C Brain — capsule : où est le Dock, et quelle épaisseur fait-il.
// Sorti de main.js pour être TESTABLE sans Dock réel : on ne peut pas
// demander à quelqu'un de déplacer son Dock pour faire tourner un test,
// et les cas qui comptent (masqué, à gauche, sur un autre écran) sont
// justement ceux qu'on n'a pas sous la main.
// OÙ EST LE DOCK, et quelle épaisseur fait-il.
//
// ⚠ NE PAS lire `defaults read com.apple.dock`. Vérifié le 2026-07-30 sur cette
// machine : `autohide` valait 1 alors que le système réservait quand même 57 px
// en bas. Un réglage écrit n'est pas un réglage appliqué (le Dock ne relit sa
// config qu'au redémarrage), et un compagnon posé d'après le fichier se
// retrouve dans le vide ou sous la barre d'icônes.
//
// La vérité est la différence entre `bounds` (l'écran entier) et `workArea`
// (ce que macOS laisse aux fenêtres). Elle est juste quelle que soit la
// version, la taille des icônes, la magnification ou l'agrandissement.
//
// Le côté HAUT est exclu : c'est la barre de menus, jamais le Dock.
function dockGeometry(display) {
  const b = display.bounds, w = display.workArea;
  const inset = {
    left:   w.x - b.x,
    right:  (b.x + b.width)  - (w.x + w.width),
    bottom: (b.y + b.height) - (w.y + w.height),
  };
  // Le plus épais des trois gagne. macOS n'en réserve qu'un à la fois.
  let side = 'bottom', size = inset.bottom;
  if (inset.left  > size) { side = 'left';  size = inset.left;  }
  if (inset.right > size) { side = 'right'; size = inset.right; }

  // Sous ce seuil il n'y a pas de Dock visible : soit il est masqué
  // automatiquement, soit il est sur un AUTRE écran. Dans les deux cas il n'y
  // a pas de sol — le compagnon se pose sur le bord de l'écran, et se
  // relèvera tout seul quand le Dock réapparaîtra (le poll le verra).
  const visible = size >= 8;
  return { side, size: visible ? size : 0, visible };
}


// Cloche : 1 juste sous le curseur, 0 au-delà de PORTEE. cos² donne des bords
// qui s'éteignent en douceur — une cloche à bord franc produirait une saccade
// au moment où la créature entre dans la zone d'influence.
// ⚠ 190 pt était BEAUCOUP trop large : le compagnon se relevait quatre icônes
// avant que le curseur ne l'atteigne. La vraie magnification d'Apple ne touche
// que deux à trois tuiles de part et d'autre. La portée se DÉDUIT donc de la
// taille des icônes : 2 pas, un pas valant ~1,148 × tilesize.
const PORTEE = 190;                  // valeur historique, gardée par défaut
function porteeDock(prefs) {
  return 2.0 * 1.148 * (prefs && prefs.tile ? prefs.tile : 48);
}
function bosseDock(dx, portee) {
  const p = portee || PORTEE;
  const d = Math.abs(dx);
  if (d >= p) return 0;
  const c = Math.cos((d / p) * Math.PI / 2);
  return c * c;
}

// ── L'ENTRÉE VERTICALE : UNE RAMPE, PAS UNE MARCHE ─────────────────────────
// Signalé par l'utilisateur le 2026-07-31 : « quand je rapproche la souris du Dock
// côté poubelle alors que la souris n'a pas survolé le Dock », le compagnon
// bondit d'un coup. Vérifié par le CALCUL sur les valeurs réelles de la
// machine, pas à l'œil : à y=890 le gonflement valait 0, à y=895 il valait 91
// — c'est-à-dire le maximum. La cloche HORIZONTALE était douce (cos²) ; la
// traversée VERTICALE, elle, était binaire.
//
// Deux défauts en un seul symptôme :
//  · le seuil se calait sur le haut RÉSERVÉ du Dock (y=899) alors que le verre
//    ne commence que 8 pt plus bas (y=907). D'où « elle n'a pas survolé le
//    Dock » : c'était exact — ça déclenchait 12 pt au-dessus de ce qu'on voit.
//    Cette marge existait déjà dans main.js pour POSER le compagnon ; elle
//    manquait ici pour le faire RÉAGIR. Elle vit maintenant à un seul endroit.
//  · et le passage restait une marche : 0 → maximum en un pixel.
//
// Désormais rien ne bouge tant que le curseur n'est pas sur le verre, puis la
// vague s'établit sur les 20 premiers points de sa descente dans le Dock.
const MARGE_VISIBLE = 8;   // le Dock RÉSERVE plus haut qu'il ne DESSINE
const RAMPE_V = 20;        // pt de descente sur lesquels la vague s'établit

// 0 au-dessus du verre, 1 une fois vraiment dedans, cos² entre les deux —
// la même famille d'adoucissement que la cloche horizontale, pour que les
// deux axes se ressemblent.
function facteurVertical(g, d, p) {
  const hautVisible = d.bounds.y + d.bounds.height - g.size + MARGE_VISIBLE;
  const dy = p.y - hautVisible;
  if (dy <= 0) return 0;
  if (dy >= RAMPE_V) return 1;
  const c = Math.cos((1 - dy / RAMPE_V) * Math.PI / 2);
  return c * c;
}

// Hauteur du Dock SOUS un point donné, magnification comprise. Pure : le
// curseur et les réglages entrent en paramètres, rien n'est lu ici.
function hauteurDockSousPoint(g, d, xCentre, p, prefs) {
  if (!g.visible || g.side !== 'bottom' || !prefs.magnification) return g.size;
  // La vague n'existe que si le curseur est réellement sur la bande du Dock :
  // survoler la créature elle-même, 100 pt plus haut, ne doit rien gonfler.
  const fv = facteurVertical(g, d, p);
  if (fv <= 0) return g.size;
  const gonfle = Math.max(0, prefs.large - prefs.tile);
  return g.size + gonfle * bosseDock(p.x - xCentre, porteeDock(prefs)) * fv;
}

module.exports = { dockGeometry, bosseDock, hauteurDockSousPoint, porteeDock,
                   facteurVertical, PORTEE, MARGE_VISIBLE, RAMPE_V };
