#!/bin/bash
# ComputerOff - VM 초기 설정 스크립트
# Oracle Linux 8 / Ubuntu 22.04 자동 감지

set -e

echo "=== ComputerOff VM 초기 설정 ==="

# OS 자동 감지
if [ -f /etc/oracle-release ]; then
    OS_TYPE="oracle"
    echo "Oracle Linux 감지됨"

    # 패키지 업데이트 및 Python 설치
    sudo dnf update -y
    sudo dnf install -y python39 python39-pip git

elif [ -f /etc/lsb-release ]; then
    OS_TYPE="ubuntu"
    echo "Ubuntu 감지됨"

    # 패키지 업데이트 및 Python 설치
    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv git

else
    echo "지원하지 않는 OS입니다"
    exit 1
fi

# 프로젝트 디렉토리 생성
echo "프로젝트 디렉토리 설정 중..."
sudo mkdir -p /opt/computeroff
sudo chown -R $USER:$USER /opt/computeroff

echo "=== VM 초기 설정 완료 ==="
echo "다음 단계: deploy.sh로 코드를 배포하세요"
