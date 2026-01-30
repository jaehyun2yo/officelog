# Oracle Cloud Free Tier 배포 가이드

ComputerOff 서버를 Oracle Cloud Free Tier VM에 배포하여 24/7 무료로 운영하는 완벽한 가이드입니다.

## 1. Oracle Cloud 계정 생성

### 1.1 가입 절차

1. **Oracle Cloud Free Tier 가입**
   - URL: https://www.oracle.com/cloud/free/
   - "무료 계정 시작" 또는 "Start for free" 버튼 클릭

2. **필요한 정보**
   - 유효한 이메일 주소
   - 신용카드 정보 (결제되지 않음, 신원 확인용)
   - 전화번호 (선택 사항)

3. **계정 활성화**
   - 이메일 인증 완료
   - 신용카드 정보 입력
   - 계정 생성 완료

### 1.2 Free Tier 제한사항

다음 리소스는 **무료**로 이용 가능합니다:

| 리소스 | 할당량 | 설명 |
|--------|--------|------|
| **Compute** | 2개 OCPU | VM.Standard.E2.1.Micro (1 OCPU, 1GB RAM) 또는 Ampere A1 Flex |
| **메모리** | 12GB | 총 메모리 할당량 |
| **스토리지** | 200GB | Boot Volume 합계 |
| **대역폭** | 월 10TB | 아웃바운드 데이터 전송 |
| **데이터베이스** | 2개 | MySQL, PostgreSQL 등 |

주의: 프리티어 범위를 초과하면 비용이 발생할 수 있습니다.

---

## 2. VM 인스턴스 생성

### 2.1 Oracle Cloud Console 접속

1. Oracle Cloud Console에 로그인: https://www.oracle.com/cloud/
2. 대시보드 하단 "Always Free Resources" 확인

### 2.2 Compute Instance 생성

1. **콘솔 메뉴 이동**
   ```
   메뉴 → Compute → Instances
   ```

2. **"Create Instance" 버튼 클릭**

3. **기본 설정**

   | 설정 항목 | 값 |
   |---------|-----|
   | Name | `computeroff-server` |
   | Compartment | root (기본값) |
   | Image | Oracle Linux 8 또는 Ubuntu 22.04 LTS |
   | Shape | VM.Standard.E2.1.Micro (Always Free) |
   | OCPU | 1 |
   | Memory | 1GB |

4. **디스크 설정**
   - Boot Volume Size: **50GB** (최대 200GB까지 무료)
   - Volume Performance: Balanced (기본값)

### 2.3 네트워크 설정

1. **Virtual Cloud Network (VCN)**
   - 신규 VCN 생성 또는 기존 VCN 선택
   - 서브넷: 공개 서브넷 선택 (Public Subnet)

2. **공인 IP (Public IP)**
   - "Assign a public IPv4 address" 체크

3. **SSH 키 설정** (중요!)

   **옵션 A: Oracle Cloud가 생성한 키 다운로드**
   ```
   "Generate a key pair for me" 선택
   → "Download Private Key" 클릭하여 저장
   → .pem 파일을 안전한 위치에 보관
   ```

   **옵션 B: 로컬에서 생성한 공개 키 사용**

   먼저 로컬 PC에서 SSH 키 생성 (이미 있다면 건너뛰기):
   ```bash
   ssh-keygen -t rsa -b 4096 -f computeroff-oracle -C "computeroff"
   ```

   생성된 파일:
   - `computeroff-oracle` (비공개 키, 안전히 보관)
   - `computeroff-oracle.pub` (공개 키, Oracle Cloud에 등록)

   Oracle Cloud에서 "Paste public key" 선택 → `computeroff-oracle.pub` 내용 붙여넣기

4. **Instance 생성**
   - "Create Instance" 버튼 클릭
   - 인스턴스 생성 완료 대기 (약 2-3분)

### 2.4 생성 후 확인

1. **인스턴스 정보 확인**
   ```
   Running 상태 확인
   공인 IP 주소 기록 (예: 152.70.xx.xx)
   ```

2. **인스턴스 상세 정보에서 확인할 항목**
   - Instance Details → Public IPv4 Address: `<VM_PUBLIC_IP>`
   - Primary VNIC → MAC Address 확인

---

## 3. SSH 접속

### 3.1 SSH 접속 방법

**Oracle Linux 사용자:**
```bash
ssh -i computeroff-oracle opc@<VM_PUBLIC_IP>
```

