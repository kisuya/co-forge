#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT="${1:-codex}"
MAX_SESSIONS="${2:-20}"
CHILD_PID=""
SESSION=0
STALL_COUNT=0
RUNTIME="$SCRIPT_DIR/runtime.py"
RUN_CONTEXT=".forge/run-context.json"

if [ "$AGENT" != "claude" ] && [ "$AGENT" != "codex" ]; then
  echo "Usage: ./.forge/scripts/orchestrate.sh [claude|codex] [max-sessions]" >&2
  exit 1
fi

if ! [[ "$MAX_SESSIONS" =~ ^[1-9][0-9]*$ ]]; then
  echo "max-sessions must be a positive integer" >&2
  exit 1
fi

RUN_ID="${FORGE_RUN_ID:-}"
MAIN_ROOT="${FORGE_MAIN_ROOT:-}"
if [ -f "$RUN_CONTEXT" ]; then
  CONTEXT_RUN_ID="$(python3 -c 'import json; print(json.load(open(".forge/run-context.json")).get("run_id",""))')"
  CONTEXT_MAIN_ROOT="$(python3 -c 'import json; print(json.load(open(".forge/run-context.json")).get("main_root",""))')"
  RUN_ID="${RUN_ID:-$CONTEXT_RUN_ID}"
  MAIN_ROOT="${MAIN_ROOT:-$CONTEXT_MAIN_ROOT}"
fi

cleanup() {
  if [ -n "$CHILD_PID" ]; then
    kill -TERM "$CHILD_PID" 2>/dev/null || true
    wait "$CHILD_PID" 2>/dev/null || true
  fi
  if [ -n "$RUN_ID" ]; then
    FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status interrupted >/dev/null || true
  fi
}
trap cleanup SIGINT SIGTERM

queue_value() {
  local key="$1"
  python3 "$RUNTIME" queue-stats | python3 -c "import json,sys; print(json.load(sys.stdin)[\"$key\"])"
}

build_prompt() {
  local prompt_doc plans_doc implement_doc documentation_doc queue_json validation_json recent_commits
  prompt_doc="$(cat docs/prompt.md 2>/dev/null)"
  plans_doc="$(cat docs/plans.md 2>/dev/null)"
  implement_doc="$(cat docs/implement.md 2>/dev/null)"
  documentation_doc="$(cat docs/documentation.md 2>/dev/null)"
  queue_json="$(cat .forge/state/current/queue.json 2>/dev/null)"
  validation_json="$(cat .forge/state/current/validation.json 2>/dev/null)"
  recent_commits="$(git log --oneline -5 2>/dev/null || true)"

  cat <<PROMPT
Read the durable docs and operate as a long-horizon coding agent inside the active milestone.

## Session Protocol
1. Run: ./forge status
2. Read docs/prompt.md, docs/plans.md, docs/implement.md, docs/documentation.md
3. Read .forge/state/current/queue.json and pick the first task with status="pending" whose dependencies are all "done"
4. Implement that task without expanding scope beyond the active milestone
5. Update .forge/state/current/queue.json:
   - status="done" when the task is complete
   - status="blocked" and notes when you are truly blocked
6. Append a short note under "## Session Notes" in docs/documentation.md describing what changed and what is next
7. Run: ./forge qa
8. If QA fails, fix the failures before exiting
9. Stop after at most 3 tasks, or earlier if the remaining tasks are blocked or unavailable
10. Never edit docs/plans.md to open the next milestone. Humans do that via forge-open.

## Durable Spec
### docs/prompt.md
$prompt_doc

### docs/plans.md
$plans_doc

### docs/implement.md
$implement_doc

### docs/documentation.md
$documentation_doc

## Derived Runtime State
### queue.json
$queue_json

### validation.json
$validation_json

## Recent Commits
$recent_commits

## Rules
- Treat docs/plans.md as the source of truth for milestone scope
- Do not edit README.md, skill docs, or harness sources while implementing a product milestone
- Keep diffs scoped to the current available task(s)
- Use the same user-facing validation surface that humans will use
- Do not run git commit; checkpointing is handled outside the agent session
PROMPT
}

