# Architecture Patterns & Tech Stack Framework

## Architecture Selection

**Monolith** (default for MVPs): Single codebase, simple testing, easy deployment. Best for agent-driven dev — agents see full picture.

**Modular Monolith**: Single deployment with clear module boundaries. Good for agents — clear scope per module.

**Microservices**: Avoid for agent-driven dev. Agents handle cross-service reasoning poorly.

## Tech Stack Decision

| Factor | Weight | Question |
|--------|--------|----------|
| User experience | High | What do they already know? |
| Ecosystem maturity | High | Good libraries for the domain? |
| Agent familiarity | Medium | Abundant training data? |
| Performance needs | Varies | PRD requirements? |

Agent familiarity ranking: Python > JS/TS > Java > Go > Rust

## Framework Selection

Prefer: well-documented, convention-over-config, widely adopted, stable.

## Database Selection

| Use Case | Choice | Why |
|----------|--------|-----|
| Most web apps | PostgreSQL | Versatile, great ecosystem |
| Simple/MVP | SQLite | Zero config, single file |
| Documents | MongoDB | Flexible schema |
| Real-time | Redis + PostgreSQL | Speed + durability |

## Design Decision Template

```markdown
### [Decision]
**Chose**: [What]
**Over**: [Alternatives]
**Because**: [Reasoning]
**Trade-offs**: [What we gave up]
**Revisit when**: [Trigger conditions]
```
