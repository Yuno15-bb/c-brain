// C Brain — la capsule : l'ORBE.
//
// Une matière de verre posée dans le coin bas droit de l'écran. Sa mécanique de
// fluide dit la NATURE du travail en cours, sa vitesse l'INTENSITÉ, sa teinte la
// FAMILLE d'agent — et le code réellement écrit défile à l'intérieur.
//
// ⚠ CE FICHIER N'EST PAS SYNCHRONISÉ depuis le tronc de l'auteur (cf. sync.sh).
//   La version privée porte une géométrie de Dock spécifique à sa machine :
//   position assise sur le Dock, vague au survol, magnification. Rien de tout
//   cela n'a de sens sur la machine de quelqu'un d'autre. Ici l'orbe vit
//   simplement dans le coin bas droit, et on peut la déplacer à la souris.
//   Toute correction faite là-bas doit donc être PORTÉE ici à la main.
const { app, BrowserWindow, screen, globalShortcut, ipcMain, powerMonitor } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');

let win;

// --- Single-instance : une seule capsule, jamais de fenêtres zombies ------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {       // un 2e lancement → on re-montre l'existante
    if (win) { win.showInactive(); }
  });
}

// L'orbe occupe un carré. 150 px : assez pour que la matière se lise et que le
// code qui défile à l'intérieur reste du texte, assez peu pour ne pas manger le
// coin de l'écran.
const TAILLE = 150;
const MARGE  = 26;

// DÉRIVÉ DE $HOME, jamais de __dirname : le moteur peut vivre ailleurs que le
// tronc (installation par symlinks), et c'est le state de l'UTILISATEUR qu'on
// surveille. Même chemin que celui utilisé par orbe.html.
const STATUS = path.join(os.homedir(), '.c-brain', 'trunk', 'state', 'status.json');

// L'orbe s'efface d'elle-même quand plus rien ne travaille : un indicateur qui
// ne dit rien ne doit pas occuper l'écran. Elle revient au premier agent.
// Une minute de présence après la fin du travail — assez pour qu'on ait le
// temps de regarder ce qui vient de se passer.
const REPOS_AVANT_EFFACEMENT = 60000;
// Même garde de fraîcheur que le renderer : `status.json` peut rester sur
// « busy » avec un horodatage périmé si un agent meurt brutalement.
const PERIME = 30000;
let reposDepuis = null;

function watchStatus() {
  const poll = () => {
    let s = 'idle', ts = 0;
    try {
      const j = JSON.parse(fs.readFileSync(STATUS, 'utf8'));
      s = j.state || 'idle'; ts = j.ts || 0;
    } catch (e) {}
    const frais = (Date.now() / 1000 - ts) * 1000 < PERIME;
    const occupe = s === 'busy' && frais;

    if (occupe) {
      reposDepuis = null;
      if (win && !win.isVisible()) win.showInactive();   // sans voler le focus
    } else if (win) {
      if (reposDepuis === null) reposDepuis = Date.now();
      if (Date.now() - reposDepuis > REPOS_AVANT_EFFACEMENT && win.isVisible()) win.hide();
    }
  };
  // ⚠ `fs.watchFile` ne se déclenche qu'au CHANGEMENT du fichier. Le délai
  //   d'inactivité, lui, doit être réévalué même quand plus rien ne bouge —
  //   sinon l'orbe ne se cache jamais. Il faut donc aussi un vrai minuteur.
  fs.watchFile(STATUS, { interval: 2000 }, poll);   // réaction immédiate au réveil
  setInterval(poll, 1500);                          // écoulement du temps de repos
  poll();
}

// --- Veille : écran éteint / session verrouillée → l'orbe se cache vraiment.
//     Sans ça elle continue d'animer et de faire recomposer le bureau devant un
//     écran noir.
let _cacheeParVeille = false;
function powerSleep() {
  if (win && win.isVisible()) { _cacheeParVeille = true; win.hide(); }
}
function powerWake() {
  if (win && _cacheeParVeille) { _cacheeParVeille = false; win.showInactive(); }
}
function watchPower() {
  ['suspend', 'lock-screen'].forEach(e => powerMonitor.on(e, powerSleep));
  ['resume', 'unlock-screen'].forEach(e => powerMonitor.on(e, powerWake));
  if (powerMonitor.on) {
    powerMonitor.on('screen-locked', powerSleep);
    powerMonitor.on('screen-unlocked', powerWake);
  }
}

// --- Le clic traverse, SAUF sur l'orbe ------------------------------------
// Un carré de 150 px posé sur le bureau qui avale les clics serait insupportable.
// `forward: true` laisse quand même remonter les mouvements de souris : la page
// sait donc dire « là, c'est moi » et ne redevient cliquable que sur le disque.
function setClickThrough(on) {
  if (!win) return;
  try { win.setIgnoreMouseEvents(on, { forward: true }); } catch (e) {}
}
ipcMain.on('cap-interactive', (_e, interactive) => setClickThrough(!interactive));

