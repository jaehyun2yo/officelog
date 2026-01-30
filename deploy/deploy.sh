#!/bin/bash
# ComputerOff - 코드 배포 스크립트
# 로컬 Windows PC에서 실행 (Git Bash 또는 WSL)

set -e

# 설정 (사용자가 수정)
VM_IP="${1:-<VM_PUBLIC_IP>}"
VM_USER="${2:-opc}"  # Oracle Linux: opc, Ubuntu: ubuntu
SSH_KEY="${3:-~/.ssh/id_rsa}"

if [ "$VM_IP" = "<VM_PUBLIC_IP>" ]; then
    echo "사용법: ./deploy.sh <VM_IP> [VM_USER] [SSH_KEY]"
    echo "예시: ./deploy.sh 123.45.67.89 opc ~/.ssh/id_rsa"
    exit 1
fi

echo "=== ComputerOff 코드 배포 ==="
echo "대상: ${VM_USER}@${VM_IP}"

# 프로젝트 루트 디렉토리 확인
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "프로젝트 경로: $PROJECT_DIR"

# server 폴더 업로드
echo "server 폴더 업로드 중..."
scp -i "$SSH_KEY" -r "$PROJECT_DIR/server" "${VM_USER}@${VM_IP}:/opt/computeroff/"

# deploy 폴더 업로드
echo "deploy 폴더 업로드 중..."
scp -i "$SSH_KEY" -r "$PROJECT_DIR/deploy" "${VM_USER}@${VM_IP}:/opt/computeroff/"

# VM에서 가상환경 설정 및 의존성 설치
echo "의존성 설치 중..."
ssh -i "$SSH_KEY" "${VM_USER}@${VM_IP}" << 'EOF'
cd /opt/computeroff
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r server/requirements.txt
echo "의존성 설치 완료"
EOF

echo "=== 코드 배포 완료 ==="
echo "다음 단계: VM에 SSH 접속 후 install-service.sh 실행"
