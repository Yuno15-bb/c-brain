/* Prouve la chaîne du glissé sans avoir à bouger une vraie souris.

   ⚠ PIÈGE QUI M'A DONNÉ UN FAUX VERT. La première version comparait la position
     de la fenêtre avant et pendant le glissé, et concluait « ça suit » si elle
     avait changé. Mais le suivi pose la fenêtre à `curseur − prise` : si le
     curseur ne bouge pas, la fenêtre ne bouge pas non plus — et c'est le
     comportement CORRECT. Le test ne passait au vert que quand la main de
     l'utilisateur bougeait par hasard pendant l'exécution. Il mesurait une
     souris humaine, pas du code.

   Ce qu'on vérifie donc vraiment :
     · un mousedown au CENTRE arme le suivi et le fait tourner ;
     · pendant le suivi, la fenêtre est exactement à `curseur − prise` ;
     · le relâché coupe le suivi ;
     · un mousedown dans un COIN n'arme RIEN (le bureau reste cliquable).
   Le dernier cas est la mutation qui rend l'ensemble crédible : sans lui, un
   `dansOrbe()` qui renverrait toujours `true` passerait pour vert. */
'use strict';
const { app, BrowserWindow, screen, ipcMain } = require('electron');
const path = require('path');

const PAGE = path.join(__dirname, '..', 'orbe.html');
app.setPath('userData', '/private/tmp/claude-orbe-banc-glisse');

let win, dragTimer = null, tours = 0, prise = null;
ipcMain.on('cap-interactive', () => {});
ipcMain.on('cap-drag-begin', () => {
  if (!win || dragTimer) return;
  const c0 = screen.getCursorScreenPoint(), b0 = win.getBounds();
  prise = { dx: c0.x - b0.x, dy: c0.y - b0.y };
  tours = 0;
  dragTimer = setInterval(() => {
    const c = screen.getCursorScreenPoint();
    win.setPosition(Math.round(c.x - prise.dx), Math.round(c.y - prise.dy));
    tours++;
  }, 16);
});
ipcMain.on('cap-drag-end', () => { clearInterval(dragTimer); dragTimer = null; });

const dire = (ok, texte) => console.log(`${ok ? 'OK    ' : 'ECHEC '} ${texte}`);

const clic = async (x, y, ms = 400) => {
  win.webContents.sendInputEvent({ type: 'mouseDown', x, y, button: 'left', clickCount: 1 });
  await new Promise(r => setTimeout(r, ms));
  const etat = { bounds: win.getBounds(), tours, arme: dragTimer !== null, prise };
  win.webContents.sendInputEvent({ type: 'mouseUp', x, y, button: 'left', clickCount: 1 });
  await new Promise(r => setTimeout(r, 200));
  return etat;
};

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  win = new BrowserWindow({
    width: 150, height: 150, x: 400, y: 400, show: true, frame: false, transparent: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });
  await win.loadFile(PAGE);
  await new Promise(r => setTimeout(r, 2500));

  // ── CENTRE : dans le disque ───────────────────────────────────────────────
  const c = await clic(75, 75);
  dire(c.arme, 'centre  : le suivi est armé');
  dire(c.tours > 10, `centre  : le suivi tourne (${c.tours} tours en 400 ms)`);
  // la fenêtre est-elle bien pilotée par le curseur ? On ne compare pas à
  // « ça a bougé » (faux positif) mais à la cible calculée.
  const cur = screen.getCursorScreenPoint();
  const visee = { x: Math.round(cur.x - c.prise.dx), y: Math.round(cur.y - c.prise.dy) };
  const colle = Math.abs(c.bounds.x - visee.x) <= 2 && Math.abs(c.bounds.y - visee.y) <= 2;
  dire(colle, `centre  : la fenêtre est à « curseur − prise » (${c.bounds.x},${c.bounds.y} vs ${visee.x},${visee.y})`);
  dire(dragTimer === null, 'relâché : le suivi est coupé');

  // ── COIN : hors du disque, rien ne doit s'armer ───────────────────────────
  const b2 = win.getBounds();
  const k = await clic(6, 6);
  dire(!k.arme, 'coin    : rien n est armé, le bureau reste cliquable');
  dire(k.bounds.x === b2.x && k.bounds.y === b2.y, 'coin    : la fenêtre n a pas bougé');
  app.quit();
});
app.on('window-all-closed', () => app.quit());
