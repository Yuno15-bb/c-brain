/* Planche comparative de l'orbe : un état par colonne, sur un FAUX BUREAU.

   ⚠ LE VERRE NE SE JUGE PAS SUR FOND NOIR. Sur du noir, un objet transparent
     est indiscernable d'un objet opaque — la planche est jolie et ne prouve
     rien. D'où le dégradé et le texte posés derrière : c'est ce qu'il y a
     vraiment sous la capsule, un bureau qu'on est censé voir à travers.

   Usage :  ./node_modules/.bin/electron banc/planche.cjs [dosages]
   ex.   :  ... banc/planche.cjs 1 0.55 0     → trois rangées comparables      */
'use strict';
const { app, BrowserWindow } = require('electron');
const fs = require('fs'), path = require('path'), cp = require('child_process');

const PAGE = path.join(__dirname, '..', 'orbe.html');
const STATUS = path.join(__dirname, '..', '..', 'hooks', 'brain_status.py');
const SORTIE = process.env.BANC_SORTIE || '/tmp/orbe-banc';
const DOSAGES = process.argv.slice(2).filter(a => !isNaN(parseFloat(a)))
                  .map(Number);
const VERRES = DOSAGES.length ? DOSAGES : [0.55];
const ETATS = [['idle', 'idle'], ['challenging', 'busy'], ['correcting', 'busy'],
               ['synthesizing', 'busy'], ['committing', 'busy']];

app.setPath('userData', '/private/tmp/claude-orbe-banc-planche');

app.whenReady().then(async () => {
  if (app.dock) app.dock.hide();
  fs.mkdirSync(SORTIE, { recursive: true });
  const w = new BrowserWindow({
    width: 150, height: 150, show: false, frame: false,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false },
  });
  await w.loadFile(PAGE);
  await new Promise(r => setTimeout(r, 2500));

  /* ⚠ TROIS FONDS, PAS UN. Le cas qu'aucune planche ne prouvait était le bureau
     presque BLANC : un objet de verre y perd son liseré, et un libellé clair y
     disparaît. Un fond sombre flatte tout, un fond coloré ment sur les teintes
     voisines, seul le fond clair dit la vérité sur la lisibilité. */
  const FONDS = {
    bureau: ['linear-gradient(135deg,#1d4ed8,#7c3aed 45%,#f59e0b)', 'rgba(255,255,255,.9)'],
    clair:  ['linear-gradient(135deg,#fdfdfd,#eef1f6 55%,#e7e2d8)', 'rgba(20,24,32,.75)'],
    sombre: ['linear-gradient(135deg,#0b0d12,#141922)',             'rgba(255,255,255,.55)'],
  };
  const poserFond = (nom) => w.webContents.executeJavaScript(`(() => {
    document.getElementById('fondBanc')?.remove();
    const bg = document.createElement('div');
    bg.id = 'fondBanc';
    bg.style.cssText = 'position:fixed;inset:0;z-index:-1;padding:6px;overflow:hidden;'
      + 'white-space:pre;font:9px/13px monospace;'
      + 'color:${FONDS[nom][1]};background:${FONDS[nom][0]}';
    bg.textContent = Array.from({length:12}, (_,i) => 'bureau ' + i + ' ~ texte').join('\\n');
    document.body.prepend(bg);
    /* ⚠ LE BANC CACHAIT CE QU'IL DEVAIT MONTRER (trouvé le 2026-08-04).
       Cette ligne montait #scene en z-index:1 — le canvas passait alors DEVANT
       le pavé de code et le libellé, qui n'ont pas de z-index. Toutes les
       planches depuis le 03/08 montrent donc une orbe MUETTE, et j'ai failli
       corriger le pavé sur la foi de cette image. Le fond suffit à lui seul
       (z-index:-1) ; on remonte explicitement les deux surcouches. */
    document.getElementById('scene').style.zIndex = '0';
    document.getElementById('pave').style.zIndex = '2';
    document.getElementById('dit').style.zIndex = '2';
    return true; })()`);

  const FONDS_DEMANDES = (process.env.BANC_FONDS || 'bureau,clair,sombre').split(',');
  const faits = [];
  for (const fond of FONDS_DEMANDES) {
   await poserFond(fond);
   for (const verre of VERRES) {
    for (const [etat, st] of ETATS) {
      cp.execFileSync('python3', [STATUS, st, st === 'busy' ? etat : '', 'banc']
                      .filter(x => x !== ''));
      await w.webContents.executeJavaScript(`window.__orbe.setVerre(${verre})`);
      // 2,6 s : le fondu de mécanique dure 1,4 s. Capturer avant fige une forme
      // intermédiaire qui n'existe à aucun moment réel.
      await new Promise(r => setTimeout(r, 2600));
      const p = path.join(SORTIE, `${fond}-v${verre}-${etat}.png`);
      fs.writeFileSync(p, (await w.webContents.capturePage()).toPNG());
      faits.push(p);
    }
   }
  }
  console.log(`${faits.length} captures dans ${SORTIE}`);
  app.quit();
});
app.on('window-all-closed', () => app.quit());
