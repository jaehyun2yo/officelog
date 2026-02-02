# Google Cloud Free Tier 배포 가이드

이 가이드는 Google Cloud Platform의 Always Free 제품을 사용하여 computeroff 서버를 무료로 배포하는 방법을 설명합니다.

## 1. Google Cloud 계정 생성

### 시작하기

- URL: https://cloud.google.com/free
- 회원가입 후 $300 크레딧 (90일) + Always Free 제품 자동 활성화
- 신용카드 필요 (자동 결제 안됨 - Free Tier 범위 내에서만 무료)

### 필수 사항

- 유효한 신용카드 또는 계좌
- 휴대폰 인증
- Google 계정

## 2. Free Tier 제한사항

### Always Free 제품 한계

- **VM 인스턴스**: e2-micro (0.25 vCPU, 1GB RAM) - 월 730시간
- **저장소**: 표준 영구 디스크 30GB
- **네트워크**: 북미 아웃바운드 1GB/월 (초과 시 유료)
- **리전**: us-west1, us-central1, us-east1 **반드시 미국 리전만 선택**

### 무료 리전 확인

```
- us-central1 (아이오와)
- us-west1 (오리건)
- us-east1 (사우스 캐롤라이나)
```

**주의**: 다른 리전 선택 시 즉시 비용 발생

## 3. VM 인스턴스 생성

### 단계별 생성 절차

1. **Google Cloud Console 접속**
   - URL: https://console.cloud.google.com
   - 프로젝트 선택 또는 새로 생성

2. **Compute Engine 네비게이션**
   - 좌측 메뉴 > Compute Engine > VM instances
   - "CREATE INSTANCE" 버튼 클릭

3. **인스턴스 설정**

   ```
   이름 (Name): computeroff-server
   리전 (Region): us-central1
   영역 (Zone): us-central1-a (또는 us-central1-b)
   머신 시리즈: E2
   머신 타입: e2-micro (무료)
   ```

4. **부팅 디스크 설정**
   - 이미지: Ubuntu 22.04 LTS
   - 디스크 타입: 표준 영구 디스크
   - 크기: 30GB (무료 한계)

5. **방화벽 설정**
   - HTTP 트래픽 허용: 체크
   - HTTPS 트래픽 허용: 체크

6. **생성**
   - "Create" 버튼 클릭
   - 2-3분 대기 후 인스턴스 시작

## 4. 방화벽 규칙 추가 (포트 8000)

서버가 포트 8000으로 실행되므로 별도의 방화벽 규칙이 필요합니다.

### 방화벽 규칙 생성

1. **VPC 네트워크 메뉴**
   - 좌측 메뉴 > VPC network > Firewall

2. **새 규칙 생성**
   - "CREATE FIREWALL RULE" 클릭

3. **규칙 설정**

   ```
   이름: allow-computeroff
   방향: Ingress (수신)
   대상: All instances
   출발지 IP 범위: 0.0.0.0/0
   프로토콜 및 포트: tcp:8000
   ```

4. **생성**
   - "Create" 버튼 클릭

### 테스트

```bash
curl http://<EXTERNAL_IP>:8000
```

## 5. SSH 접속

### 방법 1: 브라우저 콘솔 (추천)

- Google Cloud Console에서 VM 인스턴스 클릭
- "SSH" 버튼 클릭
- 자동으로 브라우저 터미널 열림

### 방법 2: gcloud CLI

```bash
# gcloud 설치 (https://cloud.google.com/sdk/docs/install)
gcloud init

# SSH 접속
gcloud compute ssh computeroff-server --zone us-central1-a
```

### 방법 3: 일반 SSH

```bash
# 외부 IP 확인
gcloud compute instances describe computeroff-server \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)' \
  --zone us-central1-a

# SSH 접속
ssh username@<EXTERNAL_IP>
```

## 6. 서버 배포

### 전제 조건

- 로컬 머신에 computeroff 저장소 클론
- VM에 SSH 접속 가능

### 배포 절차

1. **VM 인스턴스에 접속**

   ```bash
   gcloud compute ssh computeroff-server --zone us-central1-a
   ```

2. **저장소 클론 및 초기화**

   ```bash
   git clone <your-repo-url> computeroff
   cd computeroff
   chmod +x setup-vm.sh
   ./setup-vm.sh
   ```

3. **필요한 패키지 설치**

   ```bash
   # Python 및 필수 패키지
   sudo apt-get update
   sudo apt-get install -y python3 python3-pip
   pip3 install -r server/requirements.txt
   ```

4. **데이터베이스 초기화**

   ```bash
   python3 server/database.py
   ```

5. **서버 시작**

   ```bash
   cd server
   python3 app.py
   ```

6. **서비스로 등록 (선택)**
   ```bash
   sudo cp computeroff.service /etc/systemd/system/
   sudo systemctl enable computeroff
   sudo systemctl start computeroff
   sudo systemctl status computeroff
   ```

### 배포 확인

```bash
curl http://localhost:8000/status
```

## 7. Agent 설정

클라이언트에서 서버에 접속하도록 설정합니다.

### config.json 수정

```json
{
  "server_url": "http://<EXTERNAL_IP>:8000",
  "agent_id": "your-agent-id",
  "collection_interval": 3600
}
```

### 외부 IP 확인