**Ubuntu 사용자:**
```bash
ssh -i computeroff-oracle ubuntu@<VM_PUBLIC_IP>
```

### 3.2 Windows에서 SSH 접속

**방법 1: PowerShell 또는 Windows Terminal 사용**

```powershell
# SSH 키 권한 설정 (필수)
icacls.exe "computeroff-oracle" /inheritance:r /grant:r "%username%:(R)"

# SSH 접속
ssh -i computeroff-oracle opc@<VM_PUBLIC_IP>
```

**방법 2: PuTTY 사용**

1. PuTTY 다운로드: https://www.putty.org/
2. PuTTYgen으로 .pem 파일을 PuTTY 형식으로 변환
3. PuTTY Connection → SSH → Auth → Private key file 설정
4. Host Name: `opc@<VM_PUBLIC_IP>`

### 3.3 접속 후 확인

```bash
# OS 확인
cat /etc/os-release

# 인터넷 연결 확인
curl -I https://www.google.com

# 시스템 정보
uname -a
df -h
free -h
```

---

## 4. 서버 배포

### 4.1 VM 초기 설정 (Optional but Recommended)

프로젝트의 배포 스크립트를 사용하거나 수동으로 설정할 수 있습니다.

**스크립트 자동 설정 (권장):**

로컬 PC에서 VM으로 배포 스크립트 업로드:
```bash
scp -i computeroff-oracle -r deploy/ opc@<VM_PUBLIC_IP>:/home/opc/
scp -i computeroff-oracle -r server/ opc@<VM_PUBLIC_IP>:/home/opc/
```

VM에서 초기 설정:
```bash
cd /home/opc
chmod +x deploy/setup-vm.sh
./deploy/setup-vm.sh
```

**수동 설정 (Oracle Linux):**

```bash
# 패키지 업데이트
sudo dnf update -y

# Python 3.9 설치
sudo dnf install -y python39 python39-pip

# 디렉토리 생성
sudo mkdir -p /opt/computeroff
sudo chown -R $USER:$USER /opt/computeroff

# Python 가상 환경 생성
cd /opt/computeroff
python3 -m venv venv
```

**수동 설정 (Ubuntu):**

```bash
# 패키지 업데이트
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

# 디렉토리 생성
sudo mkdir -p /opt/computeroff
sudo chown -R $USER:$USER /opt/computeroff

# Python 가상 환경 생성
cd /opt/computeroff
python3 -m venv venv
```

### 4.2 코드 배포

**로컬 PC (Windows)에서 VM으로 코드 업로드:**

Windows PowerShell 또는 Git Bash에서:

```bash
# VM의 공인 IP 설정
VM_IP="<VM_PUBLIC_IP>"
VM_USER="opc"  # Oracle Linux는 opc, Ubuntu는 ubuntu

# server 폴더 업로드
scp -i computeroff-oracle -r server/ ${VM_USER}@${VM_IP}:/opt/computeroff/

# deploy 폴더 업로드
scp -i computeroff-oracle -r deploy/ ${VM_USER}@${VM_IP}:/opt/computeroff/
```

### 4.3 서버 패키지 설치

VM에 SSH 접속 후:

```bash
cd /opt/computeroff

# 가상 환경 활성화
source venv/bin/activate

# 패키지 설치
pip install -r server/requirements.txt

# 설치 확인
python -c "import fastapi; print(fastapi.__version__)"
```

### 4.4 서버 수동 실행 테스트

```bash
cd /opt/computeroff/server
source ../venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

출력 예시:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

정상 실행 확인 후 `Ctrl+C`로 종료.

---

## 5. systemd 서비스 등록

### 5.1 서비스 파일 복사

**Oracle Linux 사용자:**

```bash
sudo cp /opt/computeroff/deploy/computeroff-oracle.service /etc/systemd/system/computeroff.service
```

**Ubuntu 사용자:**

```bash
sudo cp /opt/computeroff/deploy/computeroff-ubuntu.service /etc/systemd/system/computeroff.service
```

### 5.2 서비스 활성화 및 시작

```bash
# systemd 데몬 리로드
sudo systemctl daemon-reload

# 서비스 자동 시작 활성화
sudo systemctl enable computeroff

# 서비스 시작
sudo systemctl start computeroff

