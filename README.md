# co-forge

AI와 함께 장기 자율 코딩을 굴리기 위한 하니스 템플릿.

Forge v2는 채팅 phase와 shell phase를 분리합니다.

- chat-native HITL phase: `/forge-init`, `/forge-open`, `/forge-close`
- shell-native execution phase: `./forge run`
- 관리 명령: `./forge status`, `./forge doctor`, `./forge upgrade`

이전 구조는 현재 커밋에 `v1` 태그로 보존했고, 기본 브랜치는 v2만 설명합니다.

## Quick Start

```bash
# 1. 이 템플릿으로 새 저장소 생성 후 clone
git clone https://github.com/YOU/YOUR-PROJECT.git my-project
cd my-project

# 2. 에이전트와 함께 초기화
#    Claude Code         Codex
> /forge-init           # $forge-init

# 3. 다음 milestone 열기
> /forge-open           # $forge-open

# 4. 자율 실행
./forge run             # 기본 agent: codex

# 5. 결과 리뷰 후 종결 또는 보류
> /forge-close          # $forge-close
```

반복 루프는 아래만 기억하면 됩니다.

```text
/forge-open -> ./forge run -> /forge-close
```

## 핵심 구조

```text
co-forge/
├── forge                              ← 사용자 진입점
├── .claude/skills/                    ← Claude용 chat-native phase skills
├── .agents/skills/                    ← Codex용 skill symlink
├── .forge/
│   ├── scripts/                       ← tracked Forge runtime implementation
│   ├── templates/                     ← tracked document templates
│   ├── references/                    ← tracked guidance/reference docs
│   ├── state/current/                 ← docs에서 파생된 실행 상태 (gitignore)
│   ├── runs/                          ← shell run 메타데이터 (gitignore)
│   ├── sessions/                      ← init/open/close phase 상태 (gitignore)
│   └── worktrees/                     ← 격리 실행 공간 (gitignore)
├── docs/
│   ├── prompt.md                      ← 목표/제약/검증 훅
│   ├── plans.md                       ← active milestone source of truth
│   ├── implement.md                   ← 실행 규칙
│   ├── documentation.md               ← shared memory + audit log
│   ├── user_scenarios.md              ← step-by-step 사용자 시나리오
│   ├── prd.md / architecture.md / conventions.md / tech_stack.md
│   ├── backlog.md
│   └── projects/                      ← archive snapshots
└── tests/
```

이 템플릿으로 만든 실제 프로젝트도 `.claude/skills/`와 `.agents/skills/`를 그대로 유지합니다.
`.claude`는 skill 전용이고, Forge의 tracked 구현과 runtime 상태는 모두 `.forge/` 아래에 둡니다.

## 사용자 모델

### 1. `/forge-init`

최초 1회만 사용합니다.

- 제품 아이디어를 사용자 시나리오 수준까지 선명하게 만듭니다.
- durable docs를 작성합니다.
- 사용자 리뷰를 거친 뒤 scaffold와 `./forge doctor`까지 실행합니다.

### 2. `/forge-open`

다음 milestone을 여는 HITL 세션입니다.

- backlog와 이전 회고를 검토합니다.
- 이번 milestone의 scope / acceptance / smoke scenario를 합의합니다.
- `docs/plans.md`를 리뷰 후 확정합니다.
- sync와 planning snapshot은 세션 내부에서 처리합니다.

### 3. `./forge run`

실행 전용 단계입니다.

- docs state를 sync합니다.
- active worktree가 있으면 기본적으로 resume합니다.
- resumable run이 없으면 새 isolated worktree를 엽니다.

추가 옵션:

- `./forge run --resume`
- `./forge run --fresh`
- `./forge run claude`

### 4. `/forge-close`

리뷰 우선 종결 세션입니다.

- 결과, validation, 남은 리스크를 먼저 검토합니다.
- 사람이 수정사항과 개선사항을 논의합니다.
- retrospective / backlog / durable docs를 반영합니다.
- 마지막 승인 후 archive합니다.
- 아직 닫지 않으면 deferred 상태로 남기고 나중에 이어갈 수 있습니다.

## Resume 모델

Forge v2는 resume를 기본 동작으로 둡니다.

- `./forge status`는 active phase session과 active run을 같이 보여줍니다.
- `/forge-init`, `/forge-open`, `/forge-close`는 unfinished session을 감지하면 resume합니다.
- `./forge run`은 resumable run이 있으면 기본 resume합니다.
- `close`는 `deferred` 상태를 지원합니다.

## 명령어

- `./forge run [claude|codex] [--resume|--fresh]` : active run resume 또는 새 isolated run 시작
- `./forge status` : active phase session, active run, milestone, QA 상태 표시
- `./forge doctor` : prerequisites / validation hook / docs sync 상태 점검
- `./forge upgrade` : 최신 Forge 하니스 반영

고급/내부 명령:

- `./forge qa`
- `./forge archive <name>`

## 설계 원칙

- 사람 판단이 필요한 단계는 채팅에서 끝냅니다.
- 기계적으로 오래 돌릴 단계만 shell로 뺍니다.
- validation은 가능한 한 실제 사용자 표면에서 수행합니다.
- 다음 milestone은 항상 사람이 다시 엽니다.

## License

MIT
