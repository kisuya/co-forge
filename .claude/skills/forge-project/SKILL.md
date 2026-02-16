---
name: forge-project
description: >
  Create a new project phase for autonomous coding execution. Reviews backlog for
  discovered features, reads the PRD, determines what to build next, and generates
  spec.md and features.json. The AI focuses on scope selection and feature decomposition.
  Triggers: "create project", "next project", "new phase", "plan next sprint",
  "what should I build next", "generate features", "scope the next phase".
  Part 3 of the forge suite (discover → define → project → retro).
disable-model-invocation: true
---

# Forge: Project

Scope the next project phase. AI decides WHAT to build; templates define the output format.

**Produces:**
- `docs/projects/current/spec.md` (from `.forge/templates/spec_md.template`)
- `docs/projects/current/features.json` (from `.forge/templates/features_json.template`)
- `docs/projects/current/progress.txt` (from `.forge/templates/progress_txt.template`)

## Prerequisites

- Harness must exist: AGENTS.md, .forge/scripts/, .forge/templates/, tests/
- `docs/prd.md` must exist

**Retrospective check** (skip for the very first project):
If previous projects exist in `docs/projects/`, check the most recent one.
If it has NO `retrospective.md`:
- Interactive: "이전 프로젝트의 회고가 아직 안 됐습니다. 먼저 `/forge-retro` (Claude) 또는 `$forge-retro` (Codex) 를 실행하세요."
- Headless: Warn and abort.

If a project is still in progress (features with "pending" or "in_progress"):
- Interactive: Ask if the user wants to run `/forge-retro` (Claude) or `$forge-retro` (Codex) first
- Headless: Warn and abort.

## Reference Files

→ `references/feature_decomposition.md` — sizing rules, ID conventions, dependency patterns

## Workflow

### Step 0: Backlog Review ← AI + User

**This step ensures no discovered features or new ideas are lost.**

1. **Check `docs/backlog.md`**: If it contains items (lines starting with `-`):
   - Present all items to the user
   - For each: "prd.md에 반영할까요, 나중으로 미룰까요, 삭제할까요?"
   - Reflect accepted items into `docs/prd.md` with appropriate priority (P0/P1/P2)
   - Remove processed items from `docs/backlog.md`

2. **Ask for new ideas**: "지난번 이후에 추가하고 싶은 기능이나 아이디어가 있으세요?"
   - If yes: add to `docs/prd.md` with priority
   - If no: proceed

3. If backlog.md was empty AND user has no new ideas, skip silently.

### Step 1: Assess Remaining Backlog ← AI judgment

Read:
- `docs/prd.md` — full feature backlog (now updated from Step 0)
- `docs/architecture.md` — architecture decisions and tech stack
- Previous `docs/projects/*/retrospective.md` — lessons and deferred features
- Previous `docs/projects/*/features.json` — what's already been built

Scan `docs/projects/` for completed phases. Cross-reference with `docs/prd.md`:
- Which features are done?
- Which were deferred in retrospectives?
- What remains?

### Step 2: Scope the Next Phase ← AI judgment

**Interactive**: Present remaining backlog and ask:
- "이번 프로젝트에서 뭘 집중하고 싶으세요?"
- "기간은 어느 정도 예상하세요?"

**Headless**: Apply priority rules:
1. Deferred features from most recent retrospective
2. Next P0 features not yet built
3. Then P1, then P2
4. Scope to 3-7 features per phase

### Step 3: Generate Output Files

Read templates from `.forge/templates/` and fill in:

**spec.md** — read `.forge/templates/spec_md.template`, fill in:
- `{{PROJECT_NUMBER}}`, `{{PROJECT_NAME}}`, `{{GOAL}}`
- `{{CONTEXT}}`, `{{SCOPE}}`, `{{OUT_OF_SCOPE}}`

**features.json** — read `.forge/templates/features_json.template`, generate feature list:
- Each feature: 30 min - 2 hours of work
- Unique ID: `[domain]-NNN`
- `description`: agent-ready mini-spec — see `references/feature_decomposition.md` for 5 required elements
- Strict priority ordering, no ties
- Explicit dependency declarations

**progress.txt** — read `.forge/templates/progress_txt.template`, fill in:
- `{{PROJECT_ID}}`, `{{PROJECT_NAME}}`, `{{DATE}}`
- `{{FEATURE_COUNT}}`, `{{PREVIOUS_RETRO_PATH}}`

### Step 4: Git Commit

Commit backlog and PRD changes from Step 0 (docs/projects/current/ is gitignored):

```bash
git add docs/prd.md docs/backlog.md
git commit -m "Project [name]: update PRD and process backlog"
```

Skip if neither file was modified (empty backlog, no new ideas).

### Step 5: Verify

1. `docs/projects/current/features.json` is valid JSON
2. No circular dependencies
3. Feature IDs don't duplicate previous projects
4. Run `.forge/scripts/init.sh` — confirm it shows the new project correctly

### Handoff

Print this summary and stop. Do NOT start coding or execute orchestrate.sh.

```
=== Project Ready ===
Project: [name]
Features: [count]
Estimated sessions: [count / 3-5 features per session]

To start autonomous coding:
  $ ./.forge/scripts/orchestrate.sh claude    (or codex)

Or code interactively in this session.
```
