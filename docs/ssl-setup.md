# SSL/TLS 설정 가이드

ComputerOff 서버에 HTTPS를 적용하는 방법입니다.

## 목차

1. [도메인이 있는 경우 (Let's Encrypt)](#1-도메인이-있는-경우-lets-encrypt)
2. [IP만 사용하는 경우 (Self-signed)](#2-ip만-사용하는-경우-self-signed)
3. [Agent 설정 변경](#3-agent-설정-변경)

---

## 1. 도메인이 있는 경우 (Let's Encrypt)

### 1.1 Nginx 및 Certbot 설치

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx

# CentOS/RHEL
sudo yum install epel-release
sudo yum install nginx certbot python3-certbot-nginx
```

### 1.2 Let's Encrypt 인증서 발급

```bash
# 도메인으로 인증서 발급 (your-domain.com을 실제 도메인으로 변경)
sudo certbot --nginx -d your-domain.com

# 자동 갱신 테스트
sudo certbot renew --dry-run
```

### 1.3 Nginx 설정 적용

```bash
# 설정 파일 복사
sudo cp server/nginx.conf /etc/nginx/sites-available/computeroff

# 도메인 수정 (your-domain.com을 실제 도메인으로 변경)
sudo nano /etc/nginx/sites-available/computeroff

# 심볼릭 링크 생성
sudo ln -s /etc/nginx/sites-available/computeroff /etc/nginx/sites-enabled/

# 기본 설정 비활성화
sudo rm /etc/nginx/sites-enabled/default

# 설정 테스트
sudo nginx -t

# Nginx 재시작
sudo systemctl restart nginx
```

### 1.4 방화벽 설정

```bash
# UFW (Ubuntu)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# firewalld (CentOS)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

---

## 2. IP만 사용하는 경우 (Self-signed)

도메인이 없고 IP 주소로만 접근하는 경우 자체 서명 인증서를 사용합니다.

### 2.1 Self-signed 인증서 생성

```bash
# 디렉토리 생성
sudo mkdir -p /etc/nginx/ssl

# 인증서 생성 (10년 유효)
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/server.key \
    -out /etc/nginx/ssl/server.crt \
    -subj "/C=KR/ST=Seoul/L=Seoul/O=ComputerOff/CN=34.64.116.152"

# 권한 설정
sudo chmod 600 /etc/nginx/ssl/server.key
sudo chmod 644 /etc/nginx/ssl/server.crt
```

### 2.2 Nginx 설정 수정

`/etc/nginx/sites-available/computeroff` 파일에서:

```nginx
# Let's Encrypt 인증서 주석 처리
# ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
# ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

# Self-signed 인증서 활성화
ssl_certificate /etc/nginx/ssl/server.crt;
ssl_certificate_key /etc/nginx/ssl/server.key;

# OCSP Stapling 비활성화 (Self-signed에서는 작동 안함)
# ssl_stapling on;
# ssl_stapling_verify on;
```

### 2.3 Agent에서 인증서 검증 비활성화

Self-signed 인증서는 브라우저와 Agent에서 신뢰하지 않으므로, Agent 설정에서 검증을 비활성화해야 합니다.

`agent/installer.py`의 requests 호출에 `verify=False` 추가:

```python
response = requests.post(url, json=data, timeout=5, verify=False)
```

**주의**: 이 방법은 개발/테스트 환경에서만 사용하세요. 프로덕션에서는 Let's Encrypt 사용을 권장합니다.

---

## 3. Agent 설정 변경

### 3.1 기존 Agent 업데이트

설치된 Agent의 서버 URL을 HTTPS로 변경합니다:

```bash
# 관리자 권한으로 실행
agent.exe --install https://your-domain.com
# 또는
agent.exe --install https://34.64.116.152
```

### 3.2 config.json 직접 수정

`config.json` 파일을 직접 수정할 수도 있습니다:

```json
{
  "server_url": "https://your-domain.com",
  "api_key": "your-api-key-here"
}
```

---

## 보안 체크리스트

- [ ] HTTP 요청이 HTTPS로 리다이렉트되는지 확인
- [ ] SSL Labs 테스트 통과 (https://www.ssllabs.com/ssltest/)
- [ ] HSTS 헤더 적용 확인
- [ ] 인증서 자동 갱신 설정 (Let's Encrypt)
- [ ] Agent가 HTTPS로 정상 통신하는지 확인

---

## 문제 해결

### 인증서 갱신 실패

```bash
# 수동 갱신
sudo certbot renew

# 로그 확인
sudo cat /var/log/letsencrypt/letsencrypt.log
```

### Nginx 502 Bad Gateway

```bash
# FastAPI 서버가 실행 중인지 확인
systemctl status computeroff

# 포트 확인
netstat -tlnp | grep 8000
```

### Agent 연결 실패

```bash
# 서버에서 curl 테스트
curl -k https://localhost/api/health

# 방화벽 확인
sudo ufw status
```
