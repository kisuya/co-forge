# Orchestration Guide

Forge v2 is a long-horizon harness built around durable docs, milestone execution, and a single public CLI.

## Core Loop

The reliable loop is:

1. Human freezes intent in docs
2. Agent reads docs + derived state
3. Agent edits code
4. Agent runs validation
5. Agent repairs failures
6. Agent updates queue status + documentation
7. Human reviews at milestone boundaries

## Public Command Surface

Users should mainly interact with:
- `./forge status`
- `./forge run [codex|claude]`
- `./forge upgrade`
- `./forge doctor`

Everything in `.forge/scripts/` is a backend implementation detail.

## Durable Document Stack

### `docs/prompt.md`
- frozen goal
- non-goals
- hard constraints
- deliverables
- validation command hooks
- default agent + execution profile

### `docs/plans.md`
- milestone plan source of truth
- exactly one active milestone
- tasks, task-level verification, acceptance, validation commands, smoke scenarios
- acceptance-to-test mapping via `[[validation_matrix]]`

### `docs/documentation.md`
- machine-managed status block
- session notes
- decisions
- run/demo notes
- known issues

## Runtime State

Generated from docs:
- `.forge/state/current/queue.json` (thin execution state: task status/notes only)
- `.forge/state/current/last_validation.json`

Run isolation:
- `.forge/runs/<run-id>/`
- `.forge/runs/<run-id>/workers.jsonl`
- `.forge/runs/<run-id>/worker-summary.json`
- `.forge/worktrees/<run-id>/`

## What Happens on `./forge run`

1. Sync durable docs into runtime state
2. Create or enter an isolated run worktree
3. Run the autonomous session loop for the active milestone
4. Checkpoint via `./forge qa`, reusing the latest passing result when the workspace is unchanged
5. Stop on milestone completion, blocked-only state, validation failure, or stall
6. Land the approved worktree back to the main branch during close
7. Archive the final approved worktree runtime state into the main workspace

## Validation Model

Every active milestone must define validation.
- static validation should be fast and deterministic
- surface validation should exercise the real user interface
- failures are repaired before forward motion

## Human Gates

Humans still own:
- discovery and user-scenario alignment
- scope changes and milestone opening
- retrospectives and durable process changes

Agents own:
- implementation inside the milestone
- validation execution
- queue status maintenance while leaving task definitions in `docs/plans.md`
- documentation updates in allowed sections
- batching a meaningful available task slice instead of forcing one tiny edit at a time
- making measurable progress, which includes either reducing pending work or producing real task changes before checkpoint; documentation session-note churn alone does not count
- using repo-owned tests and smoke scripts, not hiding verification logic inside ad hoc shell one-offs
- keeping one lead agent as the only writer when optional sub-agents or teammates are used
- logging worker start/finish so parallel work is observable later

## Anti-Patterns

- Directing users to raw `.forge/scripts/*` instead of `./forge`
- Letting agents edit `docs/plans.md` to open new scope
- Treating lint/test success as enough for UX-heavy products
- Mixing multiple active milestones at once
