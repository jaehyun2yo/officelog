#!/bin/bash
# ComputerOff - 배포 검증 스크립트
# VM에서 실행

echo "=== ComputerOff 배포 검증 ==="
echo ""

# 1. 서비스 상태 확인
echo "1. 서비스 상태:"
sudo systemctl status computeroff --no-pager || true
echo ""

# 2. 프로세스 확인
echo "2. 프로세스 확인:"
ps aux | grep uvicorn | grep -v grep || echo "uvicorn 프로세스 없음"
echo ""

# 3. 포트 확인
echo "3. 포트 8000 리스닝 확인:"
ss -tlnp | grep 8000 || echo "포트 8000 미사용"
echo ""

# 4. API 헬스체크
echo "4. API 헬스체크:"
curl -s http://localhost:8000/api/computers && echo "" || echo "API 응답 없음"
echo ""

# 5. 외부 IP 확인
echo "5. 외부 접근 정보:"
EXTERNAL_IP=$(curl -s ifconfig.me 2>/dev/null || echo "확인 불가")
echo "VM 공인 IP: ${EXTERNAL_IP}"
echo "대시보드 URL: http://${EXTERNAL_IP}:8000"
echo ""

echo "=== 검증 완료 ==="
echo ""
echo "문제 해결:"
echo "  - 서비스 로그: sudo journalctl -u computeroff -f"
echo "  - 서비스 재시작: sudo systemctl restart computeroff"
echo "  - 방화벽 확인: sudo firewall-cmd --list-ports (Oracle) / sudo ufw status (Ubuntu)"
