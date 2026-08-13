// LE SENS — quelles familles de travail, quelle couleur, quelle matière.
//
// C'est le SEUL fichier à réécrire pour brancher l'orbe sur un autre projet.
// Le moteur (`orbe.js`) ne connaît ni agent ni famille : il reçoit une
// mécanique et des réglages, rien d'autre.
//
// ── LE MODÈLE ─────────────────────────────────────────────────────────────
// Trois canaux, volontairement séparés :
//   · la TEINTE dit la FAMILLE de travail — quatre, pas treize. Personne ne
//     retient treize couleurs ; quatre familles s'apprennent en un jour.
//   · la MÉCANIQUE du fluide dit la NATURE de l'activité, et se lit SANS la
//     couleur (une silhouette suffit).
//   · l'INTENSITÉ de l'étape module la VITESSE, l'amplitude et la CLARTÉ —
//     jamais la teinte. On reste dans la famille.
import { hex, chromaMax } from './couleur.js';
// ⚠ DEPUIS `mecaniques.js`, PAS `orbe.js` : importer les constantes du moteur
//   ferait charger Three.js (1,27 Mo) à quiconque veut seulement les couleurs.
import { MECANIQUES } from './mecaniques.js';

// ⚠ TEINTES CHOISIES EN OKLCh, PAS EN RVB. 215° y est franchement TURQUOISE :
// une famille censée être bleue virait au vert dès que la vivacité montait, et
// se confondait avec la famille verte. Toute teinte se vérifie À L'ŒIL, rendue,
// pas sur son numéro.
export const FAMILLES = {
  repos: {
    // ⚠ chroma 0.16 donnait un BALLON GRIS : à cette fraction, le violet 268°
    // n'existe tout simplement pas à l'écran. Or le repos est l'état le plus
    // souvent affiché — c'est lui qui doit dire « Claude Brain », pas « sphère ».
    // Discret ne veut pas dire incolore : on baisse la VITESSE, pas la teinte.
    // ⚠ MÉCANIQUE CHANGÉE : `interference` → `respiration`. Avec l'interférence,
    //   le repos était une bulle quasi lisse et quasi immobile — de loin, il se
    //   confondait avec une Inspection de faible intensité, qui est lisse elle
    //   aussi. `respiration` est la seule mécanique SANS bruit : une pulsation
    //   pure. Elle donne au repos une signature de MOUVEMENT, pas de texture —
    //   et aucun état de travail ne pulse, donc la confusion disparaît même
    //   sans couleur ni libellé.
    nom: 'Repos', meca: MECANIQUES.respiration, teinte: 288, chroma: 0.50,
    // ⚠ `speed` pilote la CADENCE de la phase, et `respiration` l'utilise comme
    //   fréquence de battement : à 0.10 le cycle durait ~39 s, soit une orbe
    //   qu'on croit figée. 0.50 donne une respiration de ~8 s — visiblement
    //   vivante, jamais pressée. Sans bruit à animer, ça ne fait pas « agité ».
    // La respiration bat dans le shader, à 12 i/s (cf. CADENCE dans orbe.html) :
    // ~83 ms entre deux images, soit un déplacement bien sous le pixel par
    // image à cette amplitude. Le passer en CSS coûtait 17 % de CPU au repos.
    lent: { disp: 0.085, freq: 0.55, speed: 0.42 },
    vif:  { disp: 0.100, freq: 0.65, speed: 0.52 },
  },
  inspection: {          // il regarde, il juge, il ne change rien
    nom: 'Inspection', meca: MECANIQUES.houle, teinte: 252, chroma: 0.85,
    lent: { disp: 0.090, freq: 0.85, speed: 0.22 },
    vif:  { disp: 0.150, freq: 1.35, speed: 0.62 },
  },
  organisation: {        // il range, il classe, il déplace
    nom: 'Organisation', meca: MECANIQUES.balayage, teinte: 150, chroma: 0.85,
    lent: { disp: 0.120, freq: 0.90, speed: 0.28 },
    vif:  { disp: 0.230, freq: 1.60, speed: 0.80 },
  },
  transformation: {      // il distille, il produit
    nom: 'Transformation', meca: MECANIQUES.vortex, teinte: 300, chroma: 0.85,
    lent: { disp: 0.150, freq: 1.05, speed: 0.45 },
    vif:  { disp: 0.280, freq: 1.80, speed: 1.25 },
  },
  validation: {          // il grave, il scelle
    nom: 'Validation', meca: MECANIQUES.eclats, teinte: 50, chroma: 0.90,
    lent: { disp: 0.130, freq: 1.10, speed: 0.65 },
    vif:  { disp: 0.165, freq: 1.35, speed: 0.95 },
  },
};

