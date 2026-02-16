# Feature Decomposition Guide

## Right-Sizing Features

A well-sized feature for autonomous agent execution:
- Takes 30 min - 2 hours of coding work
- Touches 1-3 files (not counting tests)
- Has clear, testable acceptance criteria
- Can be committed independently without breaking the build
- Has a `description` that lets an agent implement without reading the full PRD

## Writing Good Descriptions

The `description` field is a mini-spec — the agent's only context for implementation.

Include:
1. **Inputs/outputs** — API paths, parameters, response shape
2. **Success behavior** — what happens when it works
3. **Error/edge cases** — what happens when it fails
4. **UX feedback** — what the user sees (toast, color, animation, loading state)
5. **Boundary conditions** — limits, defaults, ranges

Bad: `"name": "검색 결과 UX 개선"` (what exactly?)
Good: `"description": "검색 입력 시 결과 하이라이트, 외부 클릭 시 자동닫힘, 중복 방지, Escape 키로 닫기"`

Rule of thumb: if the agent would need to ask a clarifying question, the description is too vague.

## Too Large (Split It)

Signs a feature is too large:
- Description uses "and" multiple times ("create user model AND API endpoint AND frontend form")
- Touches more than 5 files
- Has more than 3 acceptance criteria
- Would take a human developer more than half a day

Split strategy: Extract each "and" into its own feature with explicit dependencies.

## Too Small (Merge It)

Signs a feature is too small:
- Just a config change or single-line edit
- No meaningful test can be written
- Would take less than 5 minutes

Merge with a related feature.

## Dependency Rules

- If feature B reads from a table that feature A creates → B depends_on A
- If feature B imports a module that feature A defines → B depends_on A
- If features touch completely different files → no dependency (can be in any order)
- Avoid chains longer than 3: A → B → C → D means D waits for everything

## ID Naming Convention

Format: `[domain]-[NNN]`

Examples:
- `auth-001`: Authentication domain, first feature
- `pay-001`: Payment domain
- `ui-001`: Frontend/UI domain
- `data-001`: Data pipeline domain
- `infra-001`: Infrastructure

Continue numbering across projects: if project1 ended at `auth-003`, project2's next auth feature is `auth-004`.

## Priority Assignment

Priority 1 = do first, 2 = do second, etc. Rules:
- Foundation features (models, core utilities) get lowest numbers
- Features with the most dependents get lower numbers
- UI/presentation features typically come after their backend dependencies
- No ties: if two features seem equally important, the one with more dependents wins