# 상태 확인
sudo systemctl status computeroff
```

정상 상태 출력:
```
● computeroff.service - ComputerOff Server
   Loaded: loaded (/etc/systemd/system/computeroff.service; enabled)
   Active: active (running)
```

### 5.3 서비스 관리 명령어

```bash
# 서비스 시작
sudo systemctl start computeroff

# 서비스 중지
sudo systemctl stop computeroff

# 서비스 다시 시작
sudo systemctl restart computeroff

# 서비스 상태 조회
sudo systemctl status computeroff

# 로그 확인
sudo journalctl -u computeroff -f
```

---

## 6. 방화벽 설정

### 6.1 Oracle Cloud VCN Security Group 설정

이 부분은 **필수**입니다. 설정하지 않으면 외부에서 서버에 접근할 수 없습니다.

1. **Oracle Cloud Console 접속**
   ```
   메뉴 → Networking → Virtual Cloud Networks
   ```

2. **VCN 선택**
   - 인스턴스 생성 시 사용한 VCN 선택 (기본값: vcn-xxxxx)

3. **Security List 열기**
   ```
   VCN 상세 화면 → Security Lists → Default Security List for vcn-xxxxx
   ```

4. **Ingress Rule 추가**

   "Add Ingress Rules" 클릭 후:

   | 항목 | 값 |
   |-----|-----|
   | Stateless | 체크 해제 (Stateful 사용) |
   | Source Type | CIDR |
   | Source CIDR | `0.0.0.0/0` (모든 IP 허용, 테스트용) |
   | IP Protocol | TCP |
   | Destination Port Range | `8000` |
   | Description | `ComputerOff Server` |

   **보안 권장사항**: 운영 환경에서는 Source CIDR을 특정 IP 대역으로 제한하세요.
   ```
   예: 203.0.113.0/24 (특정 네트워크만)
   ```

5. **규칙 추가**
   - "Add Another Rule" 선택하여 추가
   - "Add Ingress Rules" 버튼으로 최종 저장

### 6.2 VM 호스트 방화벽 설정

**Oracle Linux (firewalld):**

```bash
# 포트 8000/TCP 영구 허용
sudo firewall-cmd --permanent --add-port=8000/tcp

# 방화벽 재로드
sudo firewall-cmd --reload

# 설정 확인
sudo firewall-cmd --list-ports
```

**Ubuntu (ufw):**

```bash
# UFW 활성화 (아직 활성화하지 않았다면)
sudo ufw enable

# 포트 8000/TCP 허용
sudo ufw allow 8000/tcp

# 설정 확인
sudo ufw status
```

### 6.3 방화벽 설정 자동화 스크립트

프로젝트의 배포 스크립트 사용:

```bash
cd /opt/computeroff
chmod +x deploy/setup-firewall.sh
./deploy/setup-firewall.sh
```

---

## 7. 서버 접근 테스트

### 7.1 로컬 확인 (VM에서)

```bash
# API 헬스 체크
curl http://localhost:8000/api/computers

# 대시보드 확인
curl -I http://localhost:8000
```

응답 예시:
```
HTTP/1.1 200 OK
Content-Type: application/json
```

### 7.2 외부 접근 확인

**로컬 PC (Windows)의 브라우저에서:**

1. 브라우저 열기
2. 주소 입력: `http://<VM_PUBLIC_IP>:8000`
3. ComputerOff 대시보드 표시 확인

응답이 없다면:
- Oracle Cloud VCN Security Group 규칙 확인 (위 5.1 참고)
- VM 방화벽 설정 확인 (위 6.2 참고)
- `sudo systemctl status computeroff` 서비스 상태 확인

### 7.3 배포 검증 자동화

프로젝트의 배포 검증 스크립트 사용:

```bash
cd /opt/computeroff
chmod +x deploy/verify.sh
./deploy/verify.sh
```

---

## 8. Windows Agent 설정 업데이트

ComputerOff Agent가 설치된 Windows PC에서 서버 URL을 변경합니다.

### 8.1 config.json 위치 확인

다음 중 하나의 위치를 확인하세요:

| 위치 | 설명 |
|-----|------|
| `C:\Program Files\ComputerOff\config.json` | 정식 설치 시 |
| `{프로젝트폴더}\agent\config.json` | 개발 환경 |
| `{프로젝트폴더}\dist\config.json` | PyInstaller 빌드 후 |

### 8.2 config.json 수정

