# co-forge

AI와 함께 코드를 만드는 작업장.

자율 코딩 에이전트(Claude Code, Codex)를 위한 개발 하니스입니다. 사람이 **무엇을(WHAT)** 결정하고, AI가 **어떻게(HOW)** 실행하며, 사람이 **왜(WHY)** 회고합니다.

## Quick Start

```bash
# 1. GitHub에서 "Use this template" 버튼으로 내 저장소 생성 (권장)
#    https://github.com/kisuya/co-forge → "Use this template" → "Create a new repository"
#    그 후 clone:
git clone https://github.com/YOU/YOUR-PROJECT.git my-project
cd my-project

# 또는 직접 clone (⚠ scaffold 시 origin 변경 안내가 나옵니다)
# git clone https://github.com/kisuya/co-forge.git my-project

# 2. 에이전트에서 스킬 실행
#    Claude Code              Codex
> /forge-discover          # $forge-discover     아이디어 검증
> /forge-define            # $forge-define       PRD + 아키텍처 + 하니스 설치
> /forge-project           # $forge-project      첫 프로젝트 스코핑

# 3. 자율 코딩 실행
./.forge/scripts/orchestrate.sh claude   # 또는 codex

# 4. 회고 후 다음 사이클
> /forge-retro             # $forge-retro        프로젝트 회고
> /forge-project           # $forge-project      다음 프로젝트
```

## 구조

```
co-forge/
├── .claude/skills/                    ← 스킬 원본 (Claude Code용, 클론하면 바로 활성화)
│   ├── forge-discover/                   아이디어 검증 + 시장 조사
│   ├── forge-define/                     PRD + 아키텍처 + 하니스 설치
│   │   ├── scripts/                      scaffold.sh 외 5개 (런타임 스크립트 원본)
│   │   └── templates/                    5개 (프로젝트 템플릿 원본)
│   ├── forge-project/                    프로젝트 스코핑 + 백로그 정리
│   └── forge-retro/                      프로젝트 회고
│
├── .agents/skills/                    ← Codex용 (symlink → .claude/skills/)
│
├── .forge/                            ← 런타임 (scaffold.sh가 생성)
│   ├── scripts/                          init.sh, checkpoint.sh, orchestrate.sh, upgrade.sh, ...
│   └── templates/                        spec_md, features_json, ...
│
├── AGENTS.md                          ← AI 에이전트 지침서
├── docs/                              ← 제품 문서 + 프로젝트 상태
│   ├── prd.md, architecture.md, conventions.md, tech_stack.md
│   ├── backlog.md                        기능 발견 수집함
│   └── projects/
│       ├── current/                      활성 프로젝트 (spec.md, features.json, progress.txt)
│       └── {archived}/                   완료된 프로젝트 + 회고록
├── src/                               ← 제품 코드
└── tests/                             ← 테스트
```

## 워크플로우

```
┌─────────────────────────────────────────────────────┐
│  사람이 결정 (Interactive)                            │
│  /forge-project → 백로그 정리 → 스코프 결정           │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  AI가 실행 (Autonomous)                              │
│  orchestrate.sh → 코딩 세션 → checkpoint.sh → 반복   │
│  (에이전트가 새 기능 발견 시 → docs/backlog.md에 기록) │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│  사람이 회고 (Interactive)                            │
│  /forge-retro → 교훈 정리 → AGENTS.md 개선           │
└──────────────────────┬──────────────────────────────┘
                       │
                       └──→ 다음 /forge-project (반복)
```

## 핵심 원칙

**토큰 효율성** — 기계적 작업(테스트 실행, 진행 기록, 디렉토리 생성)은 bash 스크립트가 처리합니다. AI 토큰은 판단이 필요한 작업에만 사용됩니다.

**교대 근무자 패턴** — 에이전트 세션은 들어와서 일하고 나갑니다. 하니스(.forge/)가 상태를 유지하고, 다음 에이전트에게 컨텍스트를 전달합니다.

**사람의 게이트** — 프로젝트 스코핑과 회고는 항상 사람이 참여합니다. 자율 코딩은 그 사이에서만 돌아갑니다.

## Git 추적 정책

| 경로 | 추적 | 이유 |
|------|:----:|------|
| `.claude/skills/` | O | 스킬 원본 |
| `.agents/skills/` | O | Codex용 symlink → `.claude/skills/` |
| `.forge/scripts/`, `.forge/templates/` | O | 팀이 동일한 인프라 공유 |
| `docs/projects/{archived}/` | O | 완료된 프로젝트 이력 (팀 공유) |
| `docs/projects/current/` | X | 활성 프로젝트 상태 (개발자별, .gitignore) |
| `AGENTS.md`, `docs/` | O | 제품 문서 |
| `src/`, `tests/` | O | 제품 코드 |

## 업그레이드

템플릿이 업데이트되면 파생 프로젝트에서 하네스만 선택적으로 업데이트할 수 있습니다.

```bash
./.forge/scripts/upgrade.sh
```

스킬, 스크립트, 템플릿이 최신 버전으로 갱신됩니다. 프로젝트 고유 파일(AGENTS.md, docs/, src/, tests/)은 건드리지 않습니다.

## 호환성

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — `.claude/skills/` (원본)
- [Codex](https://openai.com/index/openai-codex/) — `.agents/skills/` (symlink, clone 즉시 활성화)

## License

MIT
