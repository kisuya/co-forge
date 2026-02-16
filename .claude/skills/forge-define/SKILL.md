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
- `AGENTS.md` — agent instructions
- Harness: `.forge/scripts/`, `.forge/templates/`, `.forge/projects/`, `tests/`

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

Write `docs/architecture.md`:
- System type, tech stack with rationale, directory structure
- Data model, API design, key decisions with WHY

### Step 4: Coding Conventions

Write `docs/conventions.md`:
- Language & style, naming, file organization (max length)
- Error handling, testing (framework, naming, coverage), git commit format

### Step 5: Tech Stack Reference

Write `docs/tech_stack.md` — quick-reference:
- Runtime, framework, database, testing, dev tools, dependencies, setup commands

---

## Part B: Agent Harness

### Step 6: Write AGENTS.md ← AI judgment

**This is the only harness step that needs AI reasoning.**

Read `references/agents_md_guide.md`. Write `AGENTS.md` in repo root:

- **Project Overview**: One sentence from docs/prd.md
- **Pointers to docs/**: 3-4 lines linking to prd, architecture, conventions, tech_stack
- **Absolute Rules** (5-7 items): Only rules agents commonly violate
  - Never modify tests
  - Run .forge/scripts/test_fast.sh before every commit
  - Update .forge/projects/current/features.json when completing a feature
  - Append to docs/backlog.md if new features discovered (never modify features.json scope)
  - Files must not exceed 300 lines
  - (add tech-stack-specific rules from docs/conventions.md)
- **Session Start Protocol**: `source .forge/scripts/init.sh`
- **Project Context**: points to .forge/projects/current/

Keep under 50 lines. Every word costs context window.

### Step 7: Run Scaffold

Run the scaffold script to install all harness infrastructure:

```bash
bash [this skill's scripts/scaffold.sh]
```

The script automatically:
1. Creates `.forge/` directory structure (scripts/, templates/, projects/current/)
2. Installs runtime scripts (init.sh, checkpoint.sh, new_project.sh, orchestrate.sh)
3. Generates test_fast.sh based on detected tech stack
4. Installs all templates for forge-project and forge-retro
5. Creates project placeholders and smoke test
6. Creates `docs/backlog.md` for feature discovery tracking
7. Adds `.forge/projects/current/` to .gitignore (active state is per-developer)
8. Initializes git if needed
9. Verifies the full structure

### Step 8: Final Verify

After scaffold completes:
1. `.forge/scripts/init.sh` runs without errors
2. `.forge/scripts/test_fast.sh` passes smoke test
3. All docs/ files exist (including backlog.md)
4. AGENTS.md exists and is under 50 lines
5. `.forge/projects/current/` is in .gitignore

### Handoff

> 하니스가 준비되었습니다. `/forge-project` 로 첫 번째 프로젝트를 생성하세요.
>
> 자율 코딩 실행 모델은 `references/orchestration_guide.md` 를 참고하세요.
