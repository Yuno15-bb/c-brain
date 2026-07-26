#!/usr/bin/env bash
# selftest — vérifie que les hooks ne plantent pas et sortent en code 0.
# Un hook qui plante en silence est pire qu'absent : ce test l'attrape.
set -u
BRAIN="$HOME/claude-brain"
cd "$BRAIN"
fail=0
ok()   { echo "  ✅ $1"; }
ko()   { echo "  ❌ $1"; fail=1; }

echo "== selftest des hooks du Claude Brain =="

# 1. compilation Python
for f in hooks/*.py; do
  python3 -m py_compile "$f" 2>/dev/null && ok "compile $f" || ko "compile $f"
done

# 2. capsule main.js
node --check capsule/main.js 2>/dev/null && ok "node --check main.js" || ko "node --check main.js"

# 3. SessionEnd : auto_maintain doit sortir 0 même sur entrée vide / session triviale.
# CLAUDE_BRAIN_GARDENING=1 = ZÉRO EFFET DE BORD : sans ça, si l'Inbox a du travail et que le quota
# est ouvert, le test franchissait les gardes, dé-filait une VRAIE session du backlog et lançait un
# agent claude (consommation tokens + risque de race). Un test ne doit jamais muter l'état réel.
CLAUDE_BRAIN_GARDENING=1 bash -c "echo '{}' | python3 hooks/auto_maintain.py"; [ $? -eq 0 ] && ok "auto_maintain exit 0 (entrée vide, sans effet de bord)" || ko "auto_maintain"

# 4. PostToolUse : on_fiche_write doit sortir 0 sur cible hors-tronc
echo '{"tool_input":{"file_path":"/tmp/horstronc.md"}}' | python3 hooks/on_fiche_write.py; [ $? -eq 0 ] && ok "on_fiche_write exit 0 (hors-tronc)" || ko "on_fiche_write"

# 5. brain_guard : interpret d'un 429 doit renvoyer 7 (échec géré, pas 0)
tmp=$(mktemp); echo '{"is_error":true,"api_error_status":429,"result":"limit resets 2:50pm"}' > "$tmp"
python3 hooks/brain_guard.py interpret "$tmp" "selftest-sid"; [ $? -eq 7 ] && ok "brain_guard interpret 429 → exit 7" || ko "brain_guard interpret"
# nettoyage de l'état de test laissé par interpret.
# CRITIQUE : interpret(429) écrit state/quota.json = {blocked_until: <futur>} (un DICT).
# L'ancien nettoyage ne traitait QUE les listes → le marqueur quota restait empoisonné
# et la maintenance autonome était silencieusement bloquée jusqu'à l'heure de reset fictive.
# On retire le sid de test de la file ET on réarme le quota à 0 (débloqué).
python3 - <<'PY' 2>/dev/null
import json,os
B=os.path.expanduser("~/claude-brain/")
p=B+"state/pending-distill.json"
if os.path.exists(p):
    try:
        d=json.load(open(p))
        if isinstance(d,list): json.dump([s for s in d if s!="selftest-sid"],open(p,"w"))
    except Exception: pass
# réarme le quota (et le login) — l'état de test ne doit JAMAIS survivre au selftest
try: json.dump({"blocked_until":0,"msg":"ok"},open(B+"state/quota.json","w"))
except Exception: pass
PY
rm -f "$tmp"

# 6. doctor doit tourner (0 sain / 1 anomalies) sans crasher
python3 hooks/brain_doctor.py --quiet; rc=$?; { [ $rc -eq 0 ] || [ $rc -eq 1 ]; } && ok "brain_doctor tourne (rc=$rc)" || ko "brain_doctor crash"

# 7. INVARIANTS du Brain — relations doc↔code, capteurs qui redescendent, tolérance legacy.
#    Chaque bug de l'audit 2026-07-10 y est gravé comme relation, pas comme cas particulier.
python3 tests/invariants_brain.py >/dev/null 2>&1 \
  && ok "invariants_brain (7 relations)" \
  || ko "invariants_brain — un invariant du tronc est violé (python3 tests/invariants_brain.py)"

echo
[ $fail -eq 0 ] && echo "✅ selftest OK — tous les hooks sains" || echo "❌ selftest : des hooks sont cassés"
exit $fail
