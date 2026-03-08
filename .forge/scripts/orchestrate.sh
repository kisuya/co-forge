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
SESSION_TASK_BUDGET="$(python3 "$RUNTIME" orchestration-setting session_task_budget 2>/dev/null || echo 6)"

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

has_material_worktree_changes() {
  # Session notes are mandatory housekeeping, not milestone progress.
  if [ -n "$(git status --porcelain 2>/dev/null | grep -v ' docs/documentation.md$' || true)" ]; then
    echo "1"
  else
    echo "0"
  fi
}

agent_profile_value() {
  local agent="$1"
  local key="$2"
  python3 "$RUNTIME" agent-profile "$agent" | python3 -c "import json,sys; print((json.load(sys.stdin).get(\"$key\") or \"\"))"
}

orchestration_setting_value() {
  local key="$1"
  python3 "$RUNTIME" orchestration-setting "$key"
}

build_prompt() {
  local prompt_doc plans_doc documentation_doc agents_doc queue_json recent_commits
  prompt_doc="$(cat docs/prompt.md 2>/dev/null)"
  plans_doc="$(cat docs/plans.md 2>/dev/null)"
  documentation_doc="$(cat docs/documentation.md 2>/dev/null)"
  agents_doc="$(cat AGENTS.md 2>/dev/null)"
  queue_json="$(cat .forge/state/current/queue.json 2>/dev/null)"
  recent_commits="$(git log --oneline -5 2>/dev/null || true)"

  cat <<PROMPT
Read the durable docs and operate as a long-horizon coding agent inside the active milestone.

## Session Protocol
1. Run: ./forge status
2. Read AGENTS.md, docs/prompt.md, docs/plans.md, docs/documentation.md
3. Read .forge/state/current/queue.json and choose one or more currently available tasks whose combined scope is still a tight, reviewable slice of the active milestone
4. Implement those tasks without expanding scope beyond the active milestone
5. Update .forge/state/current/queue.json:
   - status="done" when each completed task is complete
   - status="blocked" and notes when a task is truly blocked
6. Append a short note under "## Session Notes" in docs/documentation.md describing what changed and what is next
7. Run: ./forge qa
8. If QA fails, fix the failures before exiting
9. Stop after at most $SESSION_TASK_BUDGET completed tasks, or earlier if the remaining tasks are blocked or unavailable
10. Never edit docs/plans.md to open the next milestone. Humans do that via forge-open.

## Optional Parallelism
Use sub-agents or teammates only when they reduce wall-clock time without creating coordination risk.

Rules:
- The lead agent remains the only writer for .forge/state/current/queue.json, docs/documentation.md, checkpointing, QA, and landing
- Spawn workers only for:
  - read-only exploration
  - sidecar verification
  - implementation slices with clearly disjoint owned_paths
- If ownership is unclear, stay serial
- Before a worker starts, log it:
  python3 .forge/scripts/runtime.py worker-start --worker-id <id> --role <explorer|worker|verifier> [--task-id <task>]... [--owned-path <path>]...
- After a worker finishes, log it:
  python3 .forge/scripts/runtime.py worker-finish --worker-id <id> --status <success|failed|cancelled> --summary "<what happened>"
- Never give two write-capable workers overlapping owned_paths
- Workers must not edit docs/plans.md, .forge/state/current/queue.json, or run checkpoint/landing commands
- The lead agent integrates worker output, resolves conflicts, updates queue state, and runs QA

## Durable Spec
### docs/prompt.md
$prompt_doc

### docs/plans.md
$plans_doc

### AGENTS.md
$agents_doc

### docs/documentation.md
$documentation_doc

## Derived Runtime State
### queue.json
$queue_json

## Recent Commits
$recent_commits

## Rules
- Treat docs/plans.md as the source of truth for milestone scope
- Use docs/prompt.md and AGENTS.md for execution constraints and validation expectations
- Do not edit README.md, skill docs, or harness sources while implementing a product milestone
- Keep diffs scoped to the current available task slice
- Use the same user-facing validation surface that humans will use
- Do not run git commit; checkpointing is handled outside the agent session
PROMPT
}

run_agent() {
  local prompt="$1"
  local agent_model agent_profile agent_effort
  local -a cmd
  agent_model="$(agent_profile_value "$AGENT" model)"
  agent_profile="$(agent_profile_value "$AGENT" profile)"
  agent_effort="$(agent_profile_value "$AGENT" effort)"
  if [ "$AGENT" = "codex" ]; then
    cmd=(codex exec --sandbox danger-full-access)
    if [ -n "$agent_model" ]; then
      cmd+=(--model "$agent_model")
    fi
    if [ -n "$agent_profile" ]; then
      cmd+=(--profile "$agent_profile")
    fi
    cmd+=("$prompt")
  else
    cmd=(claude -p --verbose --output-format stream-json --dangerously-skip-permissions)
    if [ -n "$agent_model" ]; then
      cmd+=(--model "$agent_model")
    fi
    if [ -n "$agent_effort" ]; then
      cmd+=(--effort "$agent_effort")
    fi
    cmd+=("$prompt")
  fi
  "${cmd[@]}" &
  CHILD_PID=$!
  wait "$CHILD_PID"
  local exit_code=$?
  CHILD_PID=""
  return "$exit_code"
}

python3 "$RUNTIME" sync >/dev/null
SESSION_TASK_BUDGET="$(orchestration_setting_value session_task_budget 2>/dev/null || echo "$SESSION_TASK_BUDGET")"

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
  SESSION_MADE_CHANGES="$(has_material_worktree_changes)"

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

  if [ "$CURRENT_PENDING" -lt "$PREV_PENDING" ] || [ "$SESSION_MADE_CHANGES" = "1" ]; then
    STALL_COUNT=0
  else
    STALL_COUNT=$((STALL_COUNT + 1))
    if [ "$STALL_COUNT" -ge 3 ]; then
      echo "No measurable progress for 3 sessions. Stopping."
      if [ -n "$RUN_ID" ]; then
        FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status needs_human >/dev/null
      fi
      exit 0
    fi
  fi

  PREV_PENDING="$CURRENT_PENDING"
done

if [ -n "$RUN_ID" ]; then
  FORGE_MAIN_ROOT="$MAIN_ROOT" python3 "$RUNTIME" set-run-status --run-id "$RUN_ID" --status max_sessions >/dev/null
fi

echo "Reached max sessions."
