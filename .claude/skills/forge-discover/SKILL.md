---
name: forge-discover
description: >
  Validate a product idea and research the market before committing development resources.
  Use this skill whenever the user has a new product idea, wants to evaluate feasibility,
  check competitors, assess market size, or decide whether an idea is worth building.
  Triggers: "I have an idea", "is this worth building", "competitor analysis",
  "market research", "feasibility check", "validate my idea", "product discovery",
  "should I build this", "similar products".
  Part 1 of the forge suite (discover → define → project → retro).
disable-model-invocation: true
---

# Forge: Discover

Validate a product idea through feasibility analysis and market research.
The goal is a clear Go/No-Go decision backed by evidence.

**Produces:** `docs/ideation.md`, `docs/market_research.md`

## Reference Files

Read before starting:
→ `references/analysis_framework.md` — evaluation rubric, competitive analysis template, market sizing methods

## Execution Mode

**Interactive** (Cowork, Claude Code dialog, Codex dialog):
Ask the user clarifying questions at each step. Confirm findings before writing.

**Headless** (claude -p, codex --full-auto):
The idea must be fully described in the prompt. Skip clarification, proceed with best-effort research. Flag assumptions in the output documents.

## Workflow

### Step 1: Understand the Idea

Extract from the conversation or prompt:
- **Core value proposition**: What problem does this solve? For whom?
- **How it works**: High-level mechanism
- **Why now**: What makes this timely?

Interactive: Ask 2-3 focused questions if the idea is vague.
Headless: Work with whatever is provided. Note gaps as assumptions.

### Step 2: Technical Feasibility

- Does the required technology exist? Is it mature?
- Critical third-party API/data dependencies?
- Rough complexity estimate: weekend / month / quarter?
- Known hard problems?

Use web search to verify assumptions. Don't guess — look things up.

### Step 3: Competitive Landscape

Search for existing solutions:
- **Direct competitors**: Same core value proposition
- **Adjacent solutions**: Partial overlap
- **Open source alternatives**: Free options

For each: name, URL, pricing, strengths, weaknesses, differentiation.
Search broadly — product name, problem description, "alternatives to X", Product Hunt, community forums.

### Step 4: Market Assessment

- **Target user**: Be specific (not "developers" but "solo SaaS builders needing automated testing")
- **Market size**: Bottom-up estimation preferred
- **Trends**: Growing, shrinking, stable?
- **Timing**: Why hasn't this been built successfully yet?

### Step 5: Go/No-Go Decision

- **Go**: Feasible, differentiated, real market need
- **Conditional Go**: Feasible but significant risks (specify)
- **No-Go**: Fundamental blockers (explain what would need to change)

Be honest. A clear No-Go saves weeks.

### Step 6: Write Documents

**docs/ideation.md**:
```markdown
# Ideation: [Product Name]
## Core Idea
## Technical Feasibility
## Competitive Landscape
## Market Opportunity
## Risks (top 3 with mitigations)
## Recommendation (Go / Conditional Go / No-Go)
```

**docs/market_research.md**:
```markdown
# Market Research: [Product Name]
## Target User Profile
## Market Size Estimation
## Competitive Analysis (comparison table)
## Market Trends
## Opportunities
## Sources (all URLs used)
```

### Handoff

> 다음 단계: `/forge-define` 으로 PRD와 아키텍처를 정의합니다.
