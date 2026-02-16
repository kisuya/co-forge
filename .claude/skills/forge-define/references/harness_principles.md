# Harness Engineering Principles

Distilled from OpenAI and Anthropic harness engineering guides.

## 1. Code Is Documentation

Implementation details belong in code, not in docs.
- Directory structure, DB schema, API endpoints → read from the codebase
- docs/architecture.md records decisions and reasoning (WHY), not specifications (WHAT)
- If you can't know it before coding starts, don't write it down
- Wrong documentation is worse than no documentation — agents follow stale docs

Documents that duplicate code always drift. The only reliable spec is the code itself.

## 2. Fix the System, Not the Prompt

When agents fail, improve the harness (scripts, tests, structure) — not the prompt.
- Inconsistent formatting → add a linter
- Doesn't follow conventions → add structural tests
- Loses context → improve init.sh and progress.txt

AGENTS.md should be concise. The system does the heavy lifting.

## 3. Tests Are the Only Supervisor

No human watches the agent code. Tests catch mistakes.
- Tests must be reliable: no flaky tests
- Agents must NEVER modify existing tests
- Every feature needs tests alongside it
- Structural tests catch what unit tests miss

## 4. Context Window Management

- AGENTS.md = table of contents (~50 lines), details in docs/
- init.sh outputs only what's needed to start
- progress.txt is a summary, not a detailed log
- features.json uses JSON (not Markdown) for structure

## 5. Task Decomposition

One feature per session. Small, focused units.
- Each feature completable in one session
- Explicit dependencies (depends_on field)
- Agent picks highest-priority available feature
- "Done" = tests pass

## 6. Time Blindness Compensation

LLMs have no sense of time. They will wait 30 minutes for tests without noticing.
- test_fast.sh: under 30 seconds
- Timeouts on all commands
- AGENTS.md says "use test_fast.sh, not full suite"

## The Shift Worker Metaphor

Each session = a shift worker arriving at a factory.
- progress.txt = logbook
- init.sh = shift handoff briefing
- features.json = task board
- Tests = quality inspector
- AGENTS.md = employee handbook
