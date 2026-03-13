# Releasing co-forge

이 문서는 `co-forge` maintainer용 release 가이드입니다.  
핵심 목표는 `git main`의 하네스 코드와 npm에 배포된 패키지 상태를 항상 추적 가능하게 유지하는 것입니다.

## Release Model

현재 `co-forge upgrade`는 원격 저장소에서 최신 하네스를 직접 받지 않습니다.  
대신, 현재 설치된 `co-forge` npm 패키지 안에 들어 있는 하네스 파일을 프로젝트로 복사합니다.

즉 아래 두 상태는 항상 함께 관리해야 합니다.

- git 저장소의 소스
- npm에 배포된 `co-forge` 패키지

하네스 구조나 CLI 동작이 바뀌었는데 npm을 다시 배포하지 않으면, 사용자가 `co-forge upgrade`로 받는 내용은 오래된 상태로 남습니다.

## When To Release

아래 중 하나라도 바뀌면 새 npm 버전을 내는 쪽이 맞습니다.

- `bin/`
- `lib/`
- `forge`
- `.forge/`
- `.claude/`
- `package.json`
- npm 패키지에 포함되는 `README.md`

보통 아래만 바뀐 경우에는 npm release가 필요 없습니다.

- 테스트만 변경
- 패키지에 포함되지 않는 내부 문서만 변경

## Release Rules

- release는 clean working tree에서만 진행합니다.
- npm 버전은 git 커밋과 대응되어야 합니다.
- release 후에는 git tag를 남깁니다.
- publish 전에 반드시 테스트와 `npm pack --dry-run`을 통과시킵니다.
- npm 2FA가 켜져 있으면 최종 `npm publish`는 사람이 OTP를 넣어 마무리합니다.

## Agent-Assisted Workflow

Codex나 Claude Code에는 release 준비 작업을 맡기고, 최종 publish는 사람이 승인하는 방식이 가장 안전합니다.

에이전트에게 맡겨도 좋은 작업:

- 변경 범위 점검
- `package.json` 버전 업데이트
- README / release 문서 정리
- 테스트 실행
- `npm pack --dry-run` 확인
- release commit 준비
- tag 명령 준비

사람이 직접 확인하거나 승인해야 하는 작업:

- 최종 버전 결정
- `npm publish`
- OTP 입력
- 실제 공개 배포 확인

## Suggested Delegation Prompts

### Codex

```text
$codex, prepare the next co-forge npm release in this repo.

Requirements:
- inspect packaged files and release impact
- update package.json version if needed
- run tests
- run npm pack --dry-run
- summarize what changed in the package
- prepare a release commit, but do not publish to npm
- tell me the exact npm publish and git tag commands to run
```

### Claude Code

```text
/forge-open is not needed here.

Please prepare a co-forge npm release in this repository.

Do:
- inspect what changed in packaged files
- decide whether a new npm release is required
- bump package.json version if needed
- run tests and npm pack --dry-run
- prepare the release commit
- give me the exact publish and tag commands

Do not:
- publish to npm
- ask me to do manual intermediate steps unless blocked
```

## Pre-Release Checklist

프로젝트 루트 터미널에서 실행합니다.

```bash
git status --short
npm test
npm pack --dry-run --cache /tmp/co-forge-npm-cache
```

확인할 것:

- working tree가 깨끗한지
- 테스트가 통과하는지
- tarball에 기대한 파일만 포함되는지
- `package.json` 버전이 올바른지

## Release Steps

### 1. Prepare The Release Commit

필요한 변경을 마친 뒤 커밋합니다.

예시:

```bash
git add -A
git commit -m "Release co-forge v0.1.2"
git push origin main
```

### 2. Publish To npm

2FA가 없는 경우:

```bash
npm publish --cache /tmp/co-forge-npm-cache
```

2FA가 있는 경우:

```bash
npm publish --cache /tmp/co-forge-npm-cache --otp=<CODE>
```

### 3. Tag The Release

git tag는 npm 버전과 맞춥니다.

```bash
git tag v0.1.2
git push origin v0.1.2
```

## Post-Release Verification

배포 후 아래를 확인합니다.

```bash
npm view co-forge version
npx co-forge@latest --help
```

확인할 것:

- npm 최신 버전이 기대한 값인지
- CLI가 정상 실행되는지
- README / repository / bugs 링크가 npm 페이지에 노출되는지

## Common Mistakes

- git 커밋은 했지만 npm publish를 하지 않음
- npm publish는 했지만 tag를 남기지 않음
- 테스트는 통과했지만 `npm pack --dry-run`을 보지 않음
- `package.json` 버전을 올리지 않고 같은 버전으로 publish를 시도함
- OTP가 필요한데 agent에게 publish까지 맡기려다 막힘

## Versioning Guidance

- patch: 메타데이터 수정, 문서 보강, 작은 CLI/하네스 수정
- minor: 하위 호환을 유지한 새 기능 추가
- major: 설치 방식, 명령 구조, 하네스 계약에 breaking change가 있을 때

버전 판단이 애매하면 conservative하게 minor 또는 patch를 선택하고, breaking change만 major로 올립니다.
