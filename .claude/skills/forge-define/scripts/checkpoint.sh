#!/bin/bash
# Sprint checkpoint — run between coding sessions.
# Replaces the forge-iterate AI skill with a free bash script.
#
# What it does:
#   1. Runs tests via test_fast.sh
#   2. Counts done/pending features
#   3. Appends a session entry to progress.txt
#
# Exit code: 0 if tests pass, 1 if tests fail or features.json is invalid.
#
# Usage: ./.forge/scripts/checkpoint.sh
#   Called by orchestrate.sh, or manually by the user.

set -e

echo "=== Sprint Checkpoint: $(date) ==="

# --- Validate features.json ---
if [ ! -f "docs/projects/current/features.json" ]; then
  echo "ERROR: docs/projects/current/features.json not found."
  exit 1
fi

python3 -c "
import json, sys
with open('docs/projects/current/features.json') as f:
    data = json.load(f)
if 'features' not in data or not isinstance(data['features'], list):
    print('ERROR: features.json missing \"features\" array.', file=sys.stderr)
    sys.exit(1)
for f in data['features']:
    if 'id' not in f or 'status' not in f:
        print(f'ERROR: feature missing \"id\" or \"status\" key: {f}', file=sys.stderr)
        sys.exit(1)
" 2>/dev/null || {
  echo "ERROR: docs/projects/current/features.json is invalid (bad JSON or missing schema)."
  exit 1
}

# --- Count features ---
read -r DONE PENDING BLOCKED TOTAL <<< $(python3 -c "
import json
with open('docs/projects/current/features.json') as f:
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
with open('docs/projects/current/features.json') as f:
    data = json.load(f)
done_ids = [f['id'] for f in data['features'] if f['status'] == 'done']
print(', '.join(done_ids) if done_ids else 'none')
")

# --- Run full tests ---
echo ""
echo "=== Running Full Tests ==="
TEST_OUTPUT=$(./.forge/scripts/test_fast.sh 2>&1) && TEST_EXIT=0 || TEST_EXIT=$?

if [ "$TEST_EXIT" -eq 0 ]; then
  TEST_STATUS="all pass"
  echo "Tests: PASS"
else
  TEST_STATUS="failures detected"
  echo "Tests: FAIL"
  echo "$TEST_OUTPUT" | tail -20
fi

# --- Determine session number ---
SESSION_NUM=$(grep -c "^Session:" docs/projects/current/progress.txt 2>/dev/null) || SESSION_NUM=0
SESSION_NUM=$((SESSION_NUM + 1))

# --- Append to progress.txt ---
cat >> docs/projects/current/progress.txt << ENTRY

---
Session: $SESSION_NUM ($(date +%Y-%m-%d))
Features done (all-time): $COMPLETED_IDS
Features remaining: $PENDING pending, $BLOCKED blocked
Test status: $TEST_STATUS
Recent commits:
$(git log --oneline -5 2>/dev/null || echo "  none")
ENTRY

echo ""

# --- Git commit (if tests pass and there are changes) ---
if [ "$TEST_EXIT" -eq 0 ]; then
  if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet HEAD 2>/dev/null; then
    git add -A 2>/dev/null && \
    git commit -m "Session $SESSION_NUM checkpoint" 2>/dev/null && \
    echo "Git: committed" || echo "Git: commit skipped (write not available)"
  else
    echo "Git: nothing to commit"
  fi
fi

echo ""
echo "=== Checkpoint Complete ==="
echo "Session: $SESSION_NUM"
echo "Done: $DONE / $TOTAL"
echo "Remaining: $PENDING pending, $BLOCKED blocked"
echo "Tests: $TEST_STATUS"

# Exit non-zero if tests failed so orchestrate.sh can detect it
if [ "$TEST_EXIT" -ne 0 ]; then
  exit 1
fi

