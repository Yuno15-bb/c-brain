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
// ⚠ LE PAVÉ SE NOURRIT PAR SON ENTRÉE, PAS PAR UNE POIGNÉE. Première tentative :
//   une fonction exposée sur `window` pour poser les lignes. Elle a écrasé
//   `window.__orbe`, déjà pris par l'objet orbe (planche.cjs et silhouette.cjs
//   s'en servent), puis elle s'est fait repeindre par le lecteur de flux une
//   seconde plus tard. On écrit donc un VRAI fichier de session, au format que
//   la page lit déjà : même chemin de code que sur un vrai bureau, rien à
//   maintenir dans la page, et le tournage prouve du même coup que ce chemin
//   marche. Le fichier est supprimé à la fin.
//
//   Pourquoi c'est nécessaire : le pavé montre le code RÉELLEMENT écrit par la
//   session en cours. Parfait sur le bureau de quelqu'un, impubliable dans un
//   README — la vignette en ligne a montré pendant deux semaines du français
//   tiré des fichiers de l'auteur.
const FLUX_DIR = path.join(require('os').homedir(), '.claude', 'companion', 'sessions');
const FLUX_FAUX = path.join(FLUX_DIR, 'zzz-film-demo.jsonl');
const DIFFS = [
  ['src/recall.py', ['+ def rank(q, notes):', '+   hits = bm25(q, notes)', '+   return hits[:5]',
                     '- # TODO: sort later', '+ log.debug("ranked")']],
  ['tests/test_recall.py', ['+ def test_empty():', '+   assert rank("", []) == []',
                            '+ def test_order():', '+   r = rank("cache", corpus)',
                            '+   assert r[0].id == "cache-lies"']],
  ['src/store.py', ['- notes = load_all()', '+ notes = load_page(offset)', '+ index.refresh()']],
  ['docs/recall.md', ['+ ## Ranking', '+ BM25 over title and tags.', '- Sorted by mtime.']],
  ['src/api.py', ['+ @route("/search")', '+ def search(q):', '+   return rank(q, store.all())']],
];
function poserFluxFictif() {
  fs.mkdirSync(FLUX_DIR, { recursive: true });
  fs.writeFileSync(FLUX_FAUX, DIFFS.map(([rel, diff]) =>
    JSON.stringify({ type: 'diff', rel, diff })).join('\n') + '\n');
}
const ETATS = [
  // ⚠ LE RYTHME DU FILM N'EST PAS LE RYTHME DE L'ORBE. Première version : douze
  //   états à 1,4 s. Or le FONDU de mécanique dure 1,4 s à lui seul — on ne
  //   voyait donc jamais un état stable, seulement des transitions enchaînées.
  //   Règle : une étape doit durer AU MOINS deux fois le fondu.
  //   Le budget se prend sur le NOMBRE d'états, jamais sur leur durée.
  // ⚠ `synthesizing` écarté à la demande de l'auteur.
  // Le troisième champ est le DÉTAIL affiché sous l'état : il vaut un sujet
  // fictif, pas « demo ». Un mot de débogage sous une vignette de README se lit
  // comme un oubli, et c'est ce qu'il est.
  // ⚠ LA DURÉE SE PAIE EN OCTETS, ET LA QUALITÉ N'EST PAS NÉGOCIABLE : le verre
  //   repart en macro-blocs sous q≈88 (voir l'en-tête). À 45 i/s et q90, chaque
  //   seconde coûte ~300 Ko dans le README — donc on coupe des SECONDES, jamais
  //   la qualité. Le plancher reste « deux fois le fondu », soit 3 s.
  ['idle',        'idle', 2000, ''],
  ['gardening',   'busy', 3200, 'filing three new notes'],
  ['committing',  'busy', 3200, 'one zone per commit'],
  ['idle',        'idle', 2200, ''],
];
// ⚠ NI `PAS`, NI `capturePage()`. Un aller-retour de capture coûte ~50 ms : la
//   boucle plafonnait à 20 i/s, et l'auteur l'a vue saccader à côté de la carte,
//   filmée à 45. On passe par le SCREENCAST du protocole de débogage, qui pousse
//   les images au rythme du rendu au lieu de les demander une par une.
// ⚠ ET ON SUR-ÉCHANTILLONNE : fenêtre 3× plus grande + `setZoomFactor(3)`, donc
//   la mise en page reste 150×150 en pixels CSS mais elle est RENDUE en 450×450.
//   Réduite ensuite à 336 px, elle est lissée. Sans ça, le bord du verre sort en
//   marches d'escalier — « pixélisé sur les bords », constaté sur la vignette
//   publiée, qui était captée à la taille d'affichage.
const ZOOM = 3;
const COTE = 150;

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
    width: COTE * ZOOM, height: COTE * ZOOM, show: true, frame: false, x: 60, y: 120,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false, zoomFactor: ZOOM },
  });
  poserFluxFictif();          // AVANT le chargement : la page lit dès sa première passe
  await w.loadFile(PAGE);
  w.webContents.setZoomFactor(ZOOM);
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

  // ⚠ LE SEUL TÉMOIN QUI COMPTE EST LE TEXTE À L'ÉCRAN. La valeur rendue par
  //   l'injection a été un `NaN` inexplicable pendant trois essais, et pendant ce
  //   temps la vraie question — « qu'est-ce qui est écrit dans le pavé ? » — avait
  //   une réponse simple et directe. On lit les fentes, on cherche du français, on
  //   cherche un mot qu'on vient d'injecter. Ni l'un ni l'autre ne se devine.
  await new Promise(r => setTimeout(r, 1800));    // le rouleau doit avoir défilé
  const lu = await w.webContents.executeJavaScript(
    `[...document.querySelectorAll('#pave .l')].map(e=>e.textContent).join(' ')`);
  if (/[àâçéèêëîïôùûœ]/i.test(lu)) {
    console.error(`⛔ du français dans le pavé : « ${lu.replace(/\s+/g,' ').trim().slice(0, 90)} »`);
    app.exit(5); return;
  }
  if (!/rank|bm25|recall|store|search/i.test(lu)) {
    console.error(`⛔ les lignes du banc ne sont pas à l'écran : « ${lu.replace(/\s+/g,' ').trim().slice(0, 90)} »`);
    app.exit(6); return;
  }
  console.log(`  pavé : en anglais, lignes du banc — « ${lu.replace(/\s+/g,' ').trim().slice(0, 46)}… »`);

  // Le screencast : on attache le débogueur, on écoute, on acquitte chaque image.
  // Sans l'acquittement, Chromium cesse d'en envoyer au bout de quelques-unes.
  const dbg = w.webContents.debugger;
  dbg.attach('1.3');
  const images = [];
  dbg.on('message', (_e, methode, params) => {
    if (methode !== 'Page.screencastFrame') return;
    images.push(params.data);
    dbg.sendCommand('Page.screencastFrameAck', { sessionId: params.sessionId }).catch(() => {});
  });
  await dbg.sendCommand('Page.enable');
  await dbg.sendCommand('Page.startScreencast',
    { format: 'png', maxWidth: COTE * ZOOM, maxHeight: COTE * ZOOM, everyNthFrame: 1 });

  const t0 = Date.now();
  for (const [etat, st, duree, detail] of ETATS) {
    cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '', detail]
                    .filter(x => x !== ''));
    await new Promise(r => setTimeout(r, duree));
  }
  await dbg.sendCommand('Page.stopScreencast');
  const secondes = (Date.now() - t0) / 1000;
  images.forEach((b64, i) =>
    fs.writeFileSync(path.join(OUT, String(i).padStart(4, '0') + '.png'), Buffer.from(b64, 'base64')));
  const ips = Math.round(images.length / secondes);
  fs.rmSync(FLUX_FAUX, { force: true });
  console.log(`${images.length} images en ${secondes.toFixed(1)} s → ${ips} i/s, ${COTE * ZOOM}px, dans ${OUT}`);
  // Un film de 20 i/s à côté d'une carte à 45 se voit tout de suite : on refuse.
  if (ips < 35) console.error(`⛔ ${ips} i/s — trop lent. La fenêtre est-elle vraiment visible ?`);
  app.quit();
});
app.on('window-all-closed', () => app.quit());
