---
name: forge-define
description: >
  Define a product and set up the agent harness. Produces PRD, architecture,
  conventions, tech stack, AGENTS.md, and installs all runtime infrastructure into .forge/.
  This is the only step needed between discovery and coding.
  Triggers: "write a PRD", "product spec", "tech stack", "architecture", "system design",
  "define the product", "set up harness", "create AGENTS.md", "prepare for coding",
  "API design", "choose framework", "coding conventions".
  Part 2 of the forge suite (discover → define → project → retro).
disable-model-invocation: true
---

# Forge: Define

Turn a validated idea into a concrete PRD, architecture plan, and working agent harness.

**Produces:**
- `docs/prd.md`, `docs/architecture.md`, `docs/conventions.md`, `docs/tech_stack.md`, `docs/backlog.md`
- `README.md` — product entry point
- `AGENTS.md` — agent instructions
- Harness: `.forge/scripts/`, `.forge/templates/`, `docs/projects/`, `tests/`

## Input Context

Check if these exist and read them (from forge-discover, optional):
- `docs/ideation.md`
- `docs/market_research.md`

If missing, ask the user to describe what they want to build (interactive) or expect it in the prompt (headless).

## Reference Files

→ `references/prd_guide.md` — prioritization, acceptance criteria, common mistakes
→ `references/architecture_patterns.md` — architecture choices, tech stack framework
→ `references/agents_md_guide.md` — writing effective AGENTS.md
→ `references/harness_principles.md` — core principles for agent harness design
→ `references/orchestration_guide.md` — execution models, anti-patterns

## Execution Mode

**Interactive**: Confirm product scope, MVP boundary, and tech preferences with the user.
**Headless**: Use discover outputs or prompt context. Make reasonable defaults, document all assumptions.

---

## Part A: Product Definition

### Step 1: Clarify Product Scope

Confirm:
- Product name and one-line description
- Primary user action (the single most important thing a user does)
- MVP boundary (what's in v1, what's explicitly deferred)
- Non-functional requirements (performance, security, scale)

Interactive: 2-3 focused questions.
Headless: Infer from docs/ideation.md or prompt.

### Step 2: Write the PRD

Write `docs/prd.md`. Key principles:
- Features specific enough for an agent to implement without guessing
- Each feature has acceptance criteria (testable, specific)
- Prioritize: P0 (must have), P1 (soon after), P2 (nice to have)
- Include explicit "Out of Scope" section

```markdown
# PRD: [Product Name]

## Overview
## Target User
## Core Features

### P0: Must Have
#### [Feature Name]
- Description:
- Acceptance criteria:
  - [ ] [Specific, testable]

### P1: Should Have
### P2: Nice to Have

## Out of Scope
## Success Metrics
## Constraints
```

### Step 3: Architecture Decision

Write `docs/architecture.md`. Only record **decisions and reasoning**, not implementation details:
- Architecture pattern (monolith, modular monolith, etc.) with rationale
- Tech stack choices with WHY (language, framework, DB engine)
- Key design decisions and trade-offs

**Do NOT pre-define** (code is the source of truth):
- Directory structure — emerges from code as features are built
- DB schema / data models — emerges from feature implementation
- API endpoints / specs — emerges from feature implementation

If it can't be known before coding starts, don't write it down. Wrong docs are worse than no docs.

### Step 4: Coding Conventions

Write `docs/conventions.md`:
- Language & style, naming, file organization (max length)
- Error handling, testing (framework, naming, coverage)

### Step 5: Tech Stack Reference

Write `docs/tech_stack.md` — quick-reference:
- Runtime, framework, database, testing, dev tools, dependencies, setup commands

### Step 6: Write README.md

Replace the template README with the product's own README:
- Product name and one-line description
- Quick start (setup, run, test)
- Link to `docs/` for detailed documentation

Keep it short. README is the entry point — details live in `docs/`.

---

## Part B: Agent Harness

### Step 7: Write AGENTS.md ← AI judgment

**This is the only harness step that needs AI reasoning.**

Read `references/agents_md_guide.md`. Write `AGENTS.md` in repo root:

- **Project Overview**: One sentence from docs/prd.md
- **Pointers to docs/**: 3-4 lines linking to prd, architecture, conventions, tech_stack
- **Absolute Rules** (5-7 items): Only rules agents commonly violate
  - Never modify tests
  - Run .forge/scripts/test_fast.sh before marking a feature done
  - Do NOT run git commit — checkpoint.sh handles commits between sessions
  - Update docs/projects/current/features.json when completing a feature
  - Append to docs/backlog.md if new features discovered (never modify features.json scope)
  - One file, one responsibility — split when a file handles multiple concerns
  - (add tech-stack-specific rules from docs/conventions.md)
- **Session Start Protocol**: `source .forge/scripts/init.sh`
- **Project Context**: points to docs/projects/current/

Keep under 50 lines. Every word costs context window.

### Step 8: Run Scaffold

Run the scaffold script to install all harness infrastructure:

```bash
bash [this skill's scripts/scaffold.sh]
```

The script automatically:
1. Creates `.forge/` directory structure (scripts/, templates/) and `docs/projects/current/`
2. Installs runtime scripts (init.sh, checkpoint.sh, new_project.sh, orchestrate.sh, upgrade.sh)
3. Generates test_fast.sh based on detected tech stack
4. Installs all templates (used by forge-define, forge-project, and forge-retro)
5. Creates project placeholders and smoke test
6. Creates `docs/backlog.md` for feature discovery tracking
7. Adds `docs/projects/current/` to .gitignore (active state is per-developer)
8. Initializes git if needed
9. Verifies the full structure

### Step 9: Git Commit

If scaffold.sh already created an initial commit (new git repo), verify all files are tracked.
Otherwise, commit:

```bash
git add -A
git commit -m "Initial harness setup (forge-define)"
```

### Step 10: Final Verify

After scaffold completes:
1. `.forge/scripts/init.sh` runs without errors
2. `.forge/scripts/test_fast.sh` passes smoke test
3. All docs/ files exist (including backlog.md, projects/current/)
4. AGENTS.md exists and is under 50 lines
5. `docs/projects/current/` is in .gitignore

### Handoff

> 하니스가 준비되었습니다. `/forge-project` (Claude) 또는 `$forge-project` (Codex) 로 첫 번째 프로젝트를 생성하세요.
>
> 자율 코딩 실행 모델은 `references/orchestration_guide.md` 를 참고하세요.
