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
    if 'description' not in f or not f['description'].strip():
        print(f'ERROR: feature \"{f[\"id\"]}\" missing or empty \"description\".', file=sys.stderr)
        sys.exit(1)
    if f['description'].strip() == f.get('name', '').strip():
        print(f'ERROR: feature \"{f[\"id\"]}\" description is identical to name.', file=sys.stderr)
        sys.exit(1)
" 2>&1 || {
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

# --- Completed feature IDs (all-time, for delta calculation) ---
COMPLETED_IDS=$(python3 -c "
import json
with open('docs/projects/current/features.json') as f:
    data = json.load(f)
done_ids = [f['id'] for f in data['features'] if f['status'] == 'done']
print(', '.join(done_ids) if done_ids else 'none')
")

# --- Delta: newly completed feature IDs (this session only) ---
NEW_IDS=$(python3 -c "
import json, re

prev_done = set()
try:
    with open('docs/projects/current/progress.txt') as f:
        content = f.read()
    # Read from hidden meta line (<!-- done: ... -->) written by previous checkpoint
    matches = re.findall(r'<!-- done: (.+?) -->', content)
    if matches:
        prev_done = {x.strip() for x in matches[-1].split(',')}
except FileNotFoundError:
    pass

with open('docs/projects/current/features.json') as f:
    data = json.load(f)
done_ids = [f['id'] for f in data['features'] if f['status'] == 'done']
new_ids = [fid for fid in done_ids if fid not in prev_done]
print(', '.join(new_ids) if new_ids else 'no new features')
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

# --- Find last checkpoint commit for session-scoped log ---
LAST_CHECKPOINT=$(git log --oneline --grep="^Session " -1 --format="%H" 2>/dev/null || true)
if [ -n "$LAST_CHECKPOINT" ]; then
  SESSION_COMMITS=$(git log --oneline "$LAST_CHECKPOINT"..HEAD 2>/dev/null || echo "  none")
else
  SESSION_COMMITS=$(git log --oneline -5 2>/dev/null || echo "  none")
fi

# --- Collect AI summary (agent appends "Summary: ..." before exit) ---
AI_SUMMARY=$(grep "^Summary:" docs/projects/current/progress.txt 2>/dev/null | tail -1 || true)
# Remove the raw Summary line so it's merged into the structured entry
if [ -n "$AI_SUMMARY" ]; then
  python3 -c "
import re
with open('docs/projects/current/progress.txt') as f:
    lines = f.readlines()
# Remove last occurrence of Summary: line
for i in range(len(lines)-1, -1, -1):
    if lines[i].startswith('Summary:'):
        del lines[i]
        break
with open('docs/projects/current/progress.txt', 'w') as f:
    f.writelines(lines)
"
fi

# --- Append to progress.txt ---
cat >> docs/projects/current/progress.txt << ENTRY

---
Session: $SESSION_NUM ($(date +%Y-%m-%d %H:%M))
${AI_SUMMARY:-Summary: (no agent summary)}
Features this session: $NEW_IDS
Progress: $DONE/$TOTAL done ($PENDING pending, $BLOCKED blocked)
Tests: $TEST_STATUS
Commits:
$SESSION_COMMITS
<!-- done: $COMPLETED_IDS -->
ENTRY

echo ""

# --- Git commit (if tests pass and there are changes) ---
if [ "$TEST_EXIT" -eq 0 ]; then
  if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet HEAD 2>/dev/null; then
    if [ "$NEW_IDS" = "no new features" ]; then
      COMMIT_MSG="Session $SESSION_NUM: checkpoint ($DONE/$TOTAL done)"
    else
      COMMIT_MSG="Session $SESSION_NUM: $NEW_IDS ($DONE/$TOTAL done)"
    fi
    git add -A 2>/dev/null && \
    git commit -m "$COMMIT_MSG" 2>/dev/null && \
    echo "Git: committed — $COMMIT_MSG" || echo "Git: commit skipped (write not available)"
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

