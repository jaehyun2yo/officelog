#!/bin/bash
# ComputerOff - 방화벽 설정 스크립트
# VM에서 실행

set -e

echo "=== ComputerOff 방화벽 설정 ==="

# OS 자동 감지
if [ -f /etc/oracle-release ]; then
    echo "Oracle Linux 감지 - firewalld 사용"

    # firewalld로 포트 개방
    sudo firewall-cmd --permanent --add-port=8000/tcp
    sudo firewall-cmd --reload

    echo ""
    echo "개방된 포트 목록:"
    sudo firewall-cmd --list-ports

else
    echo "Ubuntu 감지 - ufw 사용"

    # ufw로 포트 개방
    sudo ufw allow 8000/tcp

    echo ""
    echo "UFW 상태:"
    sudo ufw status
fi

echo ""
echo "=== 방화벽 설정 완료 ==="
echo ""
echo "중요: Oracle Cloud 콘솔에서도 보안 그룹 설정이 필요합니다!"
echo "  1. Networking > Virtual Cloud Networks > VCN 선택"
echo "  2. Security Lists > Default Security List"
echo "  3. Add Ingress Rules:"
echo "     - Source CIDR: 0.0.0.0/0"
echo "     - IP Protocol: TCP"
echo "     - Destination Port: 8000"
echo ""
echo "다음 단계: verify.sh로 배포 검증"
