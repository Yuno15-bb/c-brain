# Two branches, one engine

`main` is **English**. `fr` is **French**, and it is the branch the engine is
extracted onto.

```
~/claude-brain (French)  ──sync.sh──▶  fr  ──translation──▶  main (English)
     the living Brain                                         what people install
```

## Why this direction and not the other

The source Brain is written in French: its hooks, its agent prompts, its
comments. `sync.sh` copies from it and `generalize.py` rewrites it with rules
that **match French strings**. Neither can run against English files.

So English cannot be the sync target. It is derived from `fr`, one step later.

## The guard

`./sync.sh` **refuses to run on `main`**. Without that guard, one sync would
silently overwrite every translated file with its French original — and nothing
would catch it: no test reads prose. Only a reader would notice, much later.

```
❌ ./sync.sh runs on the `fr` branch, not on `main`.
```

`CBRAIN_ALLOW_SYNC_ON_MAIN=1` forces it, for the rare case where you know why.

## What the sync does NOT take

Three files live **only in the package** and are excluded from the sync, because
`rsync --delete` would wipe them on the first pass:

| File | Why it is not in the living Brain |
|---|---|
| `hooks/hooks.json` | the Claude Code plugin's hook manifest |
| `tests/plugin_manifest.py` | checks the package's own manifests |
| `tests/english_only.py` | watches the translation, on `main` only |

This is the worst failure mode available here: an erased `hooks.json` does not
crash — the plugin simply **stops recording**.

## Workflow when the Brain evolves

```bash
git checkout fr
./sync.sh                  # copy + generalize, French
python3 leakcheck.py       # must be green
git commit -am "sync: <what moved>"

git checkout main
git diff fr@{1} fr -- .    # what actually changed
# port those changes, translated, onto main
python3 leakcheck.py --history
./publish.sh v1.2.0 "..."
```

Read the diff before translating. Most syncs move a handful of lines; a blind
`git merge fr` would drag the whole French tree back onto `main`.

## Tags

| Branch | Tags | Who installs it |
|---|---|---|
| `main` | `v1.2.0` | everyone, by default |
| `fr` | `v1.2.0-fr` | French speakers who ask for it |

`update.sh` sorts tags with `sort -V` and takes the newest. A `-fr` suffix sorts
**after** the bare version, so a French install stays French and an English one
stays English **only as long as each clone tracks its own branch** — which is the
case, since `git checkout <tag>` never changes branch.

## What is not translated, on purpose

`rules.json` keeps **French patterns and replacements**: they match the French
source Brain, which is the only thing they will ever run against. Its `why`
fields — pure documentation — are in English. The file is inert on `main`; it is
kept there so the repo stays complete and auditable.
