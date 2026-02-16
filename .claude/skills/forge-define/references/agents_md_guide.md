# Writing Effective AGENTS.md

## Keep Under 50 Lines

Every word costs context. Details belong in docs/.

Good: `## Architecture → docs/architecture.md`
Bad: 30 lines explaining the architecture inline.

## Essential Sections

1. **Project Overview** (1 sentence)
2. **Pointers to docs/** (3-4 lines)
3. **Absolute Rules** (5-7 items) — only rules agents commonly violate
4. **Session Start Protocol** (5-7 numbered steps)
5. **Project Context** (3-4 lines)

## Rules: Be Specific

Bad: "Write clean code."
Good: "Files must not exceed 300 lines."

Bad: "Test your code."
Good: "Run scripts/test_fast.sh before every commit."

## Only Include Rules That Agents Violate

- Agents "fix" failing tests → Rule: never modify tests
- Agents forget tracking → Rule: update features.json and progress.txt
- Agents run full test suites → Rule: use test_fast.sh
- Agents lose priorities → Rule: pick highest-priority pending feature

## Adapt Per Tech Stack

Python: mention pytest, pip, pyproject.toml
Node: mention npm, jest, package.json
Go: mention go test, go.mod