1. **메모장을 관리자 권한으로 실행**
   ```
   Windows 검색 → "메모장" 마우스 우클릭 → "관리자 권한으로 실행"
   ```

2. **파일 열기**
   ```
   파일 → 열기 → 위 8.1의 config.json 경로 선택
   ```

3. **server_url 수정**

   수정 전:
   ```json
   {
     "server_url": "http://localhost:8000"
   }
   ```

   수정 후 (VM_PUBLIC_IP를 실제 IP로 변경):
   ```json
   {
     "server_url": "http://<VM_PUBLIC_IP>:8000"
   }
   ```

   예시:
   ```json
   {
     "server_url": "http://152.70.123.45:8000"
   }
   ```

4. **저장 및 종료**
   ```
   Ctrl+S → 메모장 종료
   ```

### 8.3 변경사항 적용

**방법 A: 컴퓨터 재부팅 (권장)**
```
시작 → 전원 → 다시 시작
```

**방법 B: Agent 서비스 재시작**
```
Windows + R → services.msc 입력
→ ComputerOff 관련 서비스 찾기
→ 마우스 우클릭 → "다시 시작"
```

---

## 9. 동작 확인

### 9.1 대시보드 확인

1. Windows PC에서 브라우저 열기
2. 주소 입력: `http://<VM_PUBLIC_IP>:8000`
3. ComputerOff 대시보드 확인

### 9.2 이벤트 전송 테스트

1. Windows PC 재부팅
2. 부팅 완료 후 대시보드에서 "Boot" 이벤트 확인

또는 수동 테스트:
```bash
# PowerShell에서 (VM_PUBLIC_IP 변경)
curl -X POST http://<VM_PUBLIC_IP>:8000/api/events `
  -Headers @{"Content-Type"="application/json"} `
  -Body '{"computer_name":"TestPC","event_type":"boot"}'
```

### 9.3 문제 해결

**대시보드가 보이지 않음:**
- VM이 실행 중인지 확인: `sudo systemctl status computeroff`
- VCN Security Group 규칙 재확인 (섹션 6.1)
- VM 방화벽 설정 재확인 (섹션 6.2)

**이벤트가 전송되지 않음:**
- Agent config.json 서버 URL 재확인 (섹션 8.2)
- Agent 로그 확인: `agent.log` 파일 (Agent 실행 폴더)
- Windows 재부팅 후 다시 시도

**서버 로그 확인:**
```bash
ssh -i computeroff-oracle opc@<VM_PUBLIC_IP>
sudo journalctl -u computeroff -f
```

---

## 10. 비용 확인 및 주의사항

### 10.1 Free Tier 무료 자원

이 가이드의 구성은 다음 범위 내에서 무료입니다:

- **Compute**: VM.Standard.E2.1.Micro (1 OCPU, 1GB RAM)
- **스토리지**: 50GB Boot Volume
- **네트워크**: 공인 IP 1개 (항상 할당된 상태)
- **아웃바운드**: 월 10TB까지 무료

### 10.2 추가 비용이 발생할 수 있는 항목

| 항목 | 조건 |
|-----|------|
| **추가 OCPU** | VM 사양을 Micro 이상으로 확대 시 |
| **추가 메모리** | 1GB 이상 할당 시 |
| **스토리지** | 200GB 이상 사용 시 |
| **아웃바운드 대역폭** | 월 10TB 초과 시 |
| **공인 IP** | 사용하지 않는 IP가 있을 시 |

### 10.3 비용 확인 방법

```
Oracle Cloud Console → Billing & Cost Management → Cost Analysis
```

월별 예상 비용을 확인할 수 있습니다.

---

## 11. 추가 구성 (선택 사항)

### 11.1 도메인 연결 (HTTPS 포함)

프로덕션 환경에서는 HTTPS를 권장합니다:

1. **도메인 구매** (예: Route 53, Namecheap 등)
2. **Let's Encrypt SSL 인증서 설정**
   ```bash
   # Certbot 설치
   sudo dnf install -y certbot python3-certbot-nginx  # Oracle Linux
   # 또는
   sudo apt install -y certbot python3-certbot-nginx   # Ubuntu

   # 인증서 발급
   sudo certbot certonly --standalone -d yourdomain.com
   ```
3. **Nginx 리버스 프록시 구성** (선택)

### 11.2 모니터링 설정

서버 상태를 모니터링하려면:

