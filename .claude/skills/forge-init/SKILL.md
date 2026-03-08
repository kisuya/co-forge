---
name: forge-init
description: >
  Start a Forge project in an interactive HITL session. Use this when the user wants to
  turn a product idea into durable docs, validation rules, and an installed Forge runtime.
  Includes discovery, definition, review, and scaffold.
disable-model-invocation: true
---

# Forge: Init

Run the first human-in-the-loop setup session for a project. This session should end with
durable docs, a reviewed target, and a working `./forge` harness.

## Reference Files

Read only as needed:
- `../../../.forge/references/analysis_framework.md`
- `../../../.forge/references/prd_guide.md`
- `../../../.forge/references/architecture_patterns.md`
- `../../../.forge/references/agents_md_guide.md`
- `../../../.forge/references/harness_principles.md`
- `../../../.forge/references/orchestration_guide.md`

## Execution Mode

- Interactive only.
- Treat this as a chat-native phase, not a shell-only workflow.
- Never run scaffold before explicit user approval.
- If interrupted, leave a resumable phase session behind.

## Produces

- `docs/prd.md`
- `docs/architecture.md`
- `docs/conventions.md`
- `docs/tech_stack.md`
- `docs/backlog.md`
- `docs/prompt.md`
- `docs/implement.md`
- `docs/documentation.md`
- `docs/user_scenarios.md`
- `README.md`
- `AGENTS.md`
- installed Forge runtime via scaffold

## Session State

Start or resume the phase session first:

```bash
python3 .forge/scripts/runtime.py session-start --phase init
```

- If the result says `"mode": "resume"`, summarize the saved state before asking anything new.
- Update progress after meaningful transitions with `session-update`.
- Finalize with `session-complete` only after scaffold + verification succeed.

## Workflow

### Step 1: Clarify the product boundary

Ask until the product is vivid:
- primary user
- core problem
- primary scenario step-by-step
- major branches and edge cases
- non-goals
- validation surface the agent must use

Keep the discussion on user behavior before implementation details.

### Step 2: Draft the durable docs

Write:
- `docs/user_scenarios.md`
- `docs/prd.md`
- `docs/architecture.md`
- `docs/conventions.md`
- `docs/tech_stack.md`
- `docs/backlog.md`
- `docs/prompt.md`
- `docs/implement.md`
- `docs/documentation.md`
- `README.md`
- `AGENTS.md`

Use the shared templates in `../../../.forge/templates/` when helpful.

Set session state to `drafting`, then `awaiting_review`.

### Step 3: Human review gate

Pause and explicitly review:
- product boundary
- user scenarios
- non-goals
- validation surface
- done-when

Encourage the user to edit wording directly if needed, then reflect that feedback.

Set session state to `applying_feedback`, then `awaiting_final_approval`.

### Step 4: Final approval before scaffold

Ask a direct approval question before installing anything:
- are the docs correct enough to freeze the target?
- is the validation surface real?
- is the harness ready to install?

### Step 5: Finalize

After explicit approval:

```bash
python3 .forge/scripts/runtime.py session-update --session-id <id> --status finalizing --next-action "Run scaffold and verify the harness."
bash .forge/scripts/scaffold.sh
./forge doctor
./forge status
python3 .forge/scripts/runtime.py session-complete --session-id <id>
```

## Handoff

Print a short completion summary and stop.

```text
=== Init Complete ===
Next:
  /forge-open or $forge-open
```
