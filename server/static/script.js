const API_BASE = '';
let currentComputer = null;
let renameTarget = null;
let deleteTarget = null;
let isSettingPassword = false;
let displayNameMap = {};  // hostname -> display_name 매핑
let historyViewMode = 'summary';  // 'summary' or 'detail'
let csrfToken = null;  // CSRF 토큰 저장

async function fetchJSON(url) {
    const response = await fetch(url);
    if (response.status === 401) {
        // 인증 필요
        showLoginUI();
        throw new Error('Authentication required');
    }
    return response.json();
}

// ==================== 인증 관련 ====================

async function checkAuth() {
    try {
        const data = await fetchJSON('/api/auth/check');

        if (!data.password_set) {
            // 비밀번호 미설정 - 초기 설정 화면
            showSetPasswordUI();
            return false;
        }

        if (!data.authenticated) {
            // 미인증 - 로그인 화면
            showLoginUI();
            return false;
        }

        // CSRF 토큰 저장
        if (data.csrf_token) {
            csrfToken = data.csrf_token;
        }

        // 인증됨 - 오버레이 숨김
        hideAuthOverlay();
        return true;
    } catch (error) {
        console.error('Auth check failed:', error);
        return false;
    }
}

function showSetPasswordUI() {
    isSettingPassword = true;
    document.getElementById('auth-subtitle').textContent = '초기 비밀번호 설정';
    document.getElementById('auth-label').textContent = '새 비밀번호';
    document.getElementById('auth-confirm-group').style.display = 'block';
    document.getElementById('auth-submit').textContent = '설정 완료';
    document.getElementById('auth-overlay').style.display = 'flex';
    document.getElementById('auth-password').focus();

    // 비밀번호 정책 힌트 표시
    const hint = document.getElementById('password-hint');
    if (hint) {
        hint.style.display = 'block';
    }
}

function showLoginUI() {
    isSettingPassword = false;
    document.getElementById('auth-subtitle').textContent = '관리자 로그인';
    document.getElementById('auth-label').textContent = '비밀번호';
    document.getElementById('auth-confirm-group').style.display = 'none';
    document.getElementById('auth-submit').textContent = '로그인';
    document.getElementById('auth-overlay').style.display = 'flex';
    document.getElementById('auth-password').focus();

    // 비밀번호 정책 힌트 숨김
    const hint = document.getElementById('password-hint');
    if (hint) {
        hint.style.display = 'none';
    }
}

function hideAuthOverlay() {
    document.getElementById('auth-overlay').style.display = 'none';
    document.getElementById('auth-password').value = '';
    document.getElementById('auth-password-confirm').value = '';
    document.getElementById('auth-error').textContent = '';
}

// 비밀번호 정책 검증 (프론트엔드)
function validatePasswordPolicy(password) {
    if (password.length < 8) {
        return '비밀번호는 최소 8자 이상이어야 합니다.';
    }

    const hasUpper = /[A-Z]/.test(password);
    const hasLower = /[a-z]/.test(password);
    const hasDigit = /[0-9]/.test(password);

    if (!hasUpper || !hasLower || !hasDigit) {
        return '비밀번호는 대문자, 소문자, 숫자를 각각 1개 이상 포함해야 합니다.';
    }

    return null;  // 통과
}

