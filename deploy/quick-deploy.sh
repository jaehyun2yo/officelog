#!/bin/bash
# GitHub Push + GCP VM 자동 배포 스크립트
# 사용법: ./quick-deploy.sh "커밋 메시지" [VM_IP] [VM_USER] [SSH_KEY]
#
# 예시:
#   ./quick-deploy.sh "feat: Windows 7 지원 추가" 34.xx.xx.xx ubuntu ~/.ssh/gcp-key
#   ./quick-deploy.sh "fix: 버그 수정"  # 기본값 사용

set -e

COMMIT_MSG="${1:-deploy: $(date +%Y-%m-%d_%H:%M)}"
VM_IP="${2:-34.64.116.152}"
VM_USER="${3:-ubuntu}"
SSH_KEY="${4:-~/.ssh/id_rsa}"

echo "=========================================="
echo "  자동 배포 스크립트"
echo "=========================================="
echo "커밋 메시지: $COMMIT_MSG"
echo "VM: ${VM_USER}@${VM_IP}"
echo "SSH Key: $SSH_KEY"
echo "=========================================="

# SSH 키 파일 존재 확인
if [[ ! -f "$SSH_KEY" ]]; then
    echo "경고: SSH 키 파일을 찾을 수 없습니다: $SSH_KEY"
    echo "SSH 키 경로를 확인하세요."
    exit 1
fi

# 1. 로컬: git add, commit, push
echo ""
echo "[1/2] GitHub에 push 중..."
git add -A
git commit -m "$COMMIT_MSG" || echo "변경 사항 없음 (커밋 스킵)"
git push origin main

echo ""
echo "[2/2] VM에서 git pull + 서버 재시작 중..."

# 2. VM: git pull + 서버 재시작
ssh -i "$SSH_KEY" "${VM_USER}@${VM_IP}" << 'EOF'
echo "VM에 연결됨"
cd /opt/computeroff
echo "git pull 실행 중..."
git pull origin main
echo "서비스 재시작 중..."
sudo systemctl restart computeroff
echo ""
echo "서비스 상태:"
sudo systemctl status computeroff --no-pager
EOF

echo ""
echo "=========================================="
echo "  배포 완료!"
echo "=========================================="
