#!/bin/bash
# ComputerOff - 서비스 등록 스크립트
# VM에서 실행

set -e

echo "=== ComputerOff 서비스 등록 ==="

# OS 자동 감지
if [ -f /etc/oracle-release ]; then
    SERVICE_FILE="computeroff-oracle.service"
    echo "Oracle Linux 감지 - opc 사용자 서비스 사용"
else
    SERVICE_FILE="computeroff-ubuntu.service"
    echo "Ubuntu 감지 - ubuntu 사용자 서비스 사용"
fi

# 서비스 파일 복사
echo "서비스 파일 설치 중..."
sudo cp /opt/computeroff/deploy/${SERVICE_FILE} /etc/systemd/system/computeroff.service

# systemd 재로드 및 서비스 활성화
echo "서비스 활성화 중..."
sudo systemctl daemon-reload
sudo systemctl enable computeroff
sudo systemctl start computeroff

# 상태 확인
echo ""
echo "=== 서비스 상태 ==="
sudo systemctl status computeroff --no-pager

echo ""
echo "=== 서비스 등록 완료 ==="
echo "다음 단계: setup-firewall.sh로 방화벽 설정"
