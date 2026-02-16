# Retrospective Guide

## Why Retrospectives Matter

In agent-driven development, each session starts with zero memory. The retrospective is the primary mechanism for transferring lessons across project phases.

A good retrospective helps:
1. The **human** understand what happened and make better decisions
2. **Future agent sessions** understand past work and pitfalls

## Data Gathering (Before Writing)

Collect concrete data:
- **features.json**: Planned vs completed, priority adherence, dependency bottlenecks
- **Git log**: Commit frequency/size (large = agent did too much at once, many "fix" = test failures)
- **Test results**: Count, coverage, flaky tests
- **progress.txt**: Development flow, stuck points

## Patterns to Look For

**Scope creep**: Features not in features.json were built, files outside scope modified, unexpected dependencies added.

**Quality signals**: Test coverage increased per feature, no existing tests broken, conventions followed.

**Efficiency signals**: Priority order respected, dependencies honored, no duplicate work.

## Improvement Categories

### Harness Improvements
Changes to AGENTS.md, scripts, structure:
- "init.sh should show test coverage"
- "features.json needs finer dependency tracking"

### Process Improvements
Changes to scoping and planning:
- "Features were too large — split more next time"
- "Need architecture decision records for non-obvious choices"

### Technical Debt
Code issues to address:
- "Inconsistent error handling across modules"
- "Missing integration tests between components"

## Anti-Patterns

1. Vague observations — what specifically, how to fix?
2. No action items — every observation needs a concrete change
3. Ignoring wins — document what worked so you keep doing it
4. Copy-paste template — each retrospective must be specific

## Connecting to Next Project

- Deferred features → next project's backlog
- Technical debt → prioritize if it blocks progress
- Process improvements → apply to next phase
- Harness changes → implement before next agent run
