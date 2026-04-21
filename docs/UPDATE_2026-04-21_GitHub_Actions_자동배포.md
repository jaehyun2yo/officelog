# GitHub Actions 기반 GCP VM 자동 배포 구축

## 목적

`master` 브랜치에 서버 코드 변경을 푸시하면 GCP VM에 자동으로 반영되도록
GitHub Actions 워크플로우를 도입했다. 기존 `deploy/quick-deploy.sh`(수동
실행)를 대체하고, 누가 언제 무엇을 배포했는지 Actions 로그로 추적 가능해진다.

## 배포 트리거

| 트리거 | 동작 |
|---|---|
| `master` 브랜치에 `server/**`, `deploy/**`, `requirements.txt`, 워크플로우 파일 변경 푸시 | 자동 실행 |
| GitHub Actions 탭 → Run workflow | 수동 실행 |
| `agent/**` 단독 변경 | **배포 트리거되지 않음** (서버 재배포 불필요) |

## 배포 단계

워크플로우(`.github/workflows/deploy.yml`)는 다음을 수행한다.

1. GitHub 러너가 레포 체크아웃
2. `webfactory/ssh-agent@v0.9.0`으로 SSH 키 로드
3. `ssh-keyscan`으로 VM 호스트 키를 `known_hosts`에 등록
4. SSH로 VM 접속 후 원격 스크립트 실행
   - `git fetch origin master && git reset --hard origin/master`
   - `source venv/bin/activate && pip install -r server/requirements.txt`
   - `sudo systemctl restart computeroff`
   - `systemctl is-active` / `status` 확인
5. Health check: `http://{VM_IP}:8000/docs`로 HTTP 200 확인

`concurrency` 락으로 동시 실행 시 큐잉된다 (배포 경합 방지).

## 필요 GitHub Secrets

레포 Settings → Secrets and variables → Actions에 등록:

| 이름 | 값 |
|---|---|
| `GCP_VM_IP` | VM 외부 IP |
| `GCP_VM_USER` | `ubuntu` |
| `GCP_SSH_KEY` | SSH 개인키 전체 (`-----BEGIN ... -----END` 포함) |

SSH 키는 배포 전용으로 새로 생성했다 (`ed25519`). 로컬 키 경로는
`~/.ssh/github_actions_deploy`이며, 공개키는 VM의 `ubuntu` 유저
`authorized_keys`에 추가되어 있다.

## 구축 중 발견된 구조적 문제와 수정 사항

첫 배포 시 두 건의 근본 결함이 드러났고, 단순 회피가 아니라 근본 원인을 수정했다.

### 결함 1: `/opt/computeroff` 디렉토리 소유자가 `jaehyun180note`

`setup-vm.sh`는 VM 초기 세팅 실행 유저(`$USER`)로 소유권을 지정하는데,
초기 설치 당시 콘솔 브라우저 SSH(`gcloud` OAuth 유저 = `jaehyun180note`)로
실행됐기 때문에 `jaehyun180note:jaehyun180note` 소유가 되어 있었다.

GitHub Actions는 `ubuntu`로 접속해 `git pull`을 시도하므로 git의
`dubious ownership` 보안 검사에 걸려 첫 배포가 실패했다.

**해결:** `sudo chown -R ubuntu:ubuntu /opt/computeroff` 1회 실행.

### 결함 2: systemd 서비스 유저가 `jaehyun180note`로 설정돼 있음

소스 저장소의 `deploy/computeroff-ubuntu.service`는 `User=ubuntu`이지만,
실제 VM에 설치된 `/etc/systemd/system/computeroff.service`는 수동 편집된
`User=jaehyun180note` 상태였다. 파일 소유자가 `jaehyun180note`일 때는
서비스도 동일 유저라 DB 쓰기가 동작했지만, 결함 1 해결로 소유자를 `ubuntu`로
바꾼 뒤에는 서비스 유저(`jaehyun180note`) ≠ 파일 소유자(`ubuntu`) 불일치로
`sqlite3.OperationalError: attempt to write a readonly database` 발생.

**해결:** 소스 저장소의 서비스 파일로 교체하여 `User=ubuntu`로 통일.

```bash
sudo cp /opt/computeroff/deploy/computeroff-ubuntu.service \
        /etc/systemd/system/computeroff.service
sudo systemctl daemon-reload
sudo systemctl restart computeroff
```

이후로는 **소스 저장소의 서비스 파일이 실제 운영 설정의 단일 진실 공급원**이 된다.

## 운영 체크리스트

- [x] SSH 키 생성 및 VM `authorized_keys` 등록
- [x] GitHub Secrets 3개 등록
- [x] `/opt/computeroff` 소유권 `ubuntu` 통일
- [x] systemd 서비스 유저 `ubuntu`로 통일
- [x] 자동 배포 1회 검증 (git pull + pip + restart + health check 전부 통과)

## 향후 고려 사항

- **VM 외부 IP 고정:** 현재 IP가 재시작 시 변경될 가능성이 있다. 정적 IP
  할당 후 Secret 갱신을 권장.
- **Node.js 20 경고:** `actions/checkout@v4`, `webfactory/ssh-agent@v0.9.0`는
  2026-09-16까지 동작. 그 전에 버전 업데이트 필요.
- **Health check 강화:** 현재 `/docs` 200 응답만 확인. 전용 `/healthz`
  엔드포인트를 두면 더 안정적.
- **보안 강화 (선택):** 22번 포트가 전체 공개라면 GCP IAP 터널링 +
  Workload Identity Federation으로 전환 가능 (IP 노출 없이 인증).
