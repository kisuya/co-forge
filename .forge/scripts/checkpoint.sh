#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Forge Checkpoint: $(date) ==="

python3 "$SCRIPT_DIR/runtime.py" qa
QA_EXIT=$?

STATS_JSON="$(python3 "$SCRIPT_DIR/runtime.py" queue-stats)"
DONE="$(printf '%s' "$STATS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["done"])')"
TOTAL="$(printf '%s' "$STATS_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["total"])')"
MILESTONE_ID="$(printf '%s' "$STATS_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); milestone=data.get("active_milestone") or {}; print(milestone.get("id","no-milestone"))')"

if [ "${FORGE_AUTO_COMMIT:-0}" = "1" ] && [ "$QA_EXIT" -eq 0 ]; then
  if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet HEAD 2>/dev/null; then
    SESSION_NUM="$(git log --grep='^Session ' --oneline 2>/dev/null | wc -l | tr -d ' ')"
    SESSION_NUM=$((SESSION_NUM + 1))
    COMMIT_MSG="Session $SESSION_NUM: $MILESTONE_ID ($DONE/$TOTAL done)"
    git add -A
    git commit -m "$COMMIT_MSG"
    echo "Committed: $COMMIT_MSG"
  else
    echo "No changes to commit."
  fi
else
  echo "Auto-commit disabled."
fi

exit "$QA_EXIT"
