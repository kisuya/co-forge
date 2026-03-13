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

## Produces

- `docs/prd.md`
- `docs/architecture.md`
- `docs/backlog.md`
- `docs/prompt.md`
- `docs/documentation.md`
- `README.md`
- `AGENTS.md`
- installed Forge runtime via scaffold

## Workflow

### Step 1: Clarify the product boundary

Ask until the product is vivid:
- primary user
- core problem
- primary scenario step-by-step
- major branches and edge cases
- non-goals
- quality bar that must be true before users should trust the result
- primary failure modes that would make the product feel broken
- required user journeys that must work end to end
- validation surface the agent must use

Keep the discussion on user behavior before implementation details.

### Step 2: Draft the durable docs

If `AGENTS.md` or `docs/prompt.md` already exist, review and normalize them instead of forcing a separate manual scaffold path.
`forge-init` should remain the single guided entrypoint for first-time setup.

Write:
- `docs/prd.md`
- `docs/architecture.md`
- `docs/backlog.md`
- `docs/prompt.md`
- `docs/documentation.md`
- `README.md`
- `AGENTS.md`

Use the shared templates in `../../../.forge/templates/` when helpful.

### Step 3: Human review gate

Pause and explicitly review:
- product boundary
- non-goals
- validation surface
- done-when
- quality bar
- primary failure modes
- required user journeys

Encourage the user to edit wording directly if needed, then reflect that feedback.

### Step 4: Final approval before scaffold

Ask a direct approval question before installing anything:
- are the docs correct enough to freeze the target?
- is the validation surface real?
- is the harness ready to install?

### Step 5: Finalize

After explicit approval:

```bash
bash .forge/scripts/scaffold.sh
./forge doctor
./forge status
```

Even when docs already existed before the session, keep this finalize step inside `forge-init` after review and approval.

## Handoff

Print a short completion summary and stop.

```text
=== Init Complete ===
Next:
  /forge-open or $forge-open
```
