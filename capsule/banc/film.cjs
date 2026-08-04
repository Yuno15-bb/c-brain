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
  // ⚠ LE RYTHME DU FILM N'EST PAS LE RYTHME DE L'ORBE. Première version : douze
  //   états à 1,4 s. Or le FONDU de mécanique dure 1,4 s à lui seul — on ne
  //   voyait donc jamais un état stable, seulement des transitions enchaînées.
  //   D'où « trop court et agressif », et « on ne sent pas que le défilement a
  //   ralenti » : le texte n'a jamais le temps d'exister.
  //   Règle : une étape doit durer AU MOINS deux fois le fondu. 4 s → 1,4 s de
  //   morphing puis 2,6 s où l'objet est simplement lui-même.
  //   Le budget se prend sur le NOMBRE d'états, jamais sur leur durée.
  ['idle', 'idle', 3000],
  ['gardening', 'busy', 4200],
  ['challenging', 'busy', 4200],
  ['synthesizing', 'busy', 4200],
  ['committing', 'busy', 4200],
  ['idle', 'idle', 3400],
];
const PAS = 50;   // ms entre deux images → 20 i/s

app.setPath('userData', '/private/tmp/claude-orbe-film');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  // ⚠ `show: false` FIGE LES COULEURS. La page saute son interpolation quand
  //   `document.hidden` est vrai — c'est voulu, on ne peint pas pour personne.
  //   Mais en tournage ça donne une orbe grise : la mécanique change, la teinte
  //   jamais. Il faut donc une fenêtre RÉELLEMENT visible pour filmer.
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
      // ⚠ FOND PLAT, ET EXACTEMENT celui de la page. Un dégradé, même discret,
      //   dessine un CARRÉ visible autour de la démo une fois posée dans le
      //   README : le centre est plus clair que la page, les bords non. Le
      //   raccord se voit, et c'est ce qui fait « bâclé ». #0d1117 = le fond de
      //   GitHub en thème sombre, donc la vignette disparaît dans la page.
      + 'background:#0d1117';
    document.body.prepend(bg);
    /* ⚠ MÊME PIÈGE QUE planche.cjs, trouvé le 2026-08-04 : monter #scene en
       z-index:1 fait passer le canvas DEVANT le pavé de code et le libellé.
       La vignette publiée jusqu'ici montrait donc une orbe MUETTE — le
       défilement du code, qui est la moitié de l'intérêt, n'y a jamais été
       filmé. Le fond suffit avec son z-index:-1 ; on remonte explicitement
       les deux surcouches. */
    document.getElementById('scene').style.zIndex = '0';
    document.getElementById('pave').style.zIndex = '2';
    document.getElementById('dit').style.zIndex = '2';
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