```bash
# htop 설치 (시스템 모니터링)
sudo dnf install -y htop  # Oracle Linux
sudo apt install -y htop  # Ubuntu

# 실시간 로그 확인
sudo journalctl -u computeroff -f
```

### 11.3 자동 백업

SQLite 데이터베이스를 자동으로 백업하려면:

```bash
# 백업 디렉토리 생성
mkdir -p /opt/computeroff/backups

# 백업 스크립트 생성
cat > /opt/computeroff/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/computeroff/backups"
DB_FILE="/opt/computeroff/server/computeroff.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp $DB_FILE $BACKUP_DIR/computeroff_$TIMESTAMP.db
# 30일 이상 된 백업 삭제
find $BACKUP_DIR -name "computeroff_*.db" -mtime +30 -delete
EOF

chmod +x /opt/computeroff/backup.sh

# Cron 작업 등록 (매일 자정에 백업)
crontab -e
# 아래 라인 추가:
# 0 0 * * * /opt/computeroff/backup.sh
```

---

## 12. 도움말 및 참고 문서

### 공식 문서
- **Oracle Cloud 공식 문서**: https://docs.oracle.com/en-us/iaas/
- **FastAPI 공식 문서**: https://fastapi.tiangolo.com/
- **systemd 매뉴얼**: `man systemctl`

### 자주 묻는 질문 (FAQ)

**Q: Free Tier VM의 성능은 충분한가?**
A: ComputerOff는 가볍고 효율적인 서버이므로 Micro 인스턴스(1 OCPU, 1GB RAM)로 충분합니다.

**Q: 언제든지 VM을 중지할 수 있나?**
A: 예. Console에서 Instance를 중지해도 Always Free 할당량에는 영향을 주지 않습니다.

**Q: 데이터는 안전한가?**
A: SQLite DB는 `/opt/computeroff/server/computeroff.db`에 저장됩니다. 정기적으로 백업하기를 권장합니다 (섹션 11.3).

**Q: 데이터 전송 비용이 얼마나 드는가?**
A: 월 10TB까지 무료입니다. 초과 시 GB당 약 $0.01입니다.

---

## 부록 A: 배포 스크립트 실행 순서

프로젝트의 배포 스크립트를 사용하는 경우 다음 순서로 실행합니다:

```bash
# 1단계: 초기 설정 (VM에서)
cd /opt/computeroff
chmod +x deploy/setup-vm.sh
./deploy/setup-vm.sh

# 2단계: 패키지 설치 (VM에서)
cd /opt/computeroff
source venv/bin/activate
pip install -r server/requirements.txt

# 3단계: 서비스 등록 및 시작 (VM에서)
chmod +x deploy/install-service.sh
./deploy/install-service.sh

# 4단계: 방화벽 설정 (VM에서)
chmod +x deploy/setup-firewall.sh
./deploy/setup-firewall.sh

# 5단계: 검증 (VM에서)
chmod +x deploy/verify.sh
./deploy/verify.sh

# 6단계: Agent 설정 업데이트 (Windows PC에서)
# 섹션 8 참고
```

---

## 부록 B: 자주 사용하는 명령어

```bash
# 서비스 상태 확인
sudo systemctl status computeroff

# 서비스 로그 확인 (최근 50줄)
sudo journalctl -u computeroff -n 50

# 실시간 로그 확인
sudo journalctl -u computeroff -f

# 서비스 재시작
sudo systemctl restart computeroff

# 방화벽 포트 확인
# Oracle Linux
sudo firewall-cmd --list-ports

# Ubuntu
sudo ufw status

# 디스크 용량 확인
df -h

# 메모리 사용량 확인
free -h

# 네트워크 통계
netstat -tlnp | grep 8000

# 프로세스 확인
ps aux | grep uvicorn
```

---

## 부록 C: VM 삭제 (비용 절감)

더 이상 필요 없으면 VM을 삭제합니다:

1. **Oracle Cloud Console 접속**
   ```
   메뉴 → Compute → Instances
   ```

2. **인스턴스 선택**
   ```
   computeroff-server → "More Actions" → "Terminate"
   ```

3. **확인**
   ```
   Boot Volume도 함께 삭제 확인 → "Terminate Instance"
   ```

삭제 후 더 이상 비용이 발생하지 않습니다.

---

## 지원 및 피드백

문제가 발생하거나 개선 사항이 있으면 프로젝트 이슈 또는 토론 게시판에 남겨주세요.

행운을 기원합니다!
