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

The archive snapshot must reflect the final approved worktree runtime state, including
the final queue and validation report, even though the archive itself is written into
the main workspace after landing.

## Workflow

### Step 1: Gather objective data

Summarize:
- completed vs blocked tasks
- validation outcomes
- acceptance coverage from `docs/plans.md [[validation_matrix]]`
- which tests or smoke checks were added or changed to satisfy the milestone
- recent commits
- known issues

If `.forge/runs/current.json` points at a live worktree, treat that worktree as the source
of truth for review, doc updates, and final landing.

### Step 2: Review with the user

Ask specifically:
- what is good enough now
- what must be fixed before closing
- what should move to backlog for the next milestone
- whether every acceptance item is covered by real tests or smoke checks, not only intention

### Step 3: Classify the outcome

Sort feedback into:
- must-fix before close
- follow-up backlog items
- durable docs changes
- acceptance or coverage gaps that still need product judgment

Reflect the classification back to the user before writing it down.

### Step 4: Record the result

Write:
- retrospective draft
- backlog follow-ups
- completed PRD items only
- durable docs changes when needed
- a short record of which acceptance items were proven by which tests or smoke checks, and any accepted coverage gap

When an active run worktree exists, write these changes in that worktree so the final
land step carries them back to the main branch.

### Step 5: Final approval gate

Ask directly whether the milestone should close now or stay open.

- If the user wants more work first:
  - leave archive untouched
  - point back to `./forge run --resume` or a later `/forge-close`
- If the user approves closure:
  - land and archive inside this session

### Step 6: Finalize only after approval

For a real close:

```bash
python3 .forge/scripts/runtime.py land-current <name>
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
