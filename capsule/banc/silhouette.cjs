/* Où le mesh finit VRAIMENT, état par état — pour placer un habillage sur une
   mesure et pas à l'œil.

   ⚠ Les bornes sortent en pixels d'ÉCRAN : la capture est en retina 2×, donc
     une fenêtre de 150 rend un bitmap de 300. Diviser avant de s'en servir
     dans du CSS, sinon on place l'élément au double de la bonne distance. */
'use strict';
const { app, BrowserWindow } = require('electron');
const cp = require('child_process');
const path = require('path');

const PAGE = path.join(__dirname, '..', 'orbe.html');
const STATUS = path.join(__dirname, '..', '..', 'hooks', 'brain_status.py');
const ETATS = [['idle', 'idle'], ['challenging', 'busy'], ['correcting', 'busy'],
               ['synthesizing', 'busy'], ['committing', 'busy']];

app.setPath('userData', '/private/tmp/claude-orbe-banc-silhouette');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  const w = new BrowserWindow({
    width: 150, height: 150, show: false, frame: false, transparent: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false },
  });
  await w.loadFile(PAGE);
  await new Promise(r => setTimeout(r, 2500));
  // On mesure le MESH : tout l'habillage est masqué, sinon on relève la pastille.
  await w.webContents.executeJavaScript(
    `document.getElementById('dit').style.display='none';
     document.getElementById('pave').style.display='none'; true`);

  /* ⚠ CONTRÔLE DE MISE EN PAGE, avant toute mesure de forme.
     Une règle CSS effacée par mégarde a déjà fait poser le canvas à sa taille
     de TAMPON (300 px sur retina) dans une fenêtre de 150 : l'orbe débordait et
     tout l'habillage, centré sur la fenêtre, paraissait décalé sur le côté.
     Rien ne plante, aucun test ne rougit — ça ne se voyait que sur le bureau. */
  const geo = await w.webContents.executeJavaScript(`(() => {
    const c = document.getElementById('c');
    return { css: [c.clientWidth, c.clientHeight], fen: [innerWidth, innerHeight] }; })()`);
  const carre = geo.css[0] === geo.css[1];
  const tient = geo.css[0] === geo.fen[0] && geo.css[1] === geo.fen[1];
  console.log((carre && tient ? 'OK    ' : 'ECHEC ') +
    `canvas ${geo.css[0]}x${geo.css[1]} pour une fenêtre ${geo.fen[0]}x${geo.fen[1]}`);

  for (const [etat, st] of ETATS) {
    cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '', 'banc']
                    .filter(x => x !== ''));
    // le fondu de mécanique dure 1,4 s : capturer avant donne une forme
    // intermédiaire qui n'existe à aucun moment réel
    await new Promise(r => setTimeout(r, 2600));
    const img = await w.webContents.capturePage();
    const { width, height } = img.getSize();
    const buf = img.getBitmap();                 // BGRA, 4 octets par pixel
    let haut = height, bas = -1, gauche = width, droite = -1;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (buf[(y * width + x) * 4 + 3] > 24) {   // 24 : on ignore le halo
          if (y < haut) haut = y;
          if (y > bas) bas = y;
          if (x < gauche) gauche = x;
          if (x > droite) droite = x;
        }
      }
    }
    const css = (v) => (v / (height / 150)).toFixed(0);
    console.log(`${etat.padEnd(14)} css → haut=${css(haut)} bas=${css(bas)} ` +
                `gauche=${css(gauche)} droite=${css(droite)}`);
  }
  app.quit();
});
app.on('window-all-closed', () => app.quit());