// état → [famille, intensité 0→1]. C'est ici qu'on branche le vocabulaire du
// projet hôte.
export const ETATS = {
  idle:         ['repos', 0.0],
  mapping:      ['inspection', 0.10],   auditing:    ['inspection', 0.40],
  architecting: ['inspection', 0.70],   challenging: ['inspection', 1.00],
  filing:       ['organisation', 0.10], archiving:   ['organisation', 0.40],
  gardening:    ['organisation', 0.70], correcting:  ['organisation', 1.00],
  working:      ['transformation', 0.15], distilling: ['transformation', 0.60],
  synthesizing: ['transformation', 1.00],
  committing:   ['validation', 1.00],
};

const entre = (a, b, k) => a + (b - a) * k;

// ⚠ LE CONTRASTE DANS UNE FAMILLE PASSE PAR LA CLARTÉ, PAS PAR LA VIVACITÉ.
// Faire varier le seul chroma ne se voyait pas : quatre bleus identiques. La
// clarté, elle, se lit tout de suite — une étape profonde est plus sombre et
// plus dense, une étape légère plus claire.
// `part` ∈ [0,1] : quelle FRACTION de la vivacité maximale tenable on prend.
// Un chroma absolu ne marcherait pas : le maximum dépend de la clarté ET de la
// teinte, donc la même valeur saturerait ici et paraîtrait terne là.
function nuancier(teinte, part, niv) {
  const L = 0.74 - 0.20 * niv;
  const vivacite = chromaMax(L, teinte) * part;
  return {
    c1:  hex(Math.min(0.97, L + 0.30), vivacite * 0.45, teinte),  // crête
    c2:  hex(L,                        vivacite,        teinte),  // corps
    c3:  hex(0.10 + 0.06 * (1 - niv),  vivacite * 0.55, teinte),  // creux
    rim: hex(0.97,                     vivacite * 0.35, teinte),  // liseré
    rimI: 1.05 + 0.35 * niv,
  };
}

/** Réglage complet d'un état : couleurs + matière + mécanique. */
export function reglage(etat) {
  const [nomFam, niv] = ETATS[etat] || ETATS.idle;
  const f = FAMILLES[nomFam];
  // ⚠ DEUX ÉCHELLES, PAS UNE. La clarté vaut `0.74 - 0.20 × niv` : aux basses
  // intensités elle plafonne à ~0.74, et TOUT y devient un pastel délavé —
  // `working` (0.15) ressemblait à un lavande passé, sa mécanique invisible.
  // La MATIÈRE doit rester lente à basse intensité, la COULEUR non : elle a
  // besoin d'un plancher pour rester une couleur. D'où un niveau distinct,
  // utilisé pour le nuancier uniquement — disp/freq/speed gardent le vrai `niv`.
  const nivCouleur = Math.max(niv, 0.50);
  return {
    ...nuancier(f.teinte, f.chroma * (0.72 + 0.28 * nivCouleur), nivCouleur),
    disp:  entre(f.lent.disp,  f.vif.disp,  niv),
    freq:  entre(f.lent.freq,  f.vif.freq,  niv),
    speed: entre(f.lent.speed, f.vif.speed, niv),
    meca:  f.meca,
    famille: nomFam, nomFamille: f.nom, intensite: niv,
  };
}

export function listeEtats() { return Object.keys(ETATS); }
