# Orchestration Guide

## Core Principle

Every agent session does ONE job: work, report, and exit.
The decision of what happens next is ALWAYS made outside the agent session —
either by a human or by an external bash script.

```
CORRECT:
  [external] → agent session → work → report → exit
  [external] → check state → decide next action
  [external] → agent session → work → report → exit

WRONG:
  [agent session] → spawns another agent session  ← nested agent
  [agent skill] → contains orchestration loop     ← role confusion
```

## The Forge Suite (4 Skills + 5 Scripts)

### AI Skills — judgment required

| # | Skill | Role | Execution |
|---|-------|------|-----------|
| 1 | forge-discover | Idea validation, market research | Interactive |
| 2 | forge-define | PRD, architecture, AGENTS.md, harness scaffold | Interactive |
| 3 | forge-project | Backlog review, project scoping, features.json | Interactive |
| 4 | forge-retro | Project retrospective, backlog processing | Interactive |

Skills 1-2 run once at the start. Skills 3-4 form the repeating cycle.

forge-define also triggers `scaffold.sh` (one bash command) to install all infrastructure into `.forge/`.
No separate setup skill needed.

### Bash Scripts — no AI tokens needed

All scripts live in `.forge/scripts/` (gitignored).

| Script | Role | Called by |
|--------|------|----------|
| scaffold.sh | One-time harness install (dirs, scripts, templates, tests) | forge-define (once) |
| init.sh | Session briefing (project state, pending features) | Coding agent at session start |
| checkpoint.sh | Sprint checkpoint (tests, progress update) | orchestrate.sh after each session |
| new_project.sh | Archive current project, clean slate | forge-retro at the end |
| orchestrate.sh | Autonomous coding loop | User's terminal |

### Repo Structure After Scaffold

```
my-project/
├── .claude/
│   └── skills/            ← git tracked (project-level skills)
│       ├── forge-discover/
│       ├── forge-define/  ← includes scripts/ and templates/ source
│       ├── forge-project/
│       └── forge-retro/
├── .forge/                ← git tracked (runtime infrastructure)
│   ├── scripts/           ← copied from forge-define/scripts/ by scaffold.sh
│   ├── templates/         ← copied from forge-define/templates/ by scaffold.sh
│   └── projects/
│       ├── current/       ← GITIGNORED (per-developer working state)
│       └── {archived}/    ← git tracked (completed projects + retrospective)
├── AGENTS.md              ← git tracked
├── docs/                  ← git tracked
│   ├── prd.md, architecture.md, conventions.md, tech_stack.md
│   └── backlog.md         ← shared: agents append, humans add ideas
├── src/                   ← git tracked (product code)
├── tests/                 ← git tracked (product tests)
└── .gitignore             ← ".forge/projects/current/" only
```

## Feature Discovery Flow (docs/backlog.md)

Features emerge from three sources:
1. **During coding** — agent discovers "this also needs X" → appends to docs/backlog.md
2. **Between projects** — human thinks of ideas → adds to docs/backlog.md or tells AI
3. **During retro** — discussion reveals missing features → added to prd.md directly

The backlog is processed at two points:
- **forge-retro Step 3**: Process items from the just-completed project
- **forge-project Step 0**: Process any remaining items + ask for new ideas

This ensures prd.md is always up to date before project scoping, regardless of
whether retro was run.

## Two Execution Patterns

### Pattern 1: Interactive Development

The user works with the agent directly. No automation.

```
[Claude Code interactive session]

> /forge-project                       ← scope the work (includes backlog review)
> (code together with the agent)
> .forge/scripts/checkpoint.sh         ← quick checkpoint when you want
> (continue coding)
> /forge-retro                         ← project done → retrospective
> /forge-project                       ← next project
```

Best for: small projects, learning the workflow, when you want control.

### Pattern 2: Autonomous with Human Gates

Coding + sprint checkpoints are automated. Retro + project scoping are human.