async function handleAuth() {
    const password = document.getElementById('auth-password').value;
    const errorEl = document.getElementById('auth-error');
    errorEl.textContent = '';

    if (!password) {
        errorEl.textContent = '비밀번호를 입력하세요.';
        return;
    }

    if (isSettingPassword) {
        // 비밀번호 설정
        const confirm = document.getElementById('auth-password-confirm').value;
        if (password !== confirm) {
            errorEl.textContent = '비밀번호가 일치하지 않습니다.';
            return;
        }

        // 비밀번호 정책 검증
        const policyError = validatePasswordPolicy(password);
        if (policyError) {
            errorEl.textContent = policyError;
            return;
        }

        try {
            const response = await fetch('/api/auth/set-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.csrf_token) {
                    csrfToken = data.csrf_token;
                }
                hideAuthOverlay();
                refreshAll();
            } else {
                const data = await response.json();
                errorEl.textContent = data.detail || '설정에 실패했습니다.';
            }
        } catch (error) {
            errorEl.textContent = '오류가 발생했습니다.';
        }
    } else {
        // 로그인
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });

            if (response.ok) {
                const data = await response.json();
                if (data.csrf_token) {
                    csrfToken = data.csrf_token;
                }
                hideAuthOverlay();
                refreshAll();
            } else {
                const data = await response.json();
                errorEl.textContent = data.detail || '로그인에 실패했습니다.';
            }
        } catch (error) {
            errorEl.textContent = '오류가 발생했습니다.';
        }
    }
}

async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
        csrfToken = null;
        showLoginUI();
    } catch (error) {
        console.error('Logout failed:', error);
    }
}

function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

function formatTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function formatTimeAgo(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return '방금 전';
    if (diffMins < 60) return `${diffMins}분 전`;
    if (diffHours < 24) return `${diffHours}시간 전`;
    return `${diffDays}일 전`;
}

