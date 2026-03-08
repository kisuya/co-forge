# Writing Effective AGENTS.md

Forge v2 AGENTS.md is a compact table of contents, not a wall of prose.

## Keep it short

Point outward:
- `docs/prompt.md`
- `docs/plans.md`
- `docs/implement.md`
- `docs/documentation.md`

Do not inline architecture or long product explanations.

## Include only the rules agents violate

Good examples:
- `docs/plans.md` active milestone is the scope boundary
- update only `.forge/state/current/queue.json` task statuses
- run `./forge qa` before leaving a session
- append notes to `docs/documentation.md`
- never run `git commit`

Bad examples:
- “Write good code”
- “Think carefully”
- “Follow best practices”

## Start protocol

Prefer:
1. Run `./forge status`
2. Read durable docs
3. Work from `.forge/state/current/queue.json`

Avoid pointing agents at hidden internal scripts unless that is the only safe entrypoint.
