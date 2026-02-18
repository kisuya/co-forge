# Feature Decomposition Guide

## From PRD to Features

PRD features are **product requirements** — what the product should do.
features.json entries are **implementation tasks** — what the agent actually builds.

**These are NOT the same thing. Do not copy PRD features 1:1 into features.json.**

### Decomposition principle: 사용자 행동 단위

Split PRD features by **what the user actually does**, not by PRD structure:

```
PRD: "F1. 관심 종목 등록/관리" (5 acceptance criteria)
  ↓ decompose by user action
features.json:
  watch-001: 종목 검색 API — 디바운스 자동완성, 500ms p95
  watch-002: 종목 추가/제거 — 카탈로그 검증, 토스트 피드백, 확인 다이얼로그
  watch-003: 관심 목록 대시보드 표시 — 시장 배지, 현재가, 빈 상태 안내
```

### How to map PRD → features

1. Read the PRD feature's acceptance criteria (only `[ ]` unchecked ones)
2. Group criteria by **user interaction boundary** (one screen, one API call, one flow)
3. Each group becomes one feature — write its description as an agent-ready mini-spec
4. One PRD feature typically yields 2-5 features.json entries
5. One features.json entry should address 1-3 acceptance criteria, not more

### Anti-patterns

- **1:1 복사**: PRD "F3. AI 변동 원인 분석 리포트" → features.json `analysis-001: AI 변동 원인 분석 리포트`
  (PRD 그대로 가져오면 agent가 무엇을 만들지 알 수 없음)
- **너무 기술적**: `auth-001: bcrypt 해싱 설정` (사용자 행동이 아닌 구현 디테일)
- **PRD 구조 답습**: PRD에 P0 11개면 features.json도 11개 (우연의 일치가 아니면 분해가 안 된 것)

### Good decomposition example

```
PRD: "F5. 사용자 인증 — 이메일+비밀번호 회원가입/로그인, JWT, bcrypt, 7일 유지"
  ↓
auth-001: 회원가입 폼 + API — email/password 입력, 유효성 검증, 중복 체크, 성공 시 로그인 페이지 이동
auth-002: 로그인/로그아웃 — JWT 발급, 7일 만료, 자동 갱신, 로그아웃 시 토큰 무효화
auth-003: 인증 미들웨어 — 보호 라우트 접근 제어, 만료 토큰 처리, 401 응답
```

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