async function loadComputers() {
    const container = document.getElementById('computers-list');

    try {
        const data = await fetchJSON('/api/computers');

        if (data.computers.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>등록된 컴퓨터가 없습니다</p>
                    <p>Agent를 설치하면 자동으로 표시됩니다</p>
                </div>
            `;
            return;
        }

        // display_name 매핑 업데이트
        displayNameMap = {};
        data.computers.forEach(pc => {
            if (pc.display_name) {
                displayNameMap[pc.computer_name] = pc.display_name;
            }
        });

        container.innerHTML = data.computers.map(pc => {
            const displayName = pc.display_name || pc.computer_name;
            const showHostname = pc.display_name ? `<span class="hostname-badge">${pc.computer_name}</span>` : '';
            const ipBadge = pc.ip_address ? `<span class="ip-badge">${pc.ip_address}</span>` : '';
            return `
            <div class="computer-item">
                <div class="computer-main clickable" onclick="openHistory('${pc.computer_name}')">
                    <div>
                        <div class="computer-name">${displayName} ${showHostname} ${ipBadge}</div>
                        <div class="computer-info">
                            ${pc.status === 'online' ? '마지막 확인: 방금 전' : '마지막 활동: ' + formatTimeAgo(
                                pc.last_boot && pc.last_shutdown
                                    ? (pc.last_boot > pc.last_shutdown ? pc.last_boot : pc.last_shutdown)
                                    : (pc.last_boot || pc.last_shutdown)
                            )}
                        </div>
                    </div>
                    <span class="status ${pc.status}">
                        <span class="status-dot ${pc.status}"></span>
                        ${pc.status === 'online' ? '온라인' : '오프라인'}
                    </span>
                </div>
                <div class="computer-actions">
                    <button class="action-btn edit-btn" onclick="openRenameModal('${pc.computer_name}', '${pc.display_name || ''}')" title="이름 변경">&#9998;</button>
                    <button class="action-btn delete-btn" onclick="openDeleteModal('${pc.computer_name}')" title="삭제">&#128465;</button>
                </div>
            </div>
        `}).join('');

    } catch (error) {
        if (error.message !== 'Authentication required') {
            container.innerHTML = `<div class="empty-state"><p>데이터를 불러올 수 없습니다</p></div>`;
        }
    }
}

// 히스토리 뷰 모드 설정
function setHistoryView(mode) {
    historyViewMode = mode;
    document.getElementById('view-summary').classList.toggle('active', mode === 'summary');
    document.getElementById('view-detail').classList.toggle('active', mode === 'detail');
    loadHistory();
}

// 모달 열기
function openHistory(computerName) {
    currentComputer = computerName;
    const displayName = displayNameMap[computerName] || computerName;
    document.getElementById('modal-title').textContent = `${displayName} 이력`;
    document.getElementById('history-modal').classList.add('show');
    // 기본값 요약 뷰로 설정
    historyViewMode = 'summary';
    document.getElementById('view-summary').classList.add('active');
    document.getElementById('view-detail').classList.remove('active');
    loadHistory();
}

// 모달 닫기
function closeModal() {
    document.getElementById('history-modal').classList.remove('show');
    currentComputer = null;
}

// 이력 로드
async function loadHistory() {
    if (!currentComputer) return;

    const container = document.getElementById('history-list');
    const days = document.getElementById('days-filter').value;

    container.innerHTML = '<div class="empty-state"><p>로딩 중...</p></div>';

    try {
        if (historyViewMode === 'summary') {
            // 요약 뷰 - 하루 단위로 첫 시작 / 마지막 종료
            const data = await fetchJSON(`/api/computers/${encodeURIComponent(currentComputer)}/daily-summary?days=${days}`);

            if (data.summary.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <p>해당 기간에 기록된 이벤트가 없습니다</p>
                    </div>
                `;
                return;
            }

            let html = '<div class="summary-table-wrapper"><table class="summary-table">';
            html += '<thead><tr><th>날짜</th><th>첫 시작</th><th>마지막 종료</th></tr></thead>';
            html += '<tbody>';

            data.summary.forEach(item => {
                const dateStr = formatDateShort(item.date);
                const firstBoot = item.first_boot ? item.first_boot.substring(0, 5) : '-';
                const lastShutdown = item.last_shutdown ? item.last_shutdown.substring(0, 5) : '-';
                html += `
                    <tr>
                        <td class="date-cell">${dateStr}</td>
                        <td class="time-cell boot">${firstBoot}</td>
                        <td class="time-cell shutdown">${lastShutdown}</td>
                    </tr>
                `;
            });

            html += '</tbody></table></div>';
            container.innerHTML = html;

        } else {
            // 상세 뷰 - 모든 이벤트 표시
            const data = await fetchJSON(`/api/computers/${encodeURIComponent(currentComputer)}/history?days=${days}`);

            if (data.history.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <p>해당 기간에 기록된 이벤트가 없습니다</p>
                    </div>
                `;
                return;
            }

            // 날짜별로 그룹화
            const grouped = {};
            data.history.forEach(event => {
                const date = formatDate(event.timestamp);
                if (!grouped[date]) {
                    grouped[date] = [];
                }
                grouped[date].push(event);
            });

            let html = '';
            for (const [date, events] of Object.entries(grouped)) {
                html += `<div class="history-date-group">`;
                html += `<div class="history-date">${date}</div>`;
                html += `<div class="history-events">`;

                events.forEach(event => {
                    html += `
                        <div class="history-event ${event.event_type}">
                            <span class="history-time">${formatTime(event.timestamp)}</span>
                            <span class="history-type ${event.event_type}">
                                ${event.event_type === 'boot' ? '&#9650; 컴퓨터 시작' : '&#9660; 컴퓨터 종료'}
                            </span>
                        </div>
                    `;
                });

                html += `</div></div>`;
            }

            container.innerHTML = html;
        }

    } catch (error) {
        if (error.message !== 'Authentication required') {
            container.innerHTML = `<div class="empty-state"><p>데이터를 불러올 수 없습니다</p></div>`;
        }
    }
}

// 이름 변경 모달 열기
function openRenameModal(hostname, currentName) {
    renameTarget = hostname;
    document.getElementById('rename-hostname').textContent = hostname;
    document.getElementById('new-display-name').value = currentName;
    document.getElementById('rename-modal').classList.add('show');
    document.getElementById('new-display-name').focus();
}

// 이름 변경 모달 닫기
function closeRenameModal() {
    document.getElementById('rename-modal').classList.remove('show');
    renameTarget = null;
}

// 표시 이름 저장
async function saveDisplayName() {
    if (!renameTarget) return;

    const newName = document.getElementById('new-display-name').value.trim();
    if (!newName) {
        alert('표시 이름을 입력하세요.');
        return;
    }

    try {
        const headers = { 'Content-Type': 'application/json' };
        if (csrfToken) {
            headers['X-CSRF-Token'] = csrfToken;
        }

        const response = await fetch(`/api/computers/${encodeURIComponent(renameTarget)}`, {
            method: 'PUT',
            headers: headers,
            body: JSON.stringify({ display_name: newName })
        });

        if (response.ok) {
            closeRenameModal();
            loadComputers();
        } else if (response.status === 403) {
            alert('CSRF 토큰이 만료되었습니다. 페이지를 새로고침하세요.');
            location.reload();
        } else {
            alert('이름 변경에 실패했습니다.');
        }
    } catch (error) {
        alert('오류가 발생했습니다.');
    }
}

// 삭제 모달 열기
function openDeleteModal(hostname) {
    deleteTarget = hostname;
    document.getElementById('delete-hostname').textContent = hostname;
    document.getElementById('delete-modal').classList.add('show');
}

// 삭제 모달 닫기
function closeDeleteModal() {
    document.getElementById('delete-modal').classList.remove('show');
    deleteTarget = null;
}

// 삭제 확인
async function confirmDelete() {
    if (!deleteTarget) return;

    try {
        const headers = {};
        if (csrfToken) {
            headers['X-CSRF-Token'] = csrfToken;
        }

        const response = await fetch(`/api/computers/${encodeURIComponent(deleteTarget)}`, {
            method: 'DELETE',
            headers: headers
        });

        if (response.ok) {
            closeDeleteModal();
            refreshAll();
        } else if (response.status === 403) {
            alert('CSRF 토큰이 만료되었습니다. 페이지를 새로고침하세요.');
            location.reload();
        } else {
            alert('삭제에 실패했습니다.');
        }
    } catch (error) {
        alert('오류가 발생했습니다.');
    }
}

// 모두 삭제 모달 열기
function openDeleteAllModal() {
    document.getElementById('delete-all-confirm').value = '';
    document.getElementById('delete-all-modal').classList.add('show');
    document.getElementById('delete-all-confirm').focus();
}

// 모두 삭제 모달 닫기
function closeDeleteAllModal() {
    document.getElementById('delete-all-modal').classList.remove('show');
    document.getElementById('delete-all-confirm').value = '';
}

// 모두 삭제 확인
async function confirmDeleteAll() {
    const confirmInput = document.getElementById('delete-all-confirm').value;
    if (confirmInput !== '삭제') {
        alert('"삭제"를 정확히 입력해주세요.');
        return;
    }

    try {
        const headers = {};
        if (csrfToken) {
            headers['X-CSRF-Token'] = csrfToken;
        }

        const response = await fetch('/api/computers', {
            method: 'DELETE',
            headers: headers
        });

        if (response.ok) {
            const data = await response.json();
            closeDeleteAllModal();
            alert(`${data.deleted_computers}개의 컴퓨터와 ${data.deleted_events}개의 이벤트가 삭제되었습니다.`);
            refreshAll();
        } else if (response.status === 403) {
            alert('CSRF 토큰이 만료되었습니다. 페이지를 새로고침하세요.');
            location.reload();
        } else {
            alert('삭제에 실패했습니다.');
        }
    } catch (error) {
        alert('오류가 발생했습니다.');
    }
}

// ESC 키로 모달 닫기
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
        closeRenameModal();
        closeDeleteModal();
        closeDeleteAllModal();
    }
});

// 모달 바깥 클릭 시 닫기
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) {
            closeModal();
            closeRenameModal();
            closeDeleteModal();
            closeDeleteAllModal();
        }
    });
});

async function loadDailySummary() {
    const days = document.getElementById('summary-days').value;
    const tbody = document.getElementById('summary-body');
    try {
        const data = await fetchJSON(`/api/daily-summary?days=${days}`);
        if (data.summary.length === 0) {
            tbody.innerHTML = '<tr><td colspan="100" class="empty-state">데이터가 없습니다</td></tr>';
            return;
        }
        const dates = [...new Set(data.summary.map(s => s.date))].sort().reverse();
        const computers = [...new Set(data.summary.map(s => s.computer_name))];
        let headerHtml = '<th>날짜</th>';
        computers.forEach(hostname => {
            headerHtml += `<th>${displayNameMap[hostname] || hostname}</th>`;
        });
        document.querySelector('#summary-table thead tr').innerHTML = headerHtml;
        const dataMap = {};
        data.summary.forEach(s => {
            if (!dataMap[s.date]) dataMap[s.date] = {};
            dataMap[s.date][s.computer_name] = s;
        });
        let bodyHtml = '';
        dates.forEach(date => {
            bodyHtml += `<tr><td class="date-cell">${formatDateShort(date)}</td>`;
            computers.forEach(hostname => {
                const info = dataMap[date]?.[hostname];
                if (info) {
                    const boot = info.first_boot ? info.first_boot.substring(0, 5) : '-';
                    const shutdown = info.last_shutdown ? info.last_shutdown.substring(0, 5) : '-';
                    bodyHtml += `<td class="time-cell">${boot} / ${shutdown}</td>`;
                } else {
                    bodyHtml += '<td class="time-cell empty">-</td>';
                }
            });
            bodyHtml += '</tr>';
        });
        tbody.innerHTML = bodyHtml;
    } catch (error) {
        if (error.message !== 'Authentication required') {
            tbody.innerHTML = '<tr><td colspan="100" class="empty-state">데이터를 불러올 수 없습니다</td></tr>';
        }
    }
}

function formatDateShort(dateStr) {
    const date = new Date(dateStr);
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const dayNames = ['일', '월', '화', '수', '목', '금', '토'];
    const dayName = dayNames[date.getDay()];
    return `${month}/${day} (${dayName})`;
}

async function loadAllTimeline() {
    const container = document.getElementById('all-timeline');
    const days = document.getElementById('timeline-days').value;

    try {
        const data = await fetchJSON(`/api/timeline/all?days=${days}&limit=100`);

        if (data.events.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>해당 기간에 기록된 이벤트가 없습니다</p>
                </div>
            `;
            return;
        }

        // 날짜별로 그룹화
        const grouped = {};
        data.events.forEach(event => {
            const date = formatDate(event.timestamp);
            if (!grouped[date]) {
                grouped[date] = [];
            }
            grouped[date].push(event);
        });

        let html = '';
        for (const [date, events] of Object.entries(grouped)) {
            html += `<div class="timeline-date-group">`;
            html += `<div class="timeline-date-header">${date}</div>`;
            html += `<div class="timeline-events">`;

            events.forEach(event => {
                const displayName = event.display_name || event.computer_name;
                const eventIcon = event.event_type === 'boot' ? '&#9650;' : '&#9660;';
                const eventText = event.event_type === 'boot' ? '시작' : '종료';
                html += `
                    <div class="timeline-event ${event.event_type}">
                        <span class="timeline-time">${formatTime(event.timestamp)}</span>
                        <span class="timeline-computer">${displayName}</span>
                        <span class="timeline-type ${event.event_type}">${eventIcon} ${eventText}</span>
                    </div>
                `;
            });

            html += `</div></div>`;
        }

        container.innerHTML = html;

    } catch (error) {
        if (error.message !== 'Authentication required') {
            container.innerHTML = `<div class="empty-state"><p>데이터를 불러올 수 없습니다</p></div>`;
        }
    }
}

