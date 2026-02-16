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
#   - Project retrospective (you do: /forge-retro)
#   - Next project creation (you do: /forge-project)

AGENT="${1:-claude}"
MAX_SESSIONS="${2:-20}"
SESSION=0
STALL_COUNT=0

# Validate agent
if [ "$AGENT" != "claude" ] && [ "$AGENT" != "codex" ]; then
  echo "Error: Unknown agent '$AGENT'. Use 'claude' or 'codex'."
  exit 1
fi

get_pending() {
  python3 -c "
import json
with open('.forge/projects/current/features.json') as f:
    data = json.load(f)
print(sum(1 for f in data['features'] if f['status'] != 'done'))
"
}

get_done() {
  python3 -c "
import json
with open('.forge/projects/current/features.json') as f:
    data = json.load(f)
print(sum(1 for f in data['features'] if f['status'] == 'done'))
"
}

build_prompt() {
  # Embed full context so the agent can work autonomously
  local SPEC=$(head -20 .forge/projects/current/spec.md 2>/dev/null)
  local FEATURES=$(cat .forge/projects/current/features.json 2>/dev/null)

  cat << PROMPT
Read AGENTS.md first, then follow these instructions.

## Session Protocol
1. Run: source .forge/scripts/init.sh
2. Read .forge/projects/current/features.json
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
- NEVER modify existing tests or docs/ files
- ALWAYS run ./.forge/scripts/test_fast.sh before marking a feature done
- ALWAYS update .forge/projects/current/features.json status to "done" after passing tests
- If blocked: set status to "blocked", commit, and exit
- If you discover a new feature is needed, append one line to docs/backlog.md and continue. Do NOT add it to features.json.
PROMPT
}

run_coding_session() {
  if [ "$AGENT" = "codex" ]; then
    codex --full-auto -q "$1"
  else
    claude -p "$1"
  fi
}

PREV_PENDING=$(get_pending)

echo "=== Forge Orchestrator ==="
echo "Agent: $AGENT"
echo "Max sessions: $MAX_SESSIONS"
echo "Project: $(head -1 .forge/projects/current/spec.md)"
echo "Pending features: $PREV_PENDING"
echo ""

if [ "$PREV_PENDING" -eq 0 ]; then
  echo "No pending features. Run /forge-project to create a new project first."
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

  CURRENT_PENDING=$(get_pending)

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

echo ""
echo "=== Orchestrator finished ==="
echo "Sessions: $SESSION"
echo "Features done: $(get_done)"
echo "Features remaining: $(get_pending)"
echo ""
echo "Next steps (interactive):"
echo "  1. Review:  cat .forge/projects/current/progress.txt"
echo "  2. Retro:   claude → /forge-retro"
echo "  3. Next:    claude → /forge-project"
