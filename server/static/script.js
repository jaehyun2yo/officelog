const API_BASE = '';
let currentComputer = null;
let renameTarget = null;
let deleteTarget = null;
let isSettingPassword = false;
let displayNameMap = {};  // hostname -> display_name 매핑
let historyViewMode = 'summary';  // 'summary' or 'detail'

async function fetchJSON(url) {
    const response = await fetch(url);
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
}

function showLoginUI() {
    isSettingPassword = false;
    document.getElementById('auth-subtitle').textContent = '관리자 로그인';
    document.getElementById('auth-label').textContent = '비밀번호';
    document.getElementById('auth-confirm-group').style.display = 'none';
    document.getElementById('auth-submit').textContent = '로그인';
    document.getElementById('auth-overlay').style.display = 'flex';
    document.getElementById('auth-password').focus();
}

function hideAuthOverlay() {
    document.getElementById('auth-overlay').style.display = 'none';
    document.getElementById('auth-password').value = '';
    document.getElementById('auth-password-confirm').value = '';
    document.getElementById('auth-error').textContent = '';
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
        if (password.length < 4) {
            errorEl.textContent = '비밀번호는 최소 4자 이상이어야 합니다.';
            return;
        }

        try {
            const response = await fetch('/api/auth/set-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });

            if (response.ok) {
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
                            ${pc.status === 'online' ? '마지막 확인: 방금 전' : '마지막 활동: ' + formatTimeAgo(pc.last_boot || pc.last_shutdown)}
                        </div>
                    </div>
                    <span class="status ${pc.status}">
                        <span class="status-dot ${pc.status}"></span>
                        ${pc.status === 'online' ? '온라인' : '오프라인'}
                    </span>
                </div>
                <div class="computer-actions">
                    <button class="action-btn edit-btn" onclick="openRenameModal('${pc.computer_name}', '${pc.display_name || ''}')" title="이름 변경">✏️</button>
                    <button class="action-btn delete-btn" onclick="openDeleteModal('${pc.computer_name}')" title="삭제">🗑️</button>
                </div>
            </div>
        `}).join('');

        document.getElementById('total-computers').textContent = data.computers.length;
        document.getElementById('online-count').textContent =
            data.computers.filter(pc => pc.status === 'online').length;

    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>데이터를 불러올 수 없습니다</p></div>`;
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
                                ${event.event_type === 'boot' ? '▲ 컴퓨터 시작' : '▼ 컴퓨터 종료'}
                            </span>
                        </div>
                    `;
                });

                html += `</div></div>`;
            }

            container.innerHTML = html;
        }

    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>데이터를 불러올 수 없습니다</p></div>`;
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
        const response = await fetch(`/api/computers/${encodeURIComponent(renameTarget)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: newName })
        });

        if (response.ok) {
            closeRenameModal();
            loadComputers();
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
        const response = await fetch(`/api/computers/${encodeURIComponent(deleteTarget)}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            closeDeleteModal();
            refreshAll();
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
    }
});

// 모달 바깥 클릭 시 닫기
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) {
            closeModal();
            closeRenameModal();
            closeDeleteModal();
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
        tbody.innerHTML = '<tr><td colspan="100" class="empty-state">데이터를 불러올 수 없습니다</td></tr>';
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
                const eventIcon = event.event_type === 'boot' ? '▲' : '▼';
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
        container.innerHTML = `<div class="empty-state"><p>데이터를 불러올 수 없습니다</p></div>`;
    }
}

async function loadTodaySummary() {
    const tbody = document.getElementById('today-summary-body');
    const dateSpan = document.getElementById('today-date');

    // 오늘 날짜 표시
    const today = new Date();
    const month = String(today.getMonth() + 1).padStart(2, '0');
    const day = String(today.getDate()).padStart(2, '0');
    const dayNames = ['일', '월', '화', '수', '목', '금', '토'];
    const dayName = dayNames[today.getDay()];
    dateSpan.textContent = `(${month}/${day} ${dayName})`;

    try {
        const data = await fetchJSON('/api/daily-summary?days=1');

        // 오늘 날짜 문자열 (YYYY-MM-DD)
        const todayStr = today.toISOString().split('T')[0];

        // 오늘 데이터만 필터링
        const todayData = data.summary.filter(s => s.date === todayStr);

        if (todayData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="empty-state">오늘 기록된 이벤트가 없습니다</td></tr>';
            return;
        }

        let html = '';
        todayData.forEach(item => {
            const displayName = displayNameMap[item.computer_name] || item.computer_name;
            const firstBoot = item.first_boot ? item.first_boot.substring(0, 5) : '-';
            const lastShutdown = item.last_shutdown ? item.last_shutdown.substring(0, 5) : '-';
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
        tbody.innerHTML = '<tr><td colspan="3" class="empty-state">데이터를 불러올 수 없습니다</td></tr>';
    }
}

function refreshAll() {
    loadComputers();
    loadTodaySummary();
    loadDailySummary();
    loadAllTimeline();
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
    // 인증 확인 후 데이터 로드
    const authenticated = await checkAuth();
    if (authenticated) {
        refreshAll();
    }
    // 10초마다 자동 새로고침 (실시간 상태 확인)
    setInterval(refreshAll, 10000);
});
