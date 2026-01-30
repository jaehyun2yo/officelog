const API_BASE = '';
let currentComputer = null;

async function fetchJSON(url) {
    const response = await fetch(url);
    return response.json();
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

        container.innerHTML = data.computers.map(pc => `
            <div class="computer-item clickable" onclick="openHistory('${pc.computer_name}')">
                <div>
                    <div class="computer-name">${pc.computer_name}</div>
                    <div class="computer-info">
                        ${pc.status === 'online' ? '마지막 확인: 방금 전' : '마지막 활동: ' + formatTimeAgo(pc.last_boot || pc.last_shutdown)}
                    </div>
                </div>
                <span class="status ${pc.status}">
                    <span class="status-dot ${pc.status}"></span>
                    ${pc.status === 'online' ? '온라인' : '오프라인'}
                </span>
            </div>
        `).join('');

        document.getElementById('total-computers').textContent = data.computers.length;
        document.getElementById('online-count').textContent =
            data.computers.filter(pc => pc.status === 'online').length;

    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>데이터를 불러올 수 없습니다</p></div>`;
    }
}

async function loadEvents() {
    const container = document.getElementById('events-list');

    try {
        const data = await fetchJSON('/api/events?limit=50');

        if (data.events.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>기록된 이벤트가 없습니다</p>
                </div>
            `;
            return;
        }

        container.innerHTML = data.events.map(event => `
            <div class="event-item ${event.event_type}">
                <div class="event-icon">
                    ${event.event_type === 'boot' ? '▲' : '▼'}
                </div>
                <div class="event-details">
                    <div class="event-computer">${event.computer_name}</div>
                    <div class="event-time">${formatDateTime(event.timestamp)}</div>
                </div>
                <span class="event-type">${event.event_type === 'boot' ? '부팅' : '종료'}</span>
            </div>
        `).join('');

        document.getElementById('total-events').textContent = data.count;

    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>데이터를 불러올 수 없습니다</p></div>`;
    }
}

// 모달 열기
function openHistory(computerName) {
    currentComputer = computerName;
    document.getElementById('modal-title').textContent = `${computerName} 이력`;
    document.getElementById('history-modal').classList.add('show');
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
                            ${event.event_type === 'boot' ? '▲ 부팅' : '▼ 종료'}
                        </span>
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

// ESC 키로 모달 닫기
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
    }
});

// 모달 바깥 클릭 시 닫기
document.getElementById('history-modal').addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        closeModal();
    }
});

function refreshAll() {
    loadComputers();
    loadEvents();
}

document.addEventListener('DOMContentLoaded', () => {
    refreshAll();
    // 10초마다 자동 새로고침 (실시간 상태 확인)
    setInterval(refreshAll, 10000);
});
