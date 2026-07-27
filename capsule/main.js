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

// --- Watcher de state/status.json : la capsule se re-montre quand un agent
//     se réveille (idle -> busy), même si elle avait été cachée. -----------
// DÉRIVÉ DE $HOME, jamais de __dirname : le moteur peut vivre ailleurs que le
// tronc (installation par symlinks), et c'est le state de l'UTILISATEUR qu'on
// surveille. Même chemin que celui utilisé par index.html.
const STATUS = path.join(os.homedir(), '.c-brain', 'trunk', 'state', 'status.json');
let lastState = 'idle';
function watchStatus() {
  const poll = () => {
    let s = 'idle';
    try { s = (JSON.parse(fs.readFileSync(STATUS, 'utf8')).state) || 'idle'; } catch (e) {}
    if (s === 'busy' && lastState !== 'busy' && win && !win.isVisible()) {
      win.showInactive();                  // surface sans voler le focus du travail en cours
    }
    lastState = s;
  };
  fs.watchFile(STATUS, { interval: 2000 }, poll);   // V22 : 1000→2000 ms, le renderer poll déjà status.json
  poll();
}

// --- V22 — Mode veille : écran éteint / session verrouillée / batterie faible → la capsule
//     se cache réellement (document.hidden côté renderer → boucle en pause). Sans ça elle
//     continue d'animer et de faire recomposer WindowServer devant un écran noir. ---------
let _hiddenByPower = false;
function powerSleep() {
  if (win && win.isVisible()) { _hiddenByPower = true; win.hide(); }
}
function powerWake() {
  if (win && _hiddenByPower) { _hiddenByPower = false; win.showInactive(); }
}
function watchPower() {
  ['suspend', 'lock-screen'].forEach(e => powerMonitor.on(e, powerSleep));
  ['resume', 'unlock-screen'].forEach(e => powerMonitor.on(e, powerWake));
  // macOS ne verrouille pas toujours : on suit aussi l'extinction de l'écran.
  if (powerMonitor.on) {
    powerMonitor.on('screen-locked', powerSleep);
    powerMonitor.on('screen-unlocked', powerWake);
  }
}

function createWindow() {
  const { workAreaSize } = screen.getPrimaryDisplay();
  const W = 190, H = 306, M = 20;
  win = new BrowserWindow({
    width: W,
    height: H,
    x: workAreaSize.width - W - M,
    y: workAreaSize.height - H - M,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    fullscreenable: false,
    // backgroundThrottling:false → la capsule est un HUD JAMAIS focus (showInactive) ; sans ça Electron
    //   bride le requestAnimationFrame à ~quelques fps quand la fenêtre n'a pas le focus → animation
    //   « extrêmement saccadée ». On le désactive pour garder un rendu fluide en permanence.
    webPreferences: { nodeIntegration: true, contextIsolation: false, backgroundThrottling: false },
  });
  win.webContents.setBackgroundThrottling(false);
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.loadFile('index.html');
}

app.whenReady().then(() => {
  createWindow();
  watchStatus();   // re-montre la capsule dès qu'un agent passe en 'busy'
  watchPower();    // V22 : pause réelle quand l'écran dort ou que la session est verrouillée
  // --- Hot-reload : la page se recharge à chaque modif d'index.html (persistance des changements en direct).
  //     V22 — opt-in : c'est un confort de DÉVELOPPEMENT, pas une fonction de la capsule. En usage normal
  //     il faisait un stat() disque toutes les 400 ms à vie pour un fichier qui ne bouge jamais.
  //     Activer avec : CAPSULE_DEV=1 npx electron .
  if (process.env.CAPSULE_DEV === '1') {
    const PAGE = path.join(__dirname, 'index.html');
    fs.watchFile(PAGE, { interval: 1000 }, () => { if (win) win.webContents.reloadIgnoringCache(); });
  }
  // ⌘⇧B : montrer / cacher
  globalShortcut.register('CommandOrControl+Shift+B', () => {
    if (!win) return;
    win.isVisible() ? win.hide() : win.showInactive();
  });
});

// pilotage depuis la capsule (renderer)
ipcMain.on('cap-show', () => { if (win && !win.isVisible()) win.showInactive(); }); // sans voler le focus
ipcMain.on('cap-hide', () => { if (win && win.isVisible()) win.hide(); });
ipcMain.on('cap-quit', () => app.quit());

// debug : capture la fenêtre dans un PNG (déclenché par un fichier /tmp/cap_shot_req)
async function shot(dest) {
  if (!win) return;
  try { const img = await win.webContents.capturePage();
    fs.writeFileSync(dest, img.toPNG()); } catch (e) {}
}
ipcMain.on('cap-shot', (_e, dest) => shot(dest));
// V22 — capture de debug : opt-in aussi (CAPSULE_DEV=1). Le watchFile tournait à 300 ms en permanence
//   pour un fichier qui n'apparaît qu'en session d'audit visuel.
if (process.env.CAPSULE_DEV === '1') {
  const SHOT_REQ = '/tmp/cap_shot_req';
  fs.watchFile(SHOT_REQ, { interval: 1000 }, () => {
    if (fs.existsSync(SHOT_REQ)) { try { fs.unlinkSync(SHOT_REQ); } catch(e){} shot('/tmp/cap.png'); }
  });
}

app.on('window-all-closed', () => app.quit());
app.on('will-quit', () => globalShortcut.unregisterAll());