```
[Interactive] > /forge-project                      ← human scopes the work
[Terminal]    $ ./.forge/scripts/orchestrate.sh      ← script automates coding loop
                → coding session 1 → checkpoint.sh
                → coding session 2 → checkpoint.sh
                → coding session 3 → all features done → exit
[Interactive] > /forge-retro                        ← human does retrospective
[Interactive] > /forge-project                      ← human scopes next project
[Terminal]    $ ./.forge/scripts/orchestrate.sh      ← automate again
```

The cycle:
1. **Human decides WHAT** → /forge-project (interactive, includes backlog review)
2. **Machine does HOW** → orchestrate.sh (autonomous, agents append to backlog)
3. **Human reflects WHY** → /forge-retro (interactive, processes backlog)
4. Repeat

Best for: most projects. Maximizes token usage while keeping human judgment at decision points.

## Why checkpoint.sh Is a Script, Not a Skill

Sprint checkpoints are entirely mechanical:
- Run tests → pass/fail
- Count done/pending features → numbers
- Append session entry to progress.txt → templated text

No AI judgment is needed. Running this as an AI skill wastes a full agent session
(context window, tokens, latency) on work that bash does in 2 seconds.

## Why Retrospective Is a Separate Skill

Sprint checkpoints and project retrospectives are fundamentally different:

| | checkpoint.sh | forge-retro |
|---|---|---|
| When | Between coding sessions | After project completion |
| Nature | Mechanical | Judgment-heavy |
| Execution | Bash script (no AI) | Interactive (AI + human) |
| Frequency | Many per project | Once per project |
| Duration | ~2 seconds | ~15-30 minutes |
| Output | progress.txt update | retrospective.md + doc updates |

## orchestrate.sh Design Principles

1. **Automates sprints only**: Coding sessions + checkpoint.sh. Never retrospectives.
2. **One session = one purpose**: Don't combine coding and review in the same session.
3. **State checks are external**: Read features.json with python3, not inside an agent.
4. **Checkpoints are bash**: `./.forge/scripts/checkpoint.sh`, not an AI session. Zero tokens.
5. **Stuck detection**: If pending count doesn't decrease, stop. The agent is stuck.
6. **Max session limit**: Always cap iterations. Default 20.
7. **Agent-agnostic**: Support both claude and codex via parameter.
8. **Clear exit message**: Tell the user to run /forge-retro next.

## What Goes WHERE

| Content | Location | Executed by |
|---------|----------|-------------|
| Coding + sprint loop | .forge/scripts/orchestrate.sh | User's terminal (bash) |
| Session briefing | AGENTS.md + .forge/scripts/init.sh | Coding agent (headless) |
| Sprint checkpoint | .forge/scripts/checkpoint.sh | orchestrate.sh (bash) |
| Project retrospective | .claude/skills/forge-retro/ | User + agent (interactive) |
| Project scoping | .claude/skills/forge-project/ | User + agent (interactive) |
| Feature state | .forge/projects/current/features.json | Agents + scripts (shared) |
| Progress log | .forge/projects/current/progress.txt | Agents + scripts (shared) |
| Feature discovery | docs/backlog.md | Agents (append) + humans (add) |

## Anti-Patterns

- **Agent calling agent**: A session running `claude -p` inside itself
- **Skill containing orchestration**: A SKILL.md with a while loop that spawns sessions
- **AI doing mechanical work**: Using an agent session for tests + feature counting
- **Separate setup skill**: Wasting a full AI session on mkdir + file copy
- **Headless retrospective**: Running forge-retro without human input
- **Skipping backlog review**: Running /forge-project without checking docs/backlog.md
- **Implicit role**: Instructions that blur agent vs user responsibilities
- **Unbounded loops**: orchestrate.sh without max iteration or stuck detection
- **Agent modifying features.json scope**: Agent should only change status, never add new features