run_agent() {
  local prompt="$1"
  if [ "$AGENT" = "codex" ]; then
    codex exec --sandbox danger-full-access "$prompt" &
  else
    claude -p --verbose --output-format stream-json --dangerously-skip-permissions "$prompt" &
  fi
  CHILD_PID=$!
  wait "$CHILD_PID"
  local exit_code=$?
  CHILD_PID=""
  return "$exit_code"
}

python3 "$RUNTIME" sync >/dev/null

if [ -n "$RUN_ID" ]; then
  FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status running --pid "$$" >/dev/null
fi

PREV_PENDING="$(queue_value pending)"
TOTAL="$(queue_value total)"
AVAILABLE="$(queue_value available)"

echo "=== Forge Orchestrator ==="
echo "Agent: $AGENT"
echo "Run ID: ${RUN_ID:-standalone}"
echo "Tasks: $TOTAL total | $PREV_PENDING pending | $AVAILABLE available"

if [ "$TOTAL" -eq 0 ]; then
  echo "No active milestone. Run forge-open first."
  if [ -n "$RUN_ID" ]; then
    FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status idle >/dev/null
  fi
  exit 0
fi

if [ "$AVAILABLE" -eq 0 ] && [ "$PREV_PENDING" -gt 0 ]; then
  echo "No available tasks. Human intervention required."
  if [ -n "$RUN_ID" ]; then
    FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status needs_human >/dev/null
  fi
  exit 0
fi

while [ "$SESSION" -lt "$MAX_SESSIONS" ]; do
  SESSION=$((SESSION + 1))
  echo ""
  echo "=== Session $SESSION / $MAX_SESSIONS ==="
  PROMPT="$(build_prompt)"
  if ! run_agent "$PROMPT"; then
    echo "Agent session failed."
    FORGE_AUTO_COMMIT=0 "$SCRIPT_DIR/checkpoint.sh" || true
    if [ -n "$RUN_ID" ]; then
      FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status failed >/dev/null
    fi
    exit 1
  fi

  if ! FORGE_AUTO_COMMIT=1 "$SCRIPT_DIR/checkpoint.sh"; then
    echo "Checkpoint failed. Human review required."
    if [ -n "$RUN_ID" ]; then
      FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status needs_human >/dev/null
    fi
    exit 1
  fi

  CURRENT_PENDING="$(queue_value pending)"
  CURRENT_AVAILABLE="$(queue_value available)"
  CURRENT_DONE="$(queue_value done)"

  echo "Progress: $CURRENT_DONE/$TOTAL done | $CURRENT_PENDING pending | $CURRENT_AVAILABLE available"

  if [ "$CURRENT_PENDING" -eq 0 ]; then
    echo "Active milestone complete."
    if [ -n "$RUN_ID" ]; then
      FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status milestone_complete >/dev/null
    fi
    exit 0
  fi

  if [ "$CURRENT_AVAILABLE" -eq 0 ]; then
    echo "Only blocked/unavailable tasks remain. Human decision required."
    if [ -n "$RUN_ID" ]; then
      FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status needs_human >/dev/null
    fi
    exit 0
  fi

  if [ "$CURRENT_PENDING" -eq "$PREV_PENDING" ]; then
    STALL_COUNT=$((STALL_COUNT + 1))
    if [ "$STALL_COUNT" -ge 3 ]; then
      echo "No progress for 3 sessions. Stopping."
      if [ -n "$RUN_ID" ]; then
        FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status needs_human >/dev/null
      fi
      exit 0
    fi
  else
    STALL_COUNT=0
  fi

  PREV_PENDING="$CURRENT_PENDING"
done

if [ -n "$RUN_ID" ]; then
  FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status max_sessions >/dev/null
fi

echo "Reached max sessions."
