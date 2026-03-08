# Writing Effective AGENTS.md

Forge v2 AGENTS.md is a compact table of contents, not a wall of prose.

## Keep it short

Point outward:
- `docs/prompt.md`
- `docs/plans.md`
- `docs/documentation.md`
- `docs/backlog.md` when follow-up scope matters

Do not inline architecture or long product explanations.

## Include only the rules agents violate

Good examples:
- `docs/plans.md` active milestone is the scope boundary
- use `docs/plans.md` for task definitions and update only `.forge/state/current/queue.json` task status/notes
- run `./forge qa` before leaving a session
- append notes to `docs/documentation.md`
- start from a slim run brief, then read the real files from disk
- keep MCP usage opt-in and milestone-specific
- never run `git commit`
- never weaken or delete tests to hide failures
- allow existing tests to change only when behavior changed or the test is incorrect/flaky

Bad examples:
- “Write good code”
- “Think carefully”
- “Follow best practices”

## Start protocol

Prefer:
1. Run `./forge status`
2. Read durable docs
3. Use `docs/plans.md` for task definitions and `.forge/state/current/queue.json` for current status, then batch a small available task slice when it stays reviewable

Avoid pointing agents at hidden internal scripts unless that is the only safe entrypoint.
