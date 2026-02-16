#!/bin/bash
# Forge Orchestrator — automates the coding loop within a single project.
# Run this from your terminal, NOT from inside an agent session.
#
# Usage: ./.forge/scripts/orchestrate.sh [agent] [max-sessions]
#   agent:        "claude" (default) or "codex"
#   max-sessions: safety limit (default: 20)
#
# Flow per iteration:
#   1. AI coding session (headless) — implements features
#   2. checkpoint.sh (bash, no AI) — tests + progress update
#   3. Check: done? stuck? max reached? → exit or continue
#
# Does NOT do:
#   - Project retrospective (you do: /forge-retro or $forge-retro)
#   - Next project creation (you do: /forge-project or $forge-project)

AGENT="${1:-claude}"
MAX_SESSIONS="${2:-20}"
SESSION=0
STALL_COUNT=0
CHILD_PID=""
PID_FILE=".forge/orchestrate.pid"

# Validate agent
if [ "$AGENT" != "claude" ] && [ "$AGENT" != "codex" ]; then
  echo "Error: Unknown agent '$AGENT'. Use 'claude' or 'codex'."
  exit 1
fi

# Validate max-sessions is a positive integer
if ! [[ "$MAX_SESSIONS" =~ ^[1-9][0-9]*$ ]]; then
  echo "Error: max-sessions must be a positive integer, got '$MAX_SESSIONS'."
  exit 1
fi

# --- Signal handling: Ctrl+C / kill from another terminal ---
cleanup() {
  echo ""
  echo "=== Orchestrator interrupted ==="
  if [ -n "$CHILD_PID" ]; then
    # Kill the child process tree
    kill -TERM "$CHILD_PID" 2>/dev/null
    wait "$CHILD_PID" 2>/dev/null
  fi
  rm -f "$PID_FILE"
  exit 130
}
trap cleanup SIGINT SIGTERM

echo "$$" > "$PID_FILE"

