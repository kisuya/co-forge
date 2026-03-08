# Milestone And Task Planning Guide

Forge v2 plans work in two levels:
- milestone = human-reviewed chunk with one validation boundary
- task = small implementation unit inside that milestone

## Milestone sizing

A good active milestone:
- has one clear user outcome
- can be validated end-to-end
- is small enough to finish in one autonomous run window
- does not require the agent to invent missing product decisions

## Task sizing

A good task:
- is concrete enough to implement without guessing
- has clear dependencies
- can usually finish in one focused edit/validate cycle
- maps to visible progress inside the milestone

## Avoid these planning mistakes

- Milestone too big: “build the whole dashboard”
- Task too vague: “improve UX”
- Hidden scope: tasks that require product choices not written anywhere
- Missing validation: no command or smoke scenario proving the milestone works

## Preferred decomposition flow

1. Start from the user scenario
2. Define the milestone outcome
3. Split into tasks that move the user toward that outcome
4. Add dependency edges only where truly required
5. Attach validation commands and smoke scenarios

## Validation rule

Every active milestone must answer:
- what command proves the code is structurally sound?
- what interaction proves the user can actually use it?
- what happens if either fails?