// 로컬 시간대 기준 날짜 문자열 반환 (YYYY-MM-DD)
function getLocalDateString(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// 날짜 변경 함수
function changeDate(delta) {
    const dateInput = document.getElementById('summary-date');
    const currentDate = new Date(dateInput.value);
    currentDate.setDate(currentDate.getDate() + delta);
    dateInput.value = getLocalDateString(currentDate);
    loadDateSummary();
}

// 오늘로 이동
function goToToday() {
    const dateInput = document.getElementById('summary-date');
    dateInput.value = getLocalDateString(new Date());
    loadDateSummary();
}

// 날짜 선택기 초기화
function initDatePicker() {
    const dateInput = document.getElementById('summary-date');
    dateInput.value = getLocalDateString(new Date());
}

async function loadDateSummary() {
    const tbody = document.getElementById('today-summary-body');
    const dateInput = document.getElementById('summary-date');
    const selectedDate = dateInput.value;

    try {
        // 1. 모든 등록된 컴퓨터 목록 조회
        const computersData = await fetchJSON('/api/computers');
        const allComputers = computersData.computers;

        if (allComputers.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="empty-state">등록된 컴퓨터가 없습니다</td></tr>';
            return;
        }

        // 2. 해당 날짜의 이벤트 조회 (30일치 가져와서 필터링)
        const summaryData = await fetchJSON('/api/daily-summary?days=30');
        const dateEvents = summaryData.summary.filter(s => s.date === selectedDate);

        // 3. 이벤트를 컴퓨터별 맵으로 변환
        const eventMap = {};
        dateEvents.forEach(e => {
            eventMap[e.computer_name] = e;
        });

        // 4. 모든 컴퓨터 표시 (이벤트 없으면 "-")
        let html = '';
        allComputers.forEach(pc => {
            const displayName = pc.display_name || pc.computer_name;
            const event = eventMap[pc.computer_name];
            const firstBoot = event?.first_boot ? event.first_boot.substring(0, 5) : '-';
            const lastShutdown = event?.last_shutdown ? event.last_shutdown.substring(0, 5) : '-';
            html += `
                <tr>
                    <td class="computer-cell">${displayName}</td>
                    <td class="time-cell boot">${firstBoot}</td>
                    <td class="time-cell shutdown">${lastShutdown}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;

    } catch (error) {
        if (error.message !== 'Authentication required') {
            tbody.innerHTML = '<tr><td colspan="3" class="empty-state">데이터를 불러올 수 없습니다</td></tr>';
        }
    }
}

// 사용 현황 그래프 로드
let usageChart = null;

async function loadUsageChart() {
    const ctx = document.getElementById('usage-chart');
    if (!ctx) return;

    try {
        // 최근 7일간 데이터 조회
        const summaryData = await fetchJSON('/api/daily-summary?days=7');
        const computersData = await fetchJSON('/api/computers');

        if (summaryData.summary.length === 0 || computersData.computers.length === 0) {
            return;
        }

        // 날짜 목록 (최근 7일, 오래된 순)
        const dates = [...new Set(summaryData.summary.map(s => s.date))].sort();
        const computers = computersData.computers;

        // 컴퓨터별 색상
        const colors = [
            { bg: 'rgba(52, 152, 219, 0.7)', border: 'rgb(52, 152, 219)' },
            { bg: 'rgba(46, 204, 113, 0.7)', border: 'rgb(46, 204, 113)' },
            { bg: 'rgba(155, 89, 182, 0.7)', border: 'rgb(155, 89, 182)' },
            { bg: 'rgba(241, 196, 15, 0.7)', border: 'rgb(241, 196, 15)' },
            { bg: 'rgba(230, 126, 34, 0.7)', border: 'rgb(230, 126, 34)' },
            { bg: 'rgba(231, 76, 60, 0.7)', border: 'rgb(231, 76, 60)' },
        ];

        // 데이터 맵 생성
        const dataMap = {};
        summaryData.summary.forEach(s => {
            if (!dataMap[s.date]) dataMap[s.date] = {};
            dataMap[s.date][s.computer_name] = s;
        });

        // 데이터셋 생성 (각 컴퓨터별로 시작~종료 시간 막대)
        const datasets = [];
        computers.forEach((pc, idx) => {
            const color = colors[idx % colors.length];
            const displayName = pc.display_name || pc.computer_name;

            // 시작 시간 데이터
            const bootData = dates.map(date => {
                const info = dataMap[date]?.[pc.computer_name];
                if (info?.first_boot) {
                    const [h, m] = info.first_boot.split(':').map(Number);
                    return h + m / 60;
                }
                return null;
            });

            // 종료 시간 데이터
            const shutdownData = dates.map(date => {
                const info = dataMap[date]?.[pc.computer_name];
                if (info?.last_shutdown) {
                    const [h, m] = info.last_shutdown.split(':').map(Number);
                    return h + m / 60;
                }
                return null;
            });

            // Floating bar chart (시작~종료)
            const barData = dates.map((date, i) => {
                if (bootData[i] !== null && shutdownData[i] !== null) {
                    return [bootData[i], shutdownData[i]];
                } else if (bootData[i] !== null) {
                    return [bootData[i], bootData[i] + 0.5]; // 종료 없으면 시작만 표시
                } else if (shutdownData[i] !== null) {
                    return [shutdownData[i] - 0.5, shutdownData[i]]; // 시작 없으면 종료만 표시
                }
                return null;
            });

            datasets.push({
                label: displayName,
                data: barData,
                backgroundColor: color.bg,
                borderColor: color.border,
                borderWidth: 1,
                borderRadius: 4,
                barPercentage: 0.6,
                categoryPercentage: 0.8,
            });
        });

        // 날짜 라벨 포맷팅
        const labels = dates.map(date => {
            const d = new Date(date);
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            const dayNames = ['일', '월', '화', '수', '목', '금', '토'];
            return `${month}/${day}(${dayNames[d.getDay()]})`;
        });

        // 기존 차트 제거
        if (usageChart) {
            usageChart.destroy();
        }

        // 차트 생성
        usageChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'x',
                scales: {
                    y: {
                        min: 6,
                        max: 24,
                        reverse: false,
                        ticks: {
                            stepSize: 2,
                            callback: function(value) {
                                return value + ':00';
                            }
                        },
                        title: {
                            display: true,
                            text: '시간'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: '날짜'
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const data = context.raw;
                                if (Array.isArray(data)) {
                                    const startH = Math.floor(data[0]);
                                    const startM = Math.round((data[0] - startH) * 60);
                                    const endH = Math.floor(data[1]);
                                    const endM = Math.round((data[1] - endH) * 60);
                                    const start = `${String(startH).padStart(2, '0')}:${String(startM).padStart(2, '0')}`;
                                    const end = `${String(endH).padStart(2, '0')}:${String(endM).padStart(2, '0')}`;
                                    return `${context.dataset.label}: ${start} ~ ${end}`;
                                }
                                return context.dataset.label;
                            }
                        }
                    }
                }
            }
        });

    } catch (error) {
        console.error('Failed to load usage chart:', error);
    }
}

function refreshAll() {
    loadComputers();
    loadDateSummary();
    loadDailySummary();
    loadAllTimeline();
    loadUsageChart();
}

// Enter 키로 이름 저장
document.getElementById('new-display-name').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        saveDisplayName();
    }
});

// Enter 키로 로그인/설정
document.getElementById('auth-password').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        if (isSettingPassword) {
            document.getElementById('auth-password-confirm').focus();
        } else {
            handleAuth();
        }
    }
});

document.getElementById('auth-password-confirm').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        handleAuth();
    }
});

document.addEventListener('DOMContentLoaded', async () => {
    // 날짜 선택기 초기화
    initDatePicker();

    // 인증 확인 후 데이터 로드
    const authenticated = await checkAuth();
    if (authenticated) {
        refreshAll();
    }
    // 10초마다 자동 새로고침 (실시간 상태 확인)
    setInterval(refreshAll, 10000);
});
