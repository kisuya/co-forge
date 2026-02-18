---
name: forge-retro
description: >
  Run a project retrospective after autonomous coding is complete. Reviews what was built,
  captures lessons, updates AGENTS.md and architecture docs, archives the project.
  Interactive only — human judgment is essential for evaluating patterns and deciding
  on harness improvements. Output structure comes from templates.
  Triggers: "retrospective", "project done", "review the project", "what went well",
  "lessons learned", "archive project", "wrap up project".
  Part 4 of the forge suite (discover → define → project → retro).
disable-model-invocation: true
---

# Forge: Retro

Project retrospective. AI analyzes data and facilitates discussion; templates define output format.

**This skill is designed for interactive use.**

**Produces:**
- `docs/projects/{name}/retrospective.md` (from `.forge/templates/retrospective_md.template`)
- Updated `docs/architecture.md`
- Updated `README.md` (if needed)
- Updated `AGENTS.md` (if needed)

**Also modifies (Step 4):**
- `docs/prd.md` — completion status only (`[ ]` → `[x]`), no scope changes

## Reference Files

→ `references/retrospective_guide.md` — review approach, improvement patterns

## Prerequisites

- A project in `docs/projects/current/` with features marked "done"
- If no features done: "아직 완료된 기능이 없습니다. 먼저 코딩 세션을 실행하세요."

## Workflow

### Step 1: Gather Data (automated)

Collect objective facts. No judgment yet:

1. Read `docs/projects/current/features.json` — count done, deferred, remaining
2. Read `docs/projects/current/progress.txt` — count sessions, read notes
3. Run `git log` — commit history for this project
4. Run full test suite — record results
5. Calculate timeline from progress.txt dates
6. Read `docs/backlog.md` — check for items added by agents during coding

Present this data summary to the user before proceeding.

### Step 2: Discuss with the User ← AI judgment

Ask focused questions, one at a time:

- "이 프로젝트에서 가장 잘 된 부분은 뭐라고 생각하세요?"
- "에이전트가 반복적으로 실수한 패턴이 있었나요?"
- "다음 프로젝트에서 바꾸고 싶은 점이 있나요?"

Let the conversation flow naturally.

### Step 3: Review Backlog (do NOT modify PRD)

If `docs/backlog.md` has items added during this project:
- Present them to the user for awareness
- Discuss relevance and context, but do **NOT** update `docs/prd.md` here
- Annotate each item with retro context: `- [retro:{{project-name}}] original description`

If the discussion in Step 2 surfaced new feature ideas or improvements:
- Append them to `docs/backlog.md` with source tag: `- [retro] description`
- Do **NOT** add them directly to `docs/prd.md`

If no backlog items and no new ideas from discussion, skip.

**Why this boundary matters:** forge-retro looks backward (what did we learn?),
forge-project looks forward (what do we build next?). PRD changes are product scope
decisions that belong in forge-project Step 0, where they get proper prioritization
with full context of the upcoming phase.

### Step 4: Mark PRD Completion Status

Cross-reference features.json "done" features with PRD acceptance criteria.
This is **completion recording**, not scope modification — Step 3 boundary still applies.

1. For each "done" feature in features.json, find the corresponding PRD acceptance criteria
2. Mark completed criteria: `- [ ]` → `- [x]`
3. If ALL acceptance criteria of a PRD feature are checked, add `✅` to the feature header:
   `#### F1. 관심 종목 등록/관리` → `#### F1. 관심 종목 등록/관리 ✅`
4. If only some criteria are done, leave the header unmarked (partially complete)
5. Present the changes to the user for confirmation before saving

**Do NOT** add, remove, or reword any PRD content. Only toggle checkboxes.

### Step 5: Archive

Run `./.forge/scripts/new_project.sh [project-name]`

Suggest a descriptive name (e.g., "auth-and-user-management"). Let the user confirm.

### Step 6: Write Retrospective ← AI judgment

Read `.forge/templates/retrospective_md.template`. Fill in all `{{placeholders}}`
using data from Step 1 + user input from Step 2.

Write to `docs/projects/{name}/retrospective.md`.

Write this WITH the user — incorporate their exact words where possible.

### Step 7: Update Architecture ← AI judgment

Update `docs/architecture.md` with **decisions and reasoning only** (code is the source of truth for implementation details):
- New architectural decisions made during this project (e.g., "chose WebSocket over polling because...")
- Tech stack changes or additions with rationale
- Design trade-offs discovered during implementation

Do NOT duplicate implementation details that live in code (directory structure, DB schema, API endpoints).

Check `docs/conventions.md` for new patterns to formalize.

Review `README.md` — if it doesn't accurately reflect the current product (still template default, outdated setup steps, missing commands), update it.

### Step 8: Review AGENTS.md ← AI judgment (most impactful)

Changes here affect every future agent session.

Check:
- Rules agents violated → add specific rules
- Unnecessary or vague rules → remove or sharpen
- init.sh missing information → update script

Ask: "AGENTS.md에 추가하거나 바꿀 규칙이 있나요?"

### Step 9: Verify

1. `docs/projects/{name}/retrospective.md` — reviewed by user
2. `docs/architecture.md` — matches codebase
3. `AGENTS.md` — accurate and actionable
4. `docs/projects/current/` — clean slate
5. Full test suite passes
6. `docs/backlog.md` — reviewed and annotated (items preserved for forge-project to process)
7. `docs/prd.md` — completion checkboxes match features.json status

### Step 10: Git Commit

Commit all retrospective changes:

```bash
git add -A
git commit -m "Retrospective: [project-name]"
```

This captures: retrospective.md, updated architecture.md, updated AGENTS.md, annotated backlog.md, PRD completion status.

### Handoff

```
=== Retrospective Complete ===
Project: [name]
Sessions: [count]
Features completed: [N], deferred: [M]
Key improvements: [1-2 line summary]

Next: /forge-project (Claude) or $forge-project (Codex)
```
