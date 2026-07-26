# Migrations

One script per change that requires an adaptation on an already-installed
machine. Named `001-something.sh`, run **in order**, **exactly once** (the log
lives at `~/.c-brain/state/applied-migrations.txt`).

## The three rules

1. **Never destructive to content.** `lessons/`, `projects/`, `meta/`, `life/`,
   `sessions/` are not modified here. A migration touches the installation, not
   somebody's knowledge.
2. **Idempotent anyway.** The log can be lost (restore, new machine). Replaying a
   migration must break nothing.
3. **Failure means stop.** A non-zero exit halts the update and lets
   `brain update --rollback` do its job. Better to stop dead than proceed
   halfway.

## Template

```bash
#!/usr/bin/env bash
# 001-example.sh — <what it adapts, and why it was needed>
set -euo pipefail

TRUNK="$HOME/claude-brain"

# Check BEFORE acting: that is what makes a replay harmless.
if [ -f "$TRUNK/state/old-file.json" ]; then
  mv "$TRUNK/state/old-file.json" "$TRUNK/state/new-file.json"
  echo "  state renamed"
else
  echo "  nothing to do"
fi
```

No migration to date — this folder is waiting for the first real break.
