# co-forge

`co-forge`는 기존 소프트웨어 프로젝트에 설치해 사용하는 AI 코딩 워크플로 하네스입니다.  
milestone 계획, 구현 실행, 검증, 리뷰를 같은 저장소 안에서 이어서 운영할 수 있게 합니다.

## Overview

co-forge는 AI 에이전트를 무제한으로 풀어 두는 도구가 아니라, 사람이 scope와 validation을 정한 뒤 milestone 단위로 실행하는 워크플로입니다.

핵심 구성은 아래 세 가지입니다.

- chat-native HITL phases: `forge-init`, `forge-open`, `forge-close`
- shell-native runtime: `./forge run`, `./forge status`, `./forge doctor`
- npm-based management CLI: `co-forge install`, `co-forge upgrade`, `co-forge uninstall`

## Execution Context

| 실행 위치 | 용도 | 명령 |
| --- | --- | --- |
| Claude Code 채팅 세션 | HITL phase 진행 | `/forge-init`, `/forge-open`, `/forge-close` |
| Codex 채팅 세션 | HITL phase 진행 | `$forge-init`, `$forge-open`, `$forge-close` |
| 프로젝트 루트 터미널 | 설치, 런타임 실행, 상태 확인 | `co-forge ...`, `./forge ...` |

## Why co-forge

### Strengths

- 계획, 실행, 검증, 회고를 같은 저장소 안에서 이어서 관리할 수 있습니다.
- resumable run과 isolated worktree를 기준으로 긴 작업을 끊어서 이어가기 쉽습니다.
- 문서 기반 milestone 운영을 강제해서 scope drift와 애매한 완료 기준을 줄입니다.
- 기존 코드베이스에 설치하는 방식이라 새 템플릿 repo 없이도 도입할 수 있습니다.

### Trade-offs

- 짧은 1회성 작업보다 milestone 단위로 나눠서 운영할 때 효과가 큽니다.
- 문서와 validation을 유지해야 하므로 초기 설정 비용이 있습니다.
- shell run을 실제로 굴리려면 `codex` 또는 `claude` CLI 같은 실행 에이전트가 필요합니다.
- 무계획 자율 실행 도구가 아니라, 사람이 범위와 검증 기준을 계속 잡아 주는 워크플로에 가깝습니다.

## Installation

### Requirements

설치와 관리에 필요한 것:

- `git`
- `python3`
- `npm`

shell runtime 실행에 추가로 필요한 것:

- `codex` 또는 `claude` CLI 중 최소 하나

### Install The CLI

한 번만 설치하면 됩니다.

```bash
npm install -g co-forge
```

또는 설치 없이 바로 확인할 수 있습니다.

```bash
npx co-forge --help
```

### Install Into A Project

프로젝트 루트에서 실행합니다.

```bash
cd your-project
co-forge install
```

다른 경로를 직접 지정할 수도 있습니다.

```bash
co-forge install ../my-project
co-forge install /absolute/path/to/project
```

경로를 생략하면 현재 디렉터리를 대상으로 하고, 경로를 주면 그 프로젝트를 대상으로 작업합니다.

### Upgrade Or Remove

```bash
co-forge upgrade
co-forge upgrade /absolute/path/to/project

co-forge uninstall
co-forge uninstall ../my-project
```

`uninstall`은 co-forge가 관리하는 하네스 파일만 제거하고, 사용자 문서(`AGENTS.md`, `docs/*`)는 남겨 둡니다.

## Quick Start

### 1. Install The CLI (터미널, 1회)

```bash
npm install -g co-forge
```

### 2. Install Into A Project (터미널, 프로젝트별)

이 단계는 `forge`, `.forge/`, skill entrypoint 같은 실행 기반을 넣는 단계이고, 프로젝트 문서까지 만들지는 않습니다.

```bash
cd your-project
co-forge install
```

### 3. Initialize The Project (채팅 세션)

Claude Code에서는 `/forge-init`, Codex에서는 `$forge-init`을 사용합니다.

```text
/forge-init
or $forge-init
```

이 단계에서 보통 아래 파일들이 정리됩니다.

- `AGENTS.md`
- `docs/prd.md`
- `docs/architecture.md`
- `docs/backlog.md`
- `docs/prompt.md`
- `docs/documentation.md`

이미 일부 문서가 있더라도 보통은 같은 명령으로 시작하면 됩니다.  
`forge-init`이 기존 문서를 리뷰하고 필요한 내용을 보정한 뒤 scaffold까지 이어서 처리합니다.