get_pending() {
  local val
  val=$(python3 -c "
import json
with open('docs/projects/current/features.json') as f:
    data = json.load(f)
print(sum(1 for f in data['features'] if f['status'] != 'done'))
" 2>/dev/null) || val=""
  if [[ "$val" =~ ^[0-9]+$ ]]; then
    echo "$val"
  else
    echo "ERROR: Failed to read features.json" >&2
    echo "-1"
  fi
}

get_done() {
  local val
  val=$(python3 -c "
import json
with open('docs/projects/current/features.json') as f:
    data = json.load(f)
print(sum(1 for f in data['features'] if f['status'] == 'done'))
" 2>/dev/null) || val=""
  if [[ "$val" =~ ^[0-9]+$ ]]; then
    echo "$val"
  else
    echo "0"
  fi
}

build_prompt() {
  # Embed full context so the agent can work autonomously
  local SPEC=$(head -20 docs/projects/current/spec.md 2>/dev/null)
  local FEATURES=$(cat docs/projects/current/features.json 2>/dev/null)

  cat << PROMPT
Read AGENTS.md first, then follow these instructions.

## Session Protocol
1. Run: source .forge/scripts/init.sh
2. Read docs/projects/current/features.json
3. Find the FIRST feature with status="pending" whose dependencies are all "done"
4. Implement that feature following docs/prd.md and docs/architecture.md
5. Write tests for the feature
6. Run: ./.forge/scripts/test_fast.sh
7. If tests pass, update features.json: change that feature's status to "done"
8. Git commit: [FEATURE-ID] brief description
9. If time remains, pick the next available feature and repeat from step 3

## Current Project
$SPEC

## Feature List
$FEATURES

## Critical Rules
- NEVER modify existing tests or source docs (docs/prd.md, docs/architecture.md, etc.)
- Exception: you MUST update docs/projects/current/features.json and MAY append to docs/backlog.md
- ALWAYS run ./.forge/scripts/test_fast.sh before marking a feature done
- ALWAYS update docs/projects/current/features.json status to "done" after passing tests
- If blocked: set status to "blocked", commit, and exit
- If you discover a new feature is needed, append one line to docs/backlog.md and continue. Do NOT add it to features.json.
PROMPT
}

run_coding_session() {
  # Run agent in background + wait so that trap can fire on Ctrl+C.
  local exit_code=0
  if [ "$AGENT" = "codex" ]; then
    codex exec --full-auto "$1" &
  else
    # --dangerously-skip-permissions: autonomous mode requires no human approval.
    # The human gate is at forge-project and forge-retro, not during coding.
    claude -p --dangerously-skip-permissions "$1" &
  fi
  CHILD_PID=$!
  wait "$CHILD_PID" && exit_code=0 || exit_code=$?
  CHILD_PID=""
  return $exit_code
}

PREV_PENDING=$(get_pending)

if [ "$PREV_PENDING" -eq -1 ]; then
  echo "Error: Could not read docs/projects/current/features.json."
  echo "Run /forge-project (Claude) or \$forge-project (Codex) to create a project first."
  rm -f "$PID_FILE"
  exit 1
fi

echo "=== Forge Orchestrator ==="
echo "Agent: $AGENT"
echo "Max sessions: $MAX_SESSIONS"
echo "Project: $(head -1 docs/projects/current/spec.md)"
echo "Pending features: $PREV_PENDING"
echo ""

if [ "$PREV_PENDING" -eq 0 ]; then
  echo "No pending features. Run /forge-project (Claude) or \$forge-project (Codex) to create a new project first."
  rm -f "$PID_FILE"
  exit 0
fi

while [ "$SESSION" -lt "$MAX_SESSIONS" ]; do
  SESSION=$((SESSION + 1))
  echo ""
  echo "=============================="
  echo "  Session $SESSION / $MAX_SESSIONS"
  echo "=============================="

  # --- AI coding session (with full context) ---
  PROMPT=$(build_prompt)
  run_coding_session "$PROMPT"
  SESSION_EXIT=$?
  if [ "$SESSION_EXIT" -ne 0 ]; then
    echo ""
    echo "=== Agent session failed (exit code: $SESSION_EXIT) ==="
    echo "The agent process crashed or was not found. Stopping."
    ./.forge/scripts/checkpoint.sh || true
    break
  fi

  CURRENT_PENDING=$(get_pending)

  # --- Guard: features.json read failure mid-loop ---
  if [ "$CURRENT_PENDING" -eq -1 ]; then
    echo ""
    echo "=== Error reading features.json. Stopping. ==="
    ./.forge/scripts/checkpoint.sh || true
    break
  fi

  # --- Check completion ---
  if [ "$CURRENT_PENDING" -eq 0 ]; then
    echo ""
    echo "=== All features complete! ==="
    ./.forge/scripts/checkpoint.sh || echo "Warning: final checkpoint had issues"
    break
  fi

  # --- Check progress ---
  if [ "$CURRENT_PENDING" -gt "$PREV_PENDING" ]; then
    # Regression: more pending than before (agent broke something)
    echo ""
    echo "=== REGRESSION: pending increased ($PREV_PENDING → $CURRENT_PENDING) ==="
    echo "The agent may have broken state. Review features.json and recent commits."
    ./.forge/scripts/checkpoint.sh || true
    break
  elif [ "$CURRENT_PENDING" -eq "$PREV_PENDING" ]; then
    # No progress this session
    STALL_COUNT=$((STALL_COUNT + 1))
    echo "No feature completed this session (stall $STALL_COUNT/3)."
    if [ "$STALL_COUNT" -ge 3 ]; then
      echo ""
      echo "=== Stuck: no progress for 3 consecutive sessions ==="
      echo "Review progress.txt and recent commits."
      ./.forge/scripts/checkpoint.sh || true
      break
    fi
  else
    # Progress made — reset stall counter
    STALL_COUNT=0
  fi

  # --- Sprint checkpoint (bash, no AI tokens!) ---
  if ! ./.forge/scripts/checkpoint.sh; then
    echo ""
    echo "=== Checkpoint failed. Manual review needed. ==="
    break
  fi

  PREV_PENDING=$CURRENT_PENDING
done

rm -f "$PID_FILE"

echo ""
echo "=== Orchestrator finished ==="
echo "Sessions: $SESSION"
FINAL_DONE=$(get_done)
FINAL_PENDING=$(get_pending)
if [ "$FINAL_PENDING" -eq -1 ]; then
  echo "Features: unable to read (features.json may be broken)"
else
  echo "Features done: $FINAL_DONE"
  echo "Features remaining: $FINAL_PENDING"
fi
echo ""
echo "Next steps (interactive):"
echo "  1. Review:  cat docs/projects/current/progress.txt"
echo "  2. Retro:   /forge-retro (Claude) or \$forge-retro (Codex)"
echo "  3. Next:    /forge-project (Claude) or \$forge-project (Codex)"
