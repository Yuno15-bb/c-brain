/* Filme l'orbe pour la démo du README.

   ⚠ TROIS PIÈGES, tous payés une fois :
     · une fenêtre CACHÉE fige les couleurs — `document.hidden` coupe
       l'interpolation, la mécanique change mais jamais la teinte ;
     · un fond en DÉGRADÉ dessine un carré visible autour de la vignette une
       fois posée dans la page — il faut la couleur exacte du fond, à plat ;
     · une étape plus courte que DEUX FOIS le fondu (1,4 s) ne montre jamais
       l'objet stable, seulement des transitions enchaînées.
   Encodage : img2webp -d 50 -lossy -q 88 -sharp_yuv -m 6. En dessous de q≈88,
   les dégradés du verre et le texte de 5 px repartent en macro-blocs.
*/
'use strict';
const { app, BrowserWindow } = require('electron');
const fs = require('fs'), path = require('path'), cp = require('child_process');

const PAGE = path.join(__dirname, '..', 'orbe.html');
const STATUS = path.join(__dirname, '..', '..', 'hooks', 'brain_status.py');
const OUT = '/tmp/film';
const ETATS = [
  // ⚠ THE FILM'S PACE IS NOT THE ORB'S PACE. First version: twelve states at
  //   1.4 s each. But the mechanic cross-fade alone lasts 1.4 s — so a stable
  //   state was never on screen, only transitions running into each other.
  //   Hence "too short and aggressive", and "you cannot feel that the scroll
  //   slowed down": the text never had time to exist.
  //   Rule: a step lasts AT LEAST twice the cross-fade. 4 s → 1.4 s of morphing,
  //   then 2.6 s where the object is simply itself.
  //   The budget comes off the NUMBER of states, never off their duration.
  ['idle', 'idle', 3000],
  ['gardening', 'busy', 4200],
  ['challenging', 'busy', 4200],
  ['synthesizing', 'busy', 4200],
  ['committing', 'busy', 4200],
  ['idle', 'idle', 3400],
];
const PAS = 50;   // ms between frames → 20 fps

app.setPath('userData', '/private/tmp/claude-orbe-film');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  // ⚠ `show: false` FREEZES THE COLOURS. The page skips its interpolation when
  //   `document.hidden` is true — by design, we do not paint for nobody. But
  //   while filming that yields a grey orb: the mechanic changes, the hue never
  //   does. Filming needs a genuinely visible window.
  const w = new BrowserWindow({
    width: 150, height: 150, show: true, frame: false, x: 60, y: 120,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false },
  });
  await w.loadFile(PAGE);
  await new Promise(r => setTimeout(r, 2500));
  await w.webContents.executeJavaScript(`(() => {
    const bg = document.createElement('div');
    bg.style.cssText = 'position:fixed;inset:0;z-index:-1;'
      // ⚠ FLAT BACKGROUND, and exactly the page's own. Even a subtle gradient
      //   draws a visible SQUARE around the demo once it sits in the README:
      //   the centre is lighter than the page, the edges are not. The seam
      //   shows. #0d1117 is GitHub's dark background, so the thumbnail
      //   dissolves into the page.
      + 'background:#0d1117';
    document.body.prepend(bg);
    document.getElementById('scene').style.zIndex = '1';
    return true; })()`);

  let n = 0;
  for (const [etat, st, duree] of ETATS) {
    cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '', 'demo']
                    .filter(x => x !== ''));
    const fin = Date.now() + duree;
    while (Date.now() < fin) {
      const img = await w.webContents.capturePage();
      fs.writeFileSync(path.join(OUT, String(n++).padStart(4, '0') + '.png'), img.toPNG());
      await new Promise(r => setTimeout(r, PAS));
    }
  }
  console.log(`${n} images dans ${OUT}`);
  app.quit();
});
app.on('window-all-closed', () => app.quit());
