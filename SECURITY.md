# Security

## What this software actually does to your machine

Worth stating plainly, because it is the honest basis for judging risk:

- **It writes inside `$HOME`.** `~/.c-brain/` (engine and trunk), `~/.claude/`
  (settings merge, status line), `~/Library/LaunchAgents/com.claudebrain.*`
  (scheduled jobs), a launcher on the Desktop, and a `C Brain` shortcut in your
  home folder pointing at your trunk (`--no-shortcut` skips it). `install.sh` records every
  one of them in a manifest, and `uninstall.sh` undoes them.
- **It runs code on your machine automatically.** That is the point: hooks fire
  on your CLI agent's events, and two `launchd` jobs run on a timer. Install
  `--no-launchd` if you would rather nothing ran unattended.
- **It makes no network call except `git pull`.** No telemetry, no analytics, no
  crash reporting, no phone-home on install. `brain update` is announced, never
  automatic.
- **It never sends your notes anywhere.** They are markdown files in a directory
  you own. Nothing reads them except to hand them back to you.

## Supported versions

Fixes go onto the latest release. There is no long-term support branch, and
older tags are not patched — `brain update` moves you forward.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private reporting on this repository:
**Security → Report a vulnerability**. It reaches the maintainer directly and
stays private until there is a fix.

Useful in a report: what an attacker can do, what they need first (local access?
a malicious repo? a crafted note?), and the smallest sequence that shows it.

Expect a first answer within about a week. This is a personal project, not a
staffed product — that number is what one maintainer can honestly promise.

## In scope

- Anything letting a **note, a repository, or a hook payload** run code that the
  user did not ask for.
- **Path handling** in `install.sh`, `uninstall.sh` and the migrations — they
  move directories inside `$HOME` and a mistake there costs real work.
- **`leakcheck.py` failing open**: it is what stands between a personal trunk
  and a public push. A way to get a secret past it is a vulnerability, and one
  of the more interesting kinds here.
- **`merge_settings.py` corrupting or losing keys** in `~/.claude/settings.json`.

## Out of scope

- The fact that the engine executes on your machine by design — see above.
- Anything requiring an attacker who already has write access to your `$HOME`;
  at that point they do not need C Brain.
- Reports against the `fr` branch that do not also apply to `main`, unless the
  bug is specifically in the French version.