### 4. Open A Milestone (채팅 세션)

Claude Code에서는 `/forge-open`, Codex에서는 `$forge-open`을 사용합니다.

```text
/forge-open
or $forge-open
```

이 단계의 source of truth는 `docs/plans.md`입니다.

### 5. Run The Milestone (터미널)

프로젝트 루트에서 실행합니다.

```bash
./forge run
```

필요하면 agent나 실행 모드를 지정할 수 있습니다.

```bash
./forge run claude
./forge run --resume
./forge run --fresh
```

### 6. Review And Close (채팅 세션)

Claude Code에서는 `/forge-close`, Codex에서는 `$forge-close` 명령을 사용합니다.

```text
/forge-close
or $forge-close
```

초기 설정 이후의 일상 루프는 아래만 기억하면 됩니다.

```text
Claude Code: /forge-open -> ./forge run -> /forge-close
Codex:       $forge-open -> ./forge run -> $forge-close
```

## Phase Responsibilities

### `forge-init`

- 제품 경계, 사용자 시나리오, 품질 기준을 정리합니다.
- `docs/prd.md`, `docs/architecture.md`, `docs/backlog.md`, `docs/prompt.md` 같은 durable docs를 만듭니다.
- 문서 리뷰 후 scaffold와 `./forge doctor`까지 진행합니다.

### `forge-open`

- backlog와 이전 회고를 검토합니다.
- 이번 milestone의 scope, acceptance, smoke scenario를 정합니다.
- acceptance와 실제 검증 방법의 매핑을 `docs/plans.md`에 기록합니다.

### `./forge run`

- active milestone을 기준으로 실행합니다.
- resumable run이 있으면 기본 resume하고, 없으면 새 isolated worktree를 엽니다.
- `docs/prompt.md`의 agent profile과 orchestration 설정을 반영합니다.

### `forge-close`

- 완료/차단 상태와 validation 결과를 먼저 검토합니다.
- must-fix, follow-up, durable docs 변경을 정리합니다.
- 마지막 승인 후 land + archive하거나, defer 상태로 남길 수 있습니다.

## Command Reference

### Chat Phases

- Claude Code: `/forge-init`, `/forge-open`, `/forge-close`
- Codex: `$forge-init`, `$forge-open`, `$forge-close`

### Management CLI

- `co-forge install [path]`
  현재 경로 또는 지정한 프로젝트 경로에 Forge 하네스를 설치합니다.
- `co-forge upgrade [path]`
  현재 경로 또는 지정한 프로젝트 경로의 관리 파일을 업그레이드합니다.
- `co-forge uninstall [path]`
  현재 경로 또는 지정한 프로젝트 경로에서 관리 중인 하네스 파일을 제거합니다.

### Runtime Commands

- `./forge run [claude|codex] [--resume|--fresh]`
- `./forge status`
- `./forge doctor`
- `./forge qa`
- `./forge archive <name>`

위 명령은 모두 프로젝트 루트 터미널에서 실행합니다.

## Installed Layout

```text
your-project/
├── forge
├── .claude/skills/
├── .agents/skills/
├── .forge/
│   ├── scripts/
│   ├── templates/
│   ├── references/
│   ├── state/current/      # gitignored
│   ├── runs/               # gitignored
│   └── worktrees/          # gitignored
├── docs/
│   ├── prompt.md
│   ├── plans.md
│   ├── documentation.md
│   ├── prd.md
│   ├── architecture.md
│   ├── backlog.md
│   └── projects/
└── AGENTS.md
```

`.claude`는 chat-native skill entrypoint를 담고, `.agents/skills`는 Codex용 symlink를 둡니다.  
tracked runtime 구현은 `.forge/` 아래에 있고, 실행 중 생성되는 상태는 `.forge/state/current`, `.forge/runs`, `.forge/worktrees`에 기록됩니다.

## Design Principles

- 사람 판단이 필요한 단계는 채팅에서 끝냅니다.
- 오래 돌릴 실행 단계만 shell로 분리합니다.
- validation은 가능한 한 실제 사용자 표면에서 수행합니다.
- milestone은 항상 사람이 다시 엽니다.
- archive는 active run branch를 land한 뒤 기록합니다.
- 병렬화가 필요해도 queue와 status는 lead agent 한 명이 관리합니다.

## Development

이 저장소 자체를 수정할 때는 아래로 기본 검증을 돌립니다.

```bash
npm test
npm pack --json --dry-run
```

## License

MIT
