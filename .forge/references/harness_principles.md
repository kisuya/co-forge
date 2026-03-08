# Harness Engineering Principles

Forge v2 assumes long-horizon runs succeed because the operating structure is strong, not because one prompt is magical.

## 1. Durable docs beat chat memory

Keep the stable target in files:
- `docs/prompt.md` freezes goals, constraints, deliverables, and validation hooks
- `docs/plans.md` defines the active milestone and its checks
- `docs/implement.md` is the runbook
- `docs/documentation.md` is shared memory + audit log

If a future agent cannot re-read the decision, it is not durable enough.

## 2. One public command surface

Humans should mostly remember `./forge ...`.
Internal `.forge/scripts/*` can exist, but they are implementation detail.

## 3. Source of truth vs derived state

Keep the boundary sharp:
- `docs/plans.md` = human-reviewed plan source
- `.forge/state/current/*.json` = machine-derived runtime state

Agents may update queue status, but they must not silently expand the plan.

## 4. Validate on the same surface the user uses

Static checks matter, but they are not enough.
- Web apps: run the local app and use browser-level validation
- APIs: hit the real API surface, not internal helpers
- CLI/SDKs: invoke the public interface the way a user would

## 5. Milestones, not endless drift

Long-horizon work still needs checkpoints:
- one active milestone at a time
- stop-and-fix on validation failure
- humans reopen or reshape the next milestone

## 6. Isolate long runs

Use worktrees, isolated state, and per-run metadata so a long autonomous run does not thrash the main working copy.

## 7. Docs must stay editable

Humans will review and tweak docs between runs.
- keep files short
- keep machine-managed areas explicitly marked
- never overwrite human sections in `docs/documentation.md`
