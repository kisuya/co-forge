---
name: forge-open
description: >
  Open the next milestone in an interactive HITL session. Use this when the user wants to
  review backlog, choose scope, define acceptance and validation, review docs/plans.md,
  and prepare the project for ./forge run.
disable-model-invocation: true
---

# Forge: Open

Open one active milestone and leave the project in a ready-to-run state. The user should
only approve scope and validation; sync and snapshotting happen inside this session.

## Prerequisites

- `./forge doctor` passes
- durable docs already exist
- the last milestone is either archived or intentionally still active

## Reference Files

Read only as needed:
- `../../../.forge/references/feature_decomposition.md`
- `../../../.forge/references/harness_principles.md`
- `../../../.forge/references/orchestration_guide.md`

## Execution Mode

- Interactive only.
- Treat this as a chat-native planning session.
- Never finalize the milestone before the user reviews `docs/plans.md`.
- Never ask the user to run a manual planning commit. Snapshotting is part of this phase.

## Produces

- `docs/plans.md`
- `.forge/state/current/queue.json`

## Also Modifies

- `docs/prompt.md`
- `docs/prd.md`
- `docs/architecture.md`
- `docs/backlog.md`
- `docs/documentation.md`

## Workflow

### Step 1: Review durable context

Read:
- `docs/prd.md`
- `docs/backlog.md`
- `docs/documentation.md`
- latest retrospective in `docs/projects/*/retrospective.md`

Extract:
- what value should ship next
- what still needs product judgment
- what validation is now required

### Step 2: Scope one active milestone

Work with the user to decide:
- what this milestone achieves
- what is explicitly out of scope
- what commands and smoke scenarios must pass
- whether any MCP is truly required for this milestone; keep `docs/prompt.md` `[orchestration].run_mcps` empty unless a concrete capability such as browser automation is needed

Keep the milestone small enough for one long-horizon run window.

### Step 3: Write and review `docs/plans.md`

Use `../../../.forge/templates/plans_md.template`.

Requirements:
- exactly one active milestone
- small task list
- real validation commands
- stop-and-fix enabled
- every acceptance item must map to one or more concrete tests or smoke checks via `[[validation_matrix]]`
- every task must define how completion will be verified before it can be marked done
- shell hooks should call repo-owned tests; do not hide the real test logic inside long shell scripts
- task granularity should let a frontier model complete a meaningful slice in one run session, not force one tiny edit at a time

Pause for human review once the plan is drafted.

### Step 4: Final approval gate

Before finalizing, explicitly confirm:
- in-scope vs out-of-scope
- acceptance criteria
- acceptance-to-test mapping
- smoke scenarios
- task-level verification steps
- readiness to hand the milestone to `./forge run`

### Step 5: Finalize inside the session

After explicit approval:

```bash
./forge status
python3 .forge/scripts/runtime.py snapshot-open
```

`snapshot-open` is the hidden planning snapshot. Do not push this back onto the user.

## Handoff

Print a short milestone summary and stop.

```text
=== Open Complete ===
Next:
  ./forge run
```