```bash
# Google Cloud Console에서 확인
# VM instances > computeroff-server > External IP

# 또는 CLI로 확인
gcloud compute instances describe computeroff-server \
  --zone us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

### 테스트

```bash
curl http://<EXTERNAL_IP>:8000/status
python3 client/agent.py
```

## 8. 비용 주의사항

### 무료 범위 유지 방법

**반드시 확인하세요:**

- ✓ 리전: us-west1, us-central1, us-east1만 선택
- ✓ 머신 타입: e2-micro만 사용
- ✓ 디스크 크기: 30GB 이하 유지
- ✓ 아웃바운드: 월 1GB 이상 초과하지 않기

### 비용 예상

| 항목              | 무료 한계  | 초과 시     |
| ----------------- | ---------- | ----------- |
| e2-micro VM       | 730시간/월 | $0.033/시간 |
| 표준 디스크       | 30GB       | $0.10/GB/월 |
| 아웃바운드 (북미) | 1GB/월     | $0.12/GB    |
| 다른 리전         | 0GB        | $0.12/GB    |

### 비용 모니터링

1. **Google Cloud Console**
   - 상단 메뉴 > Billing > Overview
   - 실시간 비용 확인

2. **비용 알림 설정**
   - Billing > Budgets & alerts
   - 한계금액 설정 (예: $5)
   - 초과 시 이메일 알림

## 9. 유용한 gcloud 명령어

### VM 관리

```bash
# VM 시작
gcloud compute instances start computeroff-server --zone us-central1-a

# VM 중지 (비용 절감)
gcloud compute instances stop computeroff-server --zone us-central1-a

# VM 상태 확인
gcloud compute instances describe computeroff-server --zone us-central1-a

# VM 삭제
gcloud compute instances delete computeroff-server --zone us-central1-a
```

### SSH 및 네트워크

```bash
# SSH 접속
gcloud compute ssh computeroff-server --zone us-central1-a

# 외부 IP 확인
gcloud compute instances describe computeroff-server \
  --zone us-central1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'

# 방화벽 규칙 목록
gcloud compute firewall-rules list

# 방화벽 규칙 삭제
gcloud compute firewall-rules delete allow-computeroff
```

### 로그 확인

```bash
# 시스템 로그
gcloud compute instances get-serial-port-output computeroff-server --zone us-central1-a

# VM 내부에서 애플리케이션 로그
tail -f /var/log/computeroff.log
```

## 10. 문제 해결

### 접속 안 될 때

**증상**: curl http://<IP>:8000 연결 타임아웃

**해결방법**:

1. 방화벽 규칙 확인

   ```bash
   gcloud compute firewall-rules list --filter="name:allow-computeroff"
   ```

2. 인스턴스 상태 확인

   ```bash
   gcloud compute instances describe computeroff-server --zone us-central1-a
   ```

3. 포트 8000 리스닝 확인 (VM 내부)
   ```bash
   sudo netstat -tuln | grep 8000
   ```

### 느린 성능

**원인**: 미국 리전에서 한국으로 통신 (지연 정상)

**개선방법**:

- e2-micro의 한계 (CPU 자주 제한됨)
- 대역폭 최적화 (압축, 캐싱 등)
- 더 나은 성능 필요 시 유료 VM으로 업그레이드

### 데이터베이스 오류

**증상**: database.py 실행 시 오류

**해결방법**:

```bash
# 데이터베이스 재초기화
rm server/data/computeroff.db
python3 server/database.py

# 권한 확인
ls -la server/data/
sudo chown $USER:$USER server/data/
```

### 서비스 시작 안 됨

```bash
# 서비스 상태 확인
sudo systemctl status computeroff

# 로그 확인
sudo journalctl -u computeroff -n 50

# 수동 시작 테스트
cd /path/to/computeroff/server
python3 app.py
```

## 11. 보안 주의사항

### 필수 보안 설정

1. **SSH 키 기반 인증**
   - 비밀번호 인증 비활성화
   - 개인 SSH 키만 사용

2. **방화벽 제한**

   ```bash
   # 특정 IP에서만 접근 허용
   gcloud compute firewall-rules update allow-computeroff \
     --source-ranges 123.45.67.0/24
   ```

3. **SSL/TLS 설정 (선택)**
   - Let's Encrypt 인증서 설치
   - HTTPS 포트 443 추가

4. **정기적인 업데이트**
   ```bash
   sudo apt-get update
   sudo apt-get upgrade
   ```

## 12. 정리 및 비용 절감

### 사용하지 않을 때

```bash
# VM 중지 (비용 거의 0)
gcloud compute instances stop computeroff-server --zone us-central1-a

# VM 시작
gcloud compute instances start computeroff-server --zone us-central1-a
```

### 완전히 제거

```bash
# VM 삭제
gcloud compute instances delete computeroff-server --zone us-central1-a

# 디스크 삭제
gcloud compute disks delete computeroff-server --zone us-central1-a

# 방화벽 규칙 삭제
gcloud compute firewall-rules delete allow-computeroff

# 외부 IP 해제 (할당된 경우)
gcloud compute addresses delete computeroff-ip
```

## 참고 자료

- [Google Cloud Always Free](https://cloud.google.com/free/docs/gcp-free-tier)
- [Compute Engine 가격](https://cloud.google.com/compute/pricing)
- [gcloud 명령어 참조](https://cloud.google.com/sdk/gcloud/reference)
- [Compute Engine 문서](https://cloud.google.com/compute/docs)

- 32비트 PC: computeroff-agent-x86.exe + config.json 복사
  - 64비트 PC: computeroff-agent-x64.exe + config.json 복사
  - 관리자 권한으로 실행 후 설치
