/* Rend un diagramme HTML en PNG net (retina), recadré sur son contenu.

   ⚠ TROIS PIÈGES, tous payés une fois sur ce diagramme :
     · Chromium MÉMORISE le facteur de zoom par origine, dans le profil. Un essai
       antérieur à zoom 2 s'appliquait encore aux rendus suivants : la mise en
       page doublait et la capture paraissait coupée. On repose le zoom à 1.
     · `scrollWidth` et `max-content` MENTENT sur du flexbox : des boîtes qui se
       compriment laissent le texte déborder sans que la boîte grossisse. D'où
       une grille à colonnes FIXES dans archi.html — largeur vérifiable par le
       calcul, et un contrôle du bord droit réel ici.
     · Mesurer la hauteur sur `document.querySelectorAll('*')` inclut `html`,
       dont le rectangle vaut la hauteur de la FENÊTRE, pas du contenu : on
       mesure donc sous `document.body`.

   Usage : SRC=... OUT=... W=1700 electron banc/diagramme.cjs
*/
const { app, BrowserWindow } = require('electron'); const fs=require('fs');
app.setPath('userData','/private/tmp/claude-diag-'+Date.now());
const SRC=process.env.SRC, OUT=process.env.OUT, W=Number(process.env.W||1760);
app.whenReady().then(async()=>{ if(app.dock)app.dock.hide();
  const w=new BrowserWindow({width:W,height:1200,show:false,frame:false,backgroundColor:'#0d1117'});
  await w.loadFile(SRC);
  // ⚠ Chromium MÉMORISE le facteur de zoom par origine, dans le profil. Un essai
  //   antérieur à zoom 2 continuait de s'appliquer à chaque rendu suivant : la
  //   mise en page doublait, donc la capture semblait coupée alors que la
  //   mesure du bord droit, elle, disait « ça tient ». On le repose à 1.
  w.webContents.setZoomFactor(1);
  await new Promise(r=>setTimeout(r,900));
  // ⚠ On ne fait pas confiance à scrollWidth : on relève le bord DROIT réel de
  //   chaque élément. Un débordement de flexbox ne fait pas grossir scrollWidth.
  const m = await w.webContents.executeJavaScript(`(()=>{
    // ⚠ On EXCLUT html et body : leur rectangle vaut la hauteur de la FENÊTRE,
    //   pas celle du contenu. Les inclure renvoyait toujours la taille de départ.
    let r=0,b=0; for (const e of document.body.querySelectorAll('*')) {
      const k=e.getBoundingClientRect(); if(k.width){ r=Math.max(r,k.right); b=Math.max(b,k.bottom); } }
    return [Math.ceil(r), Math.ceil(b)]; })()`);
  console.log('bord droit', m[0], '· bas', m[1], '· fenêtre', W, m[0] > W ? '→ DÉBORDE' : '→ tient');
  w.setContentSize(W, m[1]+38);
  await new Promise(r=>setTimeout(r,600));
  fs.writeFileSync(OUT,(await w.webContents.capturePage()).toPNG());
  console.log('OK'); app.quit(); });
app.on('window-all-closed',()=>app.quit());
