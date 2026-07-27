const { app, BrowserWindow, screen, globalShortcut, ipcMain, powerMonitor } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');

let win;

// --- Single instance: one capsule only, never zombie windows ------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {       // un 2e lancement → on re-montre l'existante
    if (win) { win.showInactive(); }
  });
}

// --- Watcher de state/status.json : la capsule se re-montre quand un agent
//     wakes up (idle -> busy), even if it had been hidden. -----------
// DERIVED FROM $HOME, never from __dirname: the engine can live elsewhere than the
// tronc (installation par symlinks), et c'est le state de l'UTILISATEUR qu'on
// watching. The same path index.html uses.
const STATUS = path.join(os.homedir(), 'claude-brain', 'state', 'status.json');
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
  fs.watchFile(STATUS, { interval: 2000 }, poll);   // 1000→2000 ms; the renderer already polls status.json
  poll();
}

// --- Sleep mode: screen off / session locked / low battery → the capsule
//     really hides (document.hidden on the renderer side → the loop pauses). Without this it
//     keeps animating and forcing WindowServer to recompose in front of a black screen. ------
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
  // macOS does not always lock: we also follow the screen going dark.
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
    // backgroundThrottling:false → the capsule is a HUD that NEVER takes focus (showInactive); without this Electron
    //   throttles requestAnimationFrame to a few fps when the window is unfocused → an
    //   "extremely stuttering" animation. We disable it to keep a smooth render at all times.
    webPreferences: { nodeIntegration: true, contextIsolation: false, backgroundThrottling: false },
  });
  win.webContents.setBackgroundThrottling(false);
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.loadFile('index.html');
}

app.whenReady().then(() => {
  createWindow();
  watchStatus();   // re-shows the capsule as soon as an agent goes 'busy'
  watchPower();    // a real pause when the screen sleeps or the session is locked
  // --- Hot reload: the page reloads on every change to index.html (live editing).
  //     Opt-in: this is a DEVELOPMENT convenience, not a capsule feature. In normal use
  //     it did a disk stat() every 400 ms forever, for a file that never changes.
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

// debug: captures the window into a PNG (triggered by a /tmp/cap_shot_req file)
async function shot(dest) {
  if (!win) return;
  try { const img = await win.webContents.capturePage();
    fs.writeFileSync(dest, img.toPNG()); } catch (e) {}
}
ipcMain.on('cap-shot', (_e, dest) => shot(dest));
// The debug capture is opt-in too (CAPSULE_DEV=1). The watchFile ran at 300 ms forever
//   for a file that only appears during a visual audit session.
if (process.env.CAPSULE_DEV === '1') {
  const SHOT_REQ = '/tmp/cap_shot_req';
  fs.watchFile(SHOT_REQ, { interval: 1000 }, () => {
    if (fs.existsSync(SHOT_REQ)) { try { fs.unlinkSync(SHOT_REQ); } catch(e){} shot('/tmp/cap.png'); }
  });
}

app.on('window-all-closed', () => app.quit());
app.on('will-quit', () => globalShortcut.unregisterAll());
