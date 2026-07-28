#!/usr/bin/env bash
# selftest — checks that the hooks do not crash and exit with code 0.
# Un hook qui plante en silence est pire qu'absent : ce test l'attrape.
set -u
BRAIN="$HOME/.c-brain/trunk"
cd "$BRAIN"
fail=0
ok()   { echo "  ✅ $1"; }
ko()   { echo "  ❌ $1"; fail=1; }

echo "== C Brain — hook selftest =="

# 1. compilation Python
for f in hooks/*.py; do
  python3 -m py_compile "$f" 2>/dev/null && ok "compile $f" || ko "compile $f"
done

# 2. capsule main.js
node --check capsule/main.js 2>/dev/null && ok "node --check main.js" || ko "node --check main.js"

# 3. SessionEnd: auto_maintain must exit 0 even on empty input / a trivial session.
# CLAUDE_BRAIN_GARDENING=1 = ZERO SIDE EFFECTS: without it, if the Inbox has work and the quota
# is open, the test would cross the guards, pull a REAL session off the backlog and launch a
# claude agent (token spend + race risk). A test must never mutate real state.
CLAUDE_BRAIN_GARDENING=1 bash -c "echo '{}' | python3 hooks/auto_maintain.py"; [ $? -eq 0 ] && ok "auto_maintain exit 0 (empty input, no side effects)" || ko "auto_maintain"

# 4. PostToolUse: on_fiche_write must exit 0 on a target outside the trunk
echo '{"tool_input":{"file_path":"/tmp/horstronc.md"}}' | python3 hooks/on_fiche_write.py; [ $? -eq 0 ] && ok "on_fiche_write exit 0 (outside the trunk)" || ko "on_fiche_write"

# 5. brain_guard: interpreting a 429 must return 7 (a handled failure, not 0)
tmp=$(mktemp); echo '{"is_error":true,"api_error_status":429,"result":"limit resets 2:50pm"}' > "$tmp"
python3 hooks/brain_guard.py interpret "$tmp" "selftest-sid"; [ $? -eq 7 ] && ok "brain_guard interpret 429 → exit 7" || ko "brain_guard interpret"
# clean up the test state left behind by interpret.
# CRITICAL: interpret(429) writes state/quota.json = {blocked_until: <future>} (a DICT).
# The old cleanup handled ONLY lists → the quota marker stayed poisoned
# and autonomous maintenance was silently blocked until the fictitious reset time.
# We remove the test sid from the queue AND reset the quota to 0 (unblocked).
python3 - <<'PY' 2>/dev/null
import json,os
B=os.path.expanduser("~/.c-brain/trunk/")
p=B+"state/pending-distill.json"
if os.path.exists(p):
    try:
        d=json.load(open(p))
        if isinstance(d,list): json.dump([s for s in d if s!="selftest-sid"],open(p,"w"))
    except Exception: pass
# reset the quota (and login) — test state must NEVER survive the selftest
try: json.dump({"blocked_until":0,"msg":"ok"},open(B+"state/quota.json","w"))
except Exception: pass
PY
rm -f "$tmp"

# 6. doctor must run (0 healthy / 1 anomalies) without crashing
python3 hooks/brain_doctor.py --quiet; rc=$?; { [ $rc -eq 0 ] || [ $rc -eq 1 ]; } && ok "brain_doctor runs (rc=$rc)" || ko "brain_doctor crash"

# 7. INVARIANTS — doc↔code relations, sensors that come back down, legacy tolerance.
#    Each past bug is engraved there as a relation, not as a special case.
python3 tests/invariants_brain.py >/dev/null 2>&1 \
  && ok "invariants_brain (7 relations)" \
  || ko "invariants_brain — a trunk invariant is violated (python3 tests/invariants_brain.py)"

echo
[ $fail -eq 0 ] && echo "✅ selftest OK — every hook healthy" || echo "❌ selftest: some hooks are broken"
exit $fail
