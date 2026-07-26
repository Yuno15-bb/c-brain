# Companion — suivi live des modifications, intégré à la session

**Aucune fenêtre.** Deux surfaces seulement :

1. **La barre de bas de session** (2ᵉ ligne de la status line) — en permanence, dans la
   session : nombre de fichiers touchés, `+`/`−` cumulés, dernier fichier modifié avec son
   solde et son âge, état de l'app, âge du dernier rechargement.
2. **Ton onglet navigateur** — rechargé automatiquement après chaque rafale de
   modifications : c'est là qu'on voit le **rendu réel**, pas seulement le code.

Historique : une première version affichait un panneau Electron collé sous la fenêtre
Terminal. Abandonné — illisible, et deux sessions donnaient deux panneaux flottants qui
recouvraient le travail. Le code reste dans l'historique git.

---

## Comportement

| Point | Détail |
|---|---|
| Déclencheur | `Write` / `Edit` / `MultiEdit` / `NotebookEdit`, tous projets |
| Barre | `✎ 9f +879 −239 │ status_part.py +183 −0 2min │ app :3000 │ ↻ 4s` |
| Agrégation | incrémentale par curseur d'octets, cache dans `agg/<sid>.json` — la barre ne relit jamais tout le flux |
| Navigateur | Chrome puis Safari, onglet dont l'URL contient `localhost:<port>` ; débounce 1,2 s de silence, verrou `mkdir` (un seul recharcheur), jamais de vol de focus (`open -g`, pas d'`activate`) |
| Premier lancement | si aucun onglet n'affiche l'app, il en ouvre **un seul** (mémorisé par port), ensuite il ne fait que recharger |
| Ports sondés | `3000 · 5173 · 4321 · 8080 · 8000 · 4200` |
| Fin de session | événement `end` dans le flux, pré-images et totaux nettoyés |

## Sécurité et robustesse

- **Jamais bloquant** : chaque hook est enveloppé `try/except` + `sys.exit(0)`, timeouts 5–8 s ; le recharcheur tourne détaché. Companion cassé ⇒ session Claude intacte.
- **Secrets** : `.env`, `secrets/`, `*.pem`, `*.key`, `credentials`, `.npmrc`… → la modification est signalée, le contenu **n'est jamais affiché**. Ailleurs, toute ligne ressemblant à un secret est masquée valeur par valeur.
- **Plafonds** : diff tronqué à 500 lignes, fichiers > 2 Mo non diffés ; le flux est purgé à 7 jours.
- **Append-only** : le flux d'événements n'est jamais réécrit en bloc.

## Fichiers

```
companion/
  status_part.py           la 2e ligne de la barre (importée par ~/.claude/statusline.py)
  hooks/companion_lib.py   chemins, masquage des secrets, écriture du flux
  hooks/pre_snapshot.py    PreToolUse  → pré-image du fichier (l'« avant » du diff)
  hooks/post_diff.py       PostToolUse → diff réel + réveil du recharcheur
  hooks/browser_reload.py  détaché      → débounce puis rechargement de l'onglet
  hooks/session_close.py   SessionEnd  → marque la fin, purge (flux > 7 jours)
```

État runtime dans `~/.claude/companion/` : `sessions/<sid>.jsonl` (flux),
`snap/<sid>/` (pré-images), `agg/<sid>.json` (totaux de la barre),
`reload.json` (dernier rechargement), `port.json` (cache de sonde).

## Limites connues

- **Aucune image dans Terminal.app** : il n'existe aucun protocole d'image inline. Voir le rendu *dans* le terminal impose iTerm2 ou kitty. D'où le choix du navigateur.
- **Premier rechargement** : macOS demande une fois l'autorisation d'automatiser Chrome/Safari. Refusée, le rechargement échoue en silence — la barre reste juste.
- **Modifications hors outils d'édition** (`Bash` avec `sed`, `git checkout`, script) : invisibles. Il faudrait une surveillance de dossier.
- Le suivi **montre** le changement, il ne le **valide** pas : la vérification reste les tests et l'œil.

## Désactiver

- Barre : retirer le bloc `status_part` de `~/.claude/statusline.py` (sauvegarde `statusline.py.bak-companion-*`).
- Hooks : retirer les 3 entrées `companion/hooks/*.py` de `~/.claude/settings.json` (`PreToolUse`, `PostToolUse`, `SessionEnd`). Sauvegarde : `settings.json.bak-companion-*`.
