---
name: forge-close
description: >
  Review and close the current milestone in an interactive HITL session. Use this when
  implementation has stopped and the user wants to inspect results, discuss fixes and
  follow-ups, update docs, and archive only after explicit approval.
disable-model-invocation: true
---

# Forge: Close

Close is a review-first session. Do not archive immediately. First inspect what shipped,
discuss must-fix items and follow-ups with the user, record them, and only then ask whether
the milestone should be closed or deferred.

## Reference Files

Read only as needed:
- `../../../.forge/references/retrospective_guide.md`
- `../../../.forge/references/harness_principles.md`

## Execution Mode

- Interactive only.
- Never archive before explicit user approval.
- Support both outcomes:
  - `Close Complete`
  - `Close Deferred`

## Reads

- `docs/documentation.md`
- `.forge/state/current/queue.json`
- `.forge/state/current/last_validation.json`
- `docs/backlog.md`
- recent `git log`
- active run metadata in `.forge/runs/current.json` when present

## Produces

- `docs/projects/<name>/retrospective.md`
- updated `docs/backlog.md`
- optional updates to durable docs
- archived milestone snapshot when the user approves closure

## Session State

Start or resume the phase session first:

```bash
python3 .forge/scripts/runtime.py session-start --phase close
```

- If the result says `"mode": "resume"`, show the saved review state first.
- Keep `deferred` sessions resumable.
- Only clear the phase session after a true close.

## Workflow

### Step 1: Gather objective data

Summarize:
- completed vs blocked tasks
- validation outcomes
- recent commits
- known issues

If `.forge/runs/current.json` points at a live worktree, treat that worktree as the source
of truth for review and archive.

### Step 2: Review with the user

Ask specifically:
- what is good enough now
- what must be fixed before closing
- what should move to backlog for the next milestone

Set session state to `awaiting_review`.

### Step 3: Classify the outcome

Sort feedback into:
- must-fix before close
- follow-up backlog items
- durable docs changes

Reflect the classification back to the user before writing it down.

Set session state to `applying_feedback`.

### Step 4: Record the result

Write:
- retrospective draft
- backlog follow-ups
- completed PRD items only
- durable docs changes when needed

### Step 5: Final approval gate

Ask directly whether the milestone should close now or stay open.

- If the user wants more work first:
  - set the phase session to `deferred`
  - leave archive untouched
  - point back to `./forge run --resume` or a later `/forge-close`
- If the user approves closure:
  - set the phase session to `finalizing`
  - archive inside this session

### Step 6: Finalize only after approval

For a real close:

```bash
python3 .forge/scripts/runtime.py session-update --session-id <id> --status finalizing --next-action "Archive the milestone snapshot."
python3 .forge/scripts/runtime.py archive-current <name>
python3 .forge/scripts/runtime.py session-complete --session-id <id>
```

For a deferred close:

```bash
python3 .forge/scripts/runtime.py session-complete --session-id <id> --status deferred
```

## Handoff

When closed:

```text
=== Close Complete ===
Next:
  /forge-open or $forge-open
```

When deferred:

```text
=== Close Deferred ===
Next:
  ./forge run --resume
  or later /forge-close
```