// --- Attraper l'orbe et la déplacer ---------------------------------------
// ⚠ Le curseur est suivi ICI, dans le processus principal, et pas dans la page.
//   En glissant vite, le pointeur sort de la fenêtre : le renderer cesse alors
//   de recevoir les mouvements et l'orbe resterait plantée en arrière du geste.
//   `screen.getCursorScreenPoint()` reste juste où que soit le curseur.
let posLibre = false;      // l'utilisateur l'a déplacée : on ne la replace plus
let suivi = null;

ipcMain.on('cap-drag-begin', () => {
  if (!win || suivi) return;
  posLibre = true;
  const c0 = screen.getCursorScreenPoint();
  const b0 = win.getBounds();
  // Écart entre le coin de la fenêtre et le point saisi : sans lui, l'orbe
  // sauterait pour se centrer sous le curseur au premier pixel de mouvement.
  const dx = c0.x - b0.x, dy = c0.y - b0.y;
  suivi = setInterval(() => {
    if (!win) return;
    const c = screen.getCursorScreenPoint();
    win.setPosition(Math.round(c.x - dx), Math.round(c.y - dy));
  }, 16);
});

ipcMain.on('cap-drag-end', () => {
  if (suivi) { clearInterval(suivi); suivi = null; }
  garderAVue();
});

// Au lâcher et à chaque changement d'écran : on ramène la fenêtre dans la zone
// visible. Sans ça, une orbe lâchée sur un écran qu'on débranche reste posée
// dans le vide — elle existe, elle consomme, et elle est introuvable.
function garderAVue() {
  if (!win) return;
  const b = win.getBounds();
  const wa = screen.getDisplayMatching(b).workArea;
  const RESTE = 24;                     // ce bout d'orbe reste toujours à l'écran
  const x = Math.min(Math.max(b.x, wa.x - b.width + RESTE), wa.x + wa.width - RESTE);
  const y = Math.min(Math.max(b.y, wa.y), wa.y + wa.height - RESTE);
  if (x !== b.x || y !== b.y) win.setPosition(Math.round(x), Math.round(y));
}

function poser() {
  if (!win) return;
  if (posLibre) return garderAVue();     // l'utilisateur a choisi sa place
  const b = screen.getPrimaryDisplay().bounds;
  win.setPosition(b.x + b.width - TAILLE - MARGE, b.y + b.height - TAILLE - MARGE);
}

function createWindow() {
  const b = screen.getPrimaryDisplay().bounds;
  win = new BrowserWindow({
    width: TAILLE,
    height: TAILLE,
    x: b.x + b.width - TAILLE - MARGE,
    y: b.y + b.height - TAILLE - MARGE,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    fullscreenable: false,
    // backgroundThrottling:false → la capsule est un HUD qui n'a JAMAIS le focus
    //   (showInactive) ; sans ça Electron bride le rendu à quelques images par
    //   seconde dès qu'elle n'est pas au premier plan, et l'animation saccade.
    webPreferences: { nodeIntegration: true, contextIsolation: false, backgroundThrottling: false },
  });
  win.webContents.setBackgroundThrottling(false);
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.loadFile('orbe.html');
  // Le clic traverse DÈS LE DÉPART : entre le premier rendu et le premier
  // survol, la fenêtre est un rectangle transparent posé sur le bureau.
  // Attendre le premier mouvement de souris laisserait une zone morte au
  // moment précis où l'utilisateur découvre la chose.
  setClickThrough(true);
  // La page met son animation en pause quand personne ne la voit : peindre pour
  // un écran éteint ferait recomposer le bureau pour rien.
  const direVisible = (v) => { try { win.webContents.send('cap-visible', v); } catch (e) {} };
  win.on('show', () => direVisible(true));
  win.on('hide', () => direVisible(false));
}

app.whenReady().then(() => {
  createWindow();
  ['display-metrics-changed', 'display-added', 'display-removed']
    .forEach(e => screen.on(e, poser));
  watchStatus();   // re-montre l'orbe dès qu'un agent passe en 'busy'
  watchPower();    // pause réelle quand l'écran dort ou que la session est verrouillée

  // Rechargement à chaud — opt-in : c'est un confort de DÉVELOPPEMENT, pas une
  // fonction de la capsule. En usage normal il ferait un accès disque toutes
  // les secondes, à vie, pour un fichier qui ne bouge jamais.
  if (process.env.CAPSULE_DEV === '1') {
    const PAGE = path.join(__dirname, 'orbe.html');
    fs.watchFile(PAGE, { interval: 1000 }, () => { if (win) win.webContents.reloadIgnoringCache(); });
  }
  // ⌘⇧B : montrer / cacher
  globalShortcut.register('CommandOrControl+Shift+B', () => {
    if (!win) return;
    win.isVisible() ? win.hide() : win.showInactive();
  });
});

// pilotage depuis la page
ipcMain.on('cap-show', () => { if (win && !win.isVisible()) win.showInactive(); });
ipcMain.on('cap-hide', () => { if (win && win.isVisible()) win.hide(); });
ipcMain.on('cap-quit', () => app.quit());

app.on('window-all-closed', () => app.quit());
app.on('will-quit', () => globalShortcut.unregisterAll());
