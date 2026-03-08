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
- `.forge/state/current/validation.json`

## Also Modifies

- `docs/prd.md`
- `docs/backlog.md`
- `docs/documentation.md`

## Session State

Start or resume the phase session first:

```bash
python3 .forge/scripts/runtime.py session-start --phase open
```

- If the result says `"mode": "resume"`, summarize the unfinished milestone-opening state first.
- Update progress with `session-update`.
- Complete only after sync + snapshot succeed.

## Workflow

### Step 1: Review durable context

Read:
- `docs/prd.md`
- `docs/backlog.md`
- `docs/user_scenarios.md`
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

Keep the milestone small enough for one long-horizon run window.

Set session state to `clarifying`, then `drafting`.

### Step 3: Write and review `docs/plans.md`

Use `../../../.forge/templates/plans_md.template`.

Requirements:
- exactly one active milestone
- small task list
- real validation commands
- stop-and-fix enabled

Pause for human review once the plan is drafted.

Set session state to `awaiting_review`, then `applying_feedback`.

### Step 4: Final approval gate

Before finalizing, explicitly confirm:
- in-scope vs out-of-scope
- acceptance criteria
- smoke scenarios
- readiness to hand the milestone to `./forge run`

Set session state to `awaiting_final_approval`.

### Step 5: Finalize inside the session

After explicit approval:

```bash
python3 .forge/scripts/runtime.py session-update --session-id <id> --status finalizing --next-action "Sync state and create the planning snapshot."
./forge status
python3 .forge/scripts/runtime.py snapshot-open
python3 .forge/scripts/runtime.py session-complete --session-id <id>
```

`snapshot-open` is the hidden planning snapshot. Do not push this back onto the user.

## Handoff

Print a short milestone summary and stop.

```text
=== Open Complete ===
Next:
  ./forge run
```
