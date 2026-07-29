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

⚠ **This used to be stated the wrong way round, and it was a real bug.** The
earlier text claimed each install stayed in its own language "as long as each
clone tracks its own branch". That reasoning does not hold: `update.sh` never
looked at a branch. It ran `git tag -l 'v*' | sort -V | tail -1`, and **tags are
not scoped to a branch** — so it saw both families at once. Since `sort -V`
places `v1.18.0-fr` **after** `v1.18.0`, the global maximum was the French tag,
and an English installation would have moved onto the French tree the moment
`fr` caught up. No error: the tag exists, the checkout succeeds, the tool just
starts speaking another language.

It stayed invisible only because `fr` lagged eight versions behind. Bringing it
level is what armed it.

`update.sh` now reads the family off what is installed — the suffix of the
checked-out tag, or the tracked branch when there is none — and filters the tag
list to that family before sorting. `tests/update_tag_family.sh` builds a
throwaway repository with both branches and holds it down in CI.

## What is not translated, on purpose

`rules.json` keeps **French patterns and replacements**: they match the French
source Brain, which is the only thing they will ever run against. Its `why`
fields — pure documentation — are in English. The file is inert on `main`; it is
kept there so the repo stays complete and auditable.
