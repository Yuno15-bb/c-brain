# Recette de vérification

À rejouer **avant chaque tag publié**. Tout se fait dans un `HOME` isolé : aucune
étape ne touche à la machine réelle.

L'ordre compte : chaque étape suppose la précédente verte.

## 0. La chaîne d'extraction

```bash
cd <dépôt>
./sync.sh --check      # rc=0 → le paquet colle au Brain vivant
./sync.sh              # copie + généralisation enchaînées
python3 leakcheck.py --history
```

**Attendu** : `✅ PROPRE`. Un seul marqueur = rien ne sort.

> Le contrôle positif compte autant que le vert : modifie un fichier du paquet,
> relance `./sync.sh --check`, il doit sortir en 1. Un vert qui ne peut jamais
> virer au rouge ne prouve rien.

## 1. Installation depuis un vrai CLONE

**Jamais depuis une copie de dossier.** C'est en clonant qu'on découvre ce que le
`.gitignore` avale — un motif non ancré avait fait disparaître tout le squelette
du tronc, invisible en copiant.

```bash
T=/tmp/iso-c-brain; rm -rf $T; mkdir -p $T/.claude $T/Desktop
git clone <dépôt> $T/dev-c-brain
HOME=$T bash $T/dev-c-brain/install.sh --no-launchd
```

**Attendu** : `✅ selftest OK`, `✅ doctor — arbre cohérent`, `✅ C Brain installé.`

## 2. Non destructif et idempotent

Pose un `settings.json` contenant un modèle, un thème et un hook personnel, puis :

```bash
HOME=$T bash $T/dev-c-brain/install.sh      # 2e passe
```

**Attendu** : « déjà relié » partout, `settings.json — rien à faire`. Le hook
personnel, le modèle et le thème sont toujours là.

## 3. Le cycle de vie complet

```bash
echo "fiche test" > $T/.c-brain/trunk/lessons/test.md
HOME=$T bash $T/dev-c-brain/uninstall.sh --yes
```

**Attendu** : la fiche existe encore, `settings.json` retrouve **toutes tes clés
et aucune des nôtres**, les liens du moteur ont disparu.

⚠ Compare le JSON **analysé**, pas les octets : la désinstallation réécrit le
fichier via le sérialiseur JSON de Python, donc une mise en forme à la main
revient reformatée. C'est l'invariant que tient la CI depuis v1.13.0.

## 4. Capsule

```bash
HOME=$T CAPSULE_DEV=1 <dépôt>/capsule/node_modules/.bin/electron <dépôt>/capsule \
  --user-data-dir=$T/electron-data &
HOME=$T python3 $T/.c-brain/trunk/hooks/brain_status.py busy distilling "test"
sleep 3; touch /tmp/cap_shot_req; sleep 3   # → /tmp/cap.png
```

**Attendu** : la capture montre `DISTILLING` + le détail. Repasse en `idle`, la
capture suivante montre `IDLE`.

> `--user-data-dir` est obligatoire : sans lui, la seconde instance se ferme en
> silence à cause du verrou d'instance unique, et on croit la capsule cassée.

> Si Electron ne démarre pas : son téléchargeur laisse parfois une archive
> tronquée en sortant pourtant en succès. `install.sh` le détecte désormais et le
> dit. Remède : supprimer `capsule/node_modules/electron` et réinstaller.

## 5. Planète

```bash
HOME=$T bash $T/.c-brain/trunk/planet/launch.sh 8799 &
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8799/
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8799/graph.json
```

**Attendu** : deux fois `200`. Pour la preuve visuelle, une capture headless
(Chromium `--use-gl=angle --use-angle=swiftshader`) doit montrer le globe, le
champ d'étoiles et la légende des agents.

## 6. Companion

```bash
J='{"session_id":"t","tool_input":{"file_path":"'$T'/demo.py"}}'
echo "$J" | HOME=$T python3 $T/.c-brain/trunk/companion/hooks/pre_snapshot.py
# … modifier le fichier …
echo "$J" | HOME=$T python3 $T/.c-brain/trunk/companion/hooks/post_diff.py
echo '{"session_id":"t","model":{"display_name":"X"},"workspace":{"current_dir":"/tmp"}}' \
  | HOME=$T python3 $T/.claude/statusline.py
```

**Attendu** : **deux** lignes, la seconde affichant le compte de fichiers et le
solde `+`/`−`.

## 7. Mise à jour — le test qui compte le plus

Monte un dépôt distant local, publie deux tags, installe le premier, écris une
fiche, puis mets à jour.

```bash
git init --bare /tmp/remote.git
# … pousser v1.0.0, installer, écrire une fiche …
# … pousser v1.1.0 avec une migration et un changement visible …
HOME=$T brain update
```

**Attendu, dans cet ordre** :

- [ ] la fiche de l'utilisateur est **intacte** ;
- [ ] le changement de code est **arrivé** (les symlinks propagent instantanément) ;
- [ ] la migration a tourné **une seule fois** et figure dans le journal ;
- [ ] `brain version` renvoie le nouveau tag ;
- [ ] un second `brain update` dit « déjà à jour » et **ne rejoue pas** la migration ;
- [ ] `brain update --rollback` revient à la version précédente, selftest vert,
      fiche toujours là.

> Rappel : c'est l'updater **installé** qui s'exécute. Un correctif dans
> `update.sh` ne protège que les utilisateurs déjà passés à cette version ou
> après. Réfléchis-y à deux fois avant de publier un changement de l'updater.
