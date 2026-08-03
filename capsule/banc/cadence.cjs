/* Cadence RÉELLE, par état, mesurée sur les intervalles entre images.

   ⚠ On ne juge JAMAIS la fluidité à l'œil, et on ne se fie pas non plus à la
     cadence demandée : `setCadence(30)` dit ce qu'on VEUT, pas ce qu'on obtient.
     Ici on instrumente la boucle de rendu et on lit les intervalles réels —
     moyenne ET pire cas, car c'est le pire cas qui se voit.

   La capsule n'est PAS à 60 i/s partout, et c'est un choix : 60 i/s en
   permanence coûtait ~12 % de CPU à vie pour un objet qu'on ne regarde pas.
   Ce script sert à vérifier que chaque état tient la cadence qu'il a choisie. */
'use strict';
const { app, BrowserWindow } = require('electron');
const cp = require('child_process');
const path = require('path');

const PAGE = path.join(__dirname, '..', 'orbe.html');
const STATUS = path.join(__dirname, '..', '..', 'hooks', 'brain_status.py');
const CAS = [['idle', 'idle', 12], ['gardening', 'busy', 30], ['synthesizing', 'busy', 30]];

app.setPath('userData', '/private/tmp/claude-orbe-banc-cadence');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  const w = new BrowserWindow({
    width: 150, height: 150, show: true, frame: false, transparent: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false },
  });
  await w.loadFile(PAGE);
  await new Promise(r => setTimeout(r, 2500));

  // On se greffe sur le rendu réel : chaque appel de `render` du moteur passe
  // par requestAnimationFrame, donc on horodate là où les images sortent.
  await w.webContents.executeJavaScript(`(() => {
    window.__t = [];
    const raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = (cb) => raf((ts) => { window.__t.push(performance.now()); cb(ts); });
    return true; })()`);

  console.log('état          demandé   réelle    médian     pire     images');
  for (const [etat, st, voulu] of CAS) {
    cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '', 'cadence']
                    .filter(x => x !== ''));
    // on laisse passer le fondu de mécanique (1,4 s) : il monte à 60 i/s
    await new Promise(r => setTimeout(r, 3000));
    await w.webContents.executeJavaScript('window.__t = []; true');
    const DUREE = 6000;
    await new Promise(r => setTimeout(r, DUREE));
    const t = await w.webContents.executeJavaScript('window.__t');
    const dts = t.slice(1).map((v, i) => v - t[i]).sort((a, b) => a - b);
    if (!dts.length) { console.log(`${etat.padEnd(13)} aucune image`); continue; }
    const med = dts[Math.floor(dts.length / 2)];
    const pire = dts[dts.length - 1];
    const reel = (t.length - 1) / (DUREE / 1000);
    console.log(`${etat.padEnd(13)} ${String(voulu).padStart(4)} i/s ` +
                `${reel.toFixed(1).padStart(6)} i/s ${med.toFixed(1).padStart(7)} ms ` +
                `${pire.toFixed(1).padStart(7)} ms ${String(t.length).padStart(6)}`);
  }

  // La TRANSITION est le seul moment qui exige 60 i/s : en dessous, le fondu de
  // mécanique avance par crans et se lit comme une saccade.
  cp.execFileSync('python3', [STATUS, 'busy', 'committing', 'cadence']);
  await w.webContents.executeJavaScript('window.__t = []; true');
  await new Promise(r => setTimeout(r, 1400));
  const tt = await w.webContents.executeJavaScript('window.__t');
  const d = tt.slice(1).map((v, i) => v - tt[i]).sort((a, b) => a - b);
  console.log(`transition      60 i/s ${((tt.length - 1) / 1.4).toFixed(1).padStart(6)} i/s ` +
              `${d.length ? d[Math.floor(d.length / 2)].toFixed(1).padStart(7) : '   —'} ms ` +
              `${d.length ? d[d.length - 1].toFixed(1).padStart(7) : '   —'} ms`);
  app.quit();
});
app.on('window-all-closed', () => app.quit());
