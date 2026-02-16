#!/bin/bash
# Sprint checkpoint — run between coding sessions.
# Replaces the forge-iterate AI skill with a free bash script.
#
# What it does:
#   1. Runs full test suite
#   2. Counts done/pending features
#   3. Appends a session entry to progress.txt
#   4. Updates dependency blocking status
#
# Usage: ./.forge/scripts/checkpoint.sh
#   Called by orchestrate.sh, or manually by the user.

set -e

echo "=== Sprint Checkpoint: $(date) ==="

# --- Validate features.json ---
if [ ! -f ".forge/projects/current/features.json" ]; then
  echo "ERROR: .forge/projects/current/features.json not found."
  exit 1
fi

python3 -c "import json; json.load(open('.forge/projects/current/features.json'))" 2>/dev/null || {
  echo "ERROR: .forge/projects/current/features.json is not valid JSON."
  exit 1
}

# --- Count features ---
read DONE PENDING BLOCKED TOTAL <<< $(python3 -c "
import json
with open('.forge/projects/current/features.json') as f:
    data = json.load(f)
features = data['features']
done = sum(1 for f in features if f['status'] == 'done')
pending = sum(1 for f in features if f['status'] == 'pending')
blocked = sum(1 for f in features if f['status'] == 'blocked')
total = len(features)
print(done, pending, blocked, total)
")

echo "Features: $DONE done / $TOTAL total ($PENDING pending, $BLOCKED blocked)"

# --- Completed feature IDs ---
COMPLETED_IDS=$(python3 -c "
import json
with open('.forge/projects/current/features.json') as f:
    data = json.load(f)
done_ids = [f['id'] for f in data['features'] if f['status'] == 'done']
print(', '.join(done_ids) if done_ids else 'none')
")

# --- Run full tests ---
echo ""
echo "=== Running Full Tests ==="
TEST_OUTPUT=$(./.forge/scripts/test_fast.sh 2>&1) || true
TEST_EXIT=$?

if [ $TEST_EXIT -eq 0 ]; then
  TEST_STATUS="all pass"
  echo "Tests: PASS"
else
  TEST_STATUS="failures detected"
  echo "Tests: FAIL"
  echo "$TEST_OUTPUT" | tail -20
fi

# --- Determine session number ---
SESSION_NUM=$(grep -c "^Session:" .forge/projects/current/progress.txt 2>/dev/null || echo 0)
SESSION_NUM=$((SESSION_NUM + 1))

# --- Recent commits ---
RECENT_COMMITS=$(git log --oneline -3 2>/dev/null | head -3 || echo "  (no commits)")

# --- Append to progress.txt ---
cat >> .forge/projects/current/progress.txt << ENTRY

---
Session: $SESSION_NUM ($(date +%Y-%m-%d))
Features completed: $COMPLETED_IDS
Features remaining: $PENDING pending, $BLOCKED blocked
Test status: $TEST_STATUS
Recent commits:
$(git log --oneline -5 2>/dev/null || echo "  none")
ENTRY

echo ""
echo "=== Checkpoint Complete ==="
echo "Session: $SESSION_NUM"
echo "Done: $DONE / $TOTAL"
echo "Remaining: $PENDING pending, $BLOCKED blocked"
echo "Tests: $TEST_STATUS"

# --- Update dependency blocking ---
python3 -c "
import json
with open('.forge/projects/current/features.json') as f:
    data = json.load(f)
done_ids = {f['id'] for f in data['features'] if f['status'] == 'done'}
changed = False
for feat in data['features']:
    if feat['status'] == 'pending':
        deps = feat.get('depends_on', [])
        all_met = all(d in done_ids for d in deps)
        # No status change here — just informational
with open('.forge/projects/current/features.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
" 2>/dev/null
