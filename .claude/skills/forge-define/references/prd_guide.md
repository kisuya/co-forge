# PRD Writing Guide

## Prioritization: MoSCoW

- **Must Have (P0)**: Unusable without. Limit to 3-5 features.
- **Should Have (P1)**: Important, product works without. Sprint 2-3.
- **Could Have (P2)**: Nice additions. Backlog.
- **Won't Have**: Explicitly deferred. Prevents scope creep.

## Acceptance Criteria

Bad: "The login should work."
Good: "Valid credentials return JWT within 2s. Invalid credentials show error without revealing if email exists."

Each criterion: specific, testable, independent.

## Success Metrics by Product Type

**SaaS**: Activation rate, 30-day retention, core action frequency
**Dev Tools**: Setup-to-first-success time, daily usage, error rate
**Internal Tools**: Task completion time, error reduction, adoption rate

## Common Mistakes

1. Features without acceptance criteria — agents guess wrong
2. No "out of scope" — agents add unwanted features
3. Vague users — "developers" is meaningless, be specific
4. Missing non-functional requirements — performance is a feature
5. Too many P0s — if everything is critical, nothing is
