// static/activity_logs/js/calendar.js

const calState = {
    year: ACTIVITY_CONFIG.year,
    month: ACTIVITY_CONFIG.month,
    weekStart: null,
    modalStack: [],
    cachedUserLogs: {},
};

// ── Utilities ────────────────────────────────────────────────────

async function fetchJSON(url) {
    const res = await fetch(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

function formatTime(isoStr) {
    if (!isoStr) return '';
    return new Date(isoStr).toLocaleTimeString('en-IN', {
        hour: '2-digit', minute: '2-digit', hour12: true
    });
}

function formatDateTime(isoStr) {
    if (!isoStr) return '';
    return new Date(isoStr).toLocaleString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true
    });
}

function timeAgo(isoStr) {
    const diff = Date.now() - new Date(isoStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}

function formatRole(role) {
    return (role || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function categoryBadgeClass(cat) {
    const map = {
        create: 'bg-green-100 text-green-700',
        update: 'bg-blue-100 text-blue-700',
        delete: 'bg-red-100 text-red-700',
        auth: 'bg-purple-100 text-purple-700',
        export: 'bg-yellow-100 text-yellow-700',
        approve: 'bg-emerald-100 text-emerald-700',
        reject: 'bg-orange-100 text-orange-700',
        permission_denied: 'bg-red-100 text-red-800',
        system: 'bg-gray-100 text-gray-600',
        email: 'bg-indigo-100 text-indigo-700',
        bulk_action: 'bg-cyan-100 text-cyan-700',
    };
    return map[cat] || 'bg-gray-100 text-gray-600';
}

function levelColor(level) {
    const map = {
        high: 'bg-green-100 hover:bg-green-200 text-green-900',
        medium: 'bg-yellow-100 hover:bg-yellow-200 text-yellow-900',
        low: 'bg-red-100 hover:bg-red-200 text-red-900',
        none: 'bg-red-50 hover:bg-red-100 text-red-400',
        holiday: 'bg-purple-100 text-purple-700 cursor-default',
        future: 'bg-gray-100 text-gray-300 cursor-default',
        other_month: 'bg-gray-50 text-gray-300 cursor-default',
    };
    return map[level] || 'bg-gray-100 text-gray-400 cursor-default';
}

// ── Modal helpers ────────────────────────────────────────────────

function showModal() {
    document.getElementById('day-modal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('day-modal').classList.add('hidden');
    calState.modalStack = [];
}

function handleModalOutsideClick(e) {
    if (e.target === document.getElementById('day-modal')) closeModal();
}

function setModalContent(html) {
    document.getElementById('modal-content').innerHTML = html;
}

function setModalLoading() {
    setModalContent('<div class="text-center py-12 text-gray-400 text-sm">Loading...</div>');
}

// ── Month View ───────────────────────────────────────────────────

async function loadMonth(year, month) {
    document.getElementById('month-grid').innerHTML =
        '<div class="col-span-7 text-center py-8 text-gray-400 text-sm">Loading...</div>';

    const data = await fetchJSON(
        `${ACTIVITY_CONFIG.apiMonth}?year=${year}&month=${month}`
    );
    renderMonthGrid(data);
    document.getElementById('month-title').textContent = data.month_name;
}

function renderMonthGrid(data) {
    const grid = document.getElementById('month-grid');
    grid.innerHTML = '';

    data.weeks.forEach(week => {
        week.forEach(day => {
            const el = document.createElement('div');
            const color = levelColor(day.activity_level);
            const clickable = !['holiday', 'future', 'other_month'].includes(day.activity_level);

            el.className = `rounded-xl p-3 min-h-24 transition ${color} ${clickable ? 'cursor-pointer' : ''}`;

            if (day.is_current_month) {
                let inner = `<div class="text-sm font-bold mb-1">${day.day}</div>`;
                if (!day.is_future && !day.is_sunday) {
                    inner += `
                        <div class="text-xs opacity-75">👥 ${day.unique_users}</div>
                        <div class="text-xs opacity-75">⚡ ${day.total_actions}</div>
                        ${day.suspicious_count > 0
                            ? `<div class="text-xs font-semibold text-red-600">🚨 ${day.suspicious_count}</div>`
                            : ''}
                    `;
                } else if (day.is_sunday) {
                    inner += '<div class="text-xs opacity-50">Sunday</div>';
                }
                el.innerHTML = inner;
            } else {
                el.innerHTML = `<div class="text-sm font-bold opacity-40">${day.day}</div>`;
            }

            if (clickable) {
                el.addEventListener('click', () => openDayModal(day.date));
            }
            grid.appendChild(el);
        });
    });
}

// ── Week View ────────────────────────────────────────────────────

async function loadWeek(startDate) {
    const params = startDate ? `?start_date=${startDate}` : '';
    const data = await fetchJSON(`${ACTIVITY_CONFIG.apiWeek}${params}`);
    calState.weekStart = data.week_start;
    renderWeekGrid(data);
    document.getElementById('week-title').textContent =
        `Week of ${new Date(data.week_start + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}`;
}

function renderWeekGrid(data) {
    const grid = document.getElementById('week-grid');
    grid.innerHTML = '';
    data.days.forEach(day => {
        const isToday = day.date === ACTIVITY_CONFIG.today;
        const el = document.createElement('div');
        el.className = `rounded-xl p-4 text-center ${
            day.is_future ? 'bg-gray-100 text-gray-400'
            : isToday ? 'bg-indigo-100 text-indigo-900 ring-2 ring-indigo-400'
            : 'bg-white border border-gray-200 hover:border-indigo-300 cursor-pointer'
        } transition`;
        el.innerHTML = `
            <div class="text-xs font-semibold text-gray-500 uppercase">${day.day_name}</div>
            <div class="text-2xl font-bold my-1">${day.day_num}</div>
            ${!day.is_future ? `
                <div class="text-xs text-gray-500">👥 ${day.unique_users}</div>
                <div class="text-xs text-gray-500">⚡ ${day.total_actions}</div>
                ${day.suspicious_count > 0
                    ? `<div class="text-xs font-semibold text-red-600 mt-1">🚨 ${day.suspicious_count}</div>`
                    : ''}
            ` : ''}
        `;
        if (!day.is_future) {
            el.addEventListener('click', () => openDayModal(day.date));
        }
        grid.appendChild(el);
    });
}

// ── Day Modal — Level 1 (Day Summary) ──────────────────────────

async function openDayModal(dateStr) {
    showModal();
    setModalLoading();
    calState.modalStack = [{ level: 1, dateStr }];

    try {
        const data = await fetchJSON(
            ACTIVITY_CONFIG.apiDay.replace('__DATE__', dateStr)
        );
        renderLevel1(data, dateStr);
    } catch (e) {
        setModalContent('<div class="text-center py-8 text-red-400">Failed to load. Try again.</div>');
    }
}

function renderLevel1(data, dateStr) {
    const usersHtml = data.users.length === 0
        ? '<p class="text-sm text-gray-400 text-center py-4">No activity on this day.</p>'
        : data.users.map(u => `
            <div class="bg-gray-50 rounded-xl p-4 cursor-pointer hover:bg-indigo-50 hover:ring-1 hover:ring-indigo-300 transition"
                 onclick="openUserDay(${u.user_id}, '${dateStr}')">
                <div class="font-semibold text-gray-900 text-sm">${u.user_display_name}</div>
                <div class="text-xs text-gray-400 mb-2">${formatRole(u.role_snapshot)}</div>
                <div class="grid grid-cols-2 gap-x-2 text-xs text-gray-600">
                    <span>⚡ ${u.total} total</span>
                    <span>✏️ ${u.creates} created</span>
                    <span>🔄 ${u.updates} updated</span>
                    <span>📤 ${u.exports} exported</span>
                    ${u.suspicious > 0
                        ? `<span class="col-span-2 text-red-600 font-semibold">🚨 ${u.suspicious} flagged</span>`
                        : ''}
                </div>
            </div>
        `).join('');

    setModalContent(`
        <div class="flex items-start justify-between mb-5">
            <div>
                <h2 class="text-lg font-bold text-gray-900">${data.date_display}</h2>
                <p class="text-sm text-gray-400">Click a user to see their activity timeline</p>
            </div>
            <button onclick="closeModal()" class="text-gray-300 hover:text-gray-500 text-xl leading-none">✕</button>
        </div>
        <div class="grid grid-cols-3 gap-3 mb-6">
            <div class="bg-blue-50 rounded-xl p-3 text-center">
                <div class="text-2xl font-bold text-blue-700">${data.total_actions || 0}</div>
                <div class="text-xs text-blue-500 mt-1">Total Actions</div>
            </div>
            <div class="bg-green-50 rounded-xl p-3 text-center">
                <div class="text-2xl font-bold text-green-700">${data.total_users || 0}</div>
                <div class="text-xs text-green-500 mt-1">Active Users</div>
            </div>
            <div class="bg-red-50 rounded-xl p-3 text-center">
                <div class="text-2xl font-bold text-red-700">${data.suspicious_total || 0}</div>
                <div class="text-xs text-red-500 mt-1">Flagged</div>
            </div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">${usersHtml}</div>
    `);
}

// ── Day Modal — Level 2 (User Timeline) ────────────────────────

async function openUserDay(userId, dateStr) {
    setModalLoading();
    calState.modalStack.push({ level: 2, userId, dateStr });

    try {
        const url = ACTIVITY_CONFIG.apiUserDay
            .replace('/0/', `/${userId}/`)
            .replace('__DATE__', dateStr);
        const data = await fetchJSON(url);
        calState.cachedUserLogs = {};
        data.logs.forEach(l => { calState.cachedUserLogs[l.id] = l; });
        renderLevel2(data, userId, dateStr);
    } catch (e) {
        setModalContent('<div class="text-center py-8 text-red-400">Failed to load.</div>');
    }
}

function renderLevel2(data, userId, dateStr) {
    const catChips = Object.entries(data.category_counts || {})
        .map(([cat, count]) => `
            <span class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${categoryBadgeClass(cat)}">
                ${cat} <span class="font-bold">${count}</span>
            </span>
        `).join('');

    const timelineHtml = data.logs.length === 0
        ? '<div class="text-center py-4 text-sm text-gray-400">No logs found.</div>'
        : data.logs.map(log => `
            <div class="flex gap-3 py-2.5 border-b border-gray-50 cursor-pointer hover:bg-gray-50 px-2 rounded-lg transition"
                 onclick="openActivityDetail(${log.id})">
                <div class="text-xs text-gray-400 w-16 shrink-0 pt-0.5">${formatTime(log.timestamp)}</div>
                <div class="flex-1 min-w-0">
                    <span class="inline-block px-1.5 py-0.5 rounded text-xs font-medium mr-1 ${categoryBadgeClass(log.action_category)}">
                        ${log.action_category}
                    </span>
                    <span class="text-sm text-gray-800">${log.description}</span>
                    ${log.is_suspicious ? '<span class="ml-1 text-red-500 text-xs">🚨</span>' : ''}
                </div>
            </div>
        `).join('');

    setModalContent(`
        <div class="flex items-center gap-3 mb-4">
            <button onclick="modalBack()" class="text-gray-400 hover:text-gray-700 text-sm">← Back</button>
            <div class="flex-1">
                <h2 class="text-base font-bold text-gray-900">${data.user_display_name}</h2>
                <p class="text-xs text-gray-400">${formatRole(data.role_snapshot)} · ${dateStr}</p>
            </div>
            <button onclick="closeModal()" class="text-gray-300 hover:text-gray-500 text-xl">✕</button>
        </div>
        <div class="flex flex-wrap gap-2 mb-4">${catChips}</div>
        <div class="max-h-96 overflow-y-auto pr-1">${timelineHtml}</div>
    `);
}

// ── Day Modal — Level 3 (Activity Detail) ──────────────────────

function openActivityDetail(logId) {
    const log = calState.cachedUserLogs[logId];
    if (!log) return;
    calState.modalStack.push({ level: 3, logId });
    renderLevel3(log);
}

function renderLevel3(log) {
    const extra = log.extra_data || {};
    const hasOldNew = extra.old && Object.keys(extra.old).length > 0;

    const changesHtml = hasOldNew
        ? Object.entries(extra.old).map(([k, v]) => `
            <tr>
                <td class="py-1.5 pr-4 text-sm font-medium text-gray-500 capitalize">${k.replace(/_/g, ' ')}</td>
                <td class="py-1.5 pr-4 text-sm text-red-500">${v ?? '—'}</td>
                <td class="py-1.5 text-sm text-green-700">${extra.new?.[k] ?? '—'}</td>
            </tr>`).join('')
        : `<tr><td colspan="3" class="py-2 text-sm text-gray-400">No field-level changes recorded</td></tr>`;

    const extraFiltered = Object.entries(extra)
        .filter(([k]) => !['old', 'new'].includes(k));

    setModalContent(`
        <div class="flex items-center gap-3 mb-4">
            <button onclick="modalBack()" class="text-gray-400 hover:text-gray-700 text-sm">← Back</button>
            <h2 class="flex-1 text-base font-bold text-gray-900">Activity Detail</h2>
            <button onclick="closeModal()" class="text-gray-300 hover:text-gray-500 text-xl">✕</button>
        </div>
        <div class="space-y-4">
            <div class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm bg-gray-50 rounded-xl p-4">
                <div class="text-gray-400">Action</div>
                <div class="font-medium">${log.action_type || '—'}</div>
                <div class="text-gray-400">Category</div>
                <div>
                    <span class="inline-block px-2 py-0.5 rounded text-xs font-medium ${categoryBadgeClass(log.action_category)}">
                        ${log.action_category}
                    </span>
                </div>
                <div class="text-gray-400">Module</div>
                <div class="capitalize">${log.module || '—'}</div>
                <div class="text-gray-400">Record</div>
                <div class="text-gray-700">${log.object_repr || '—'}</div>
                <div class="text-gray-400">Time</div>
                <div>${formatDateTime(log.timestamp)}</div>
                <div class="text-gray-400">IP Address</div>
                <div class="font-mono text-xs">${log.ip_address || '—'}</div>
                <div class="text-gray-400">Source</div>
                <div class="capitalize">${log.source || '—'}</div>
                ${log.url_path ? `
                <div class="text-gray-400">URL</div>
                <div class="text-xs font-mono text-gray-600 break-all">${log.url_path}</div>
                ` : ''}
            </div>
            ${hasOldNew ? `
            <div>
                <div class="text-sm font-semibold text-gray-700 mb-2">Field Changes</div>
                <table class="w-full text-sm">
                    <thead>
                        <tr class="text-xs text-gray-400 border-b border-gray-100">
                            <th class="text-left pb-1">Field</th>
                            <th class="text-left pb-1">Before</th>
                            <th class="text-left pb-1">After</th>
                        </tr>
                    </thead>
                    <tbody>${changesHtml}</tbody>
                </table>
            </div>
            ` : ''}
            ${extraFiltered.length > 0 ? `
            <div>
                <div class="text-sm font-semibold text-gray-700 mb-2">Additional Info</div>
                <div class="bg-gray-50 rounded-lg p-3 text-xs font-mono text-gray-600 break-all">
                    ${extraFiltered.map(([k, v]) =>
                        `<div><span class="text-gray-400">${k}:</span> ${JSON.stringify(v)}</div>`
                    ).join('')}
                </div>
            </div>
            ` : ''}
        </div>
    `);
}

// ── Modal back navigation ────────────────────────────────────────

async function modalBack() {
    calState.modalStack.pop();
    const prev = calState.modalStack[calState.modalStack.length - 1];
    if (!prev) { closeModal(); return; }
    if (prev.level === 1) {
        const data = await fetchJSON(
            ACTIVITY_CONFIG.apiDay.replace('__DATE__', prev.dateStr)
        );
        renderLevel1(data, prev.dateStr);
    } else if (prev.level === 2) {
        const url = ACTIVITY_CONFIG.apiUserDay
            .replace('/0/', `/${prev.userId}/`)
            .replace('__DATE__', prev.dateStr);
        const data = await fetchJSON(url);
        renderLevel2(data, prev.userId, prev.dateStr);
    }
}

// ── Tab switching ────────────────────────────────────────────────

function setupTabs() {
    const tabs = {
        'tab-month': 'view-month',
        'tab-week':  'view-week',
        'tab-feed':  'view-feed',
    };

    Object.entries(tabs).forEach(([btnId, viewId]) => {
        document.getElementById(btnId).addEventListener('click', () => {
            Object.values(tabs).forEach(v =>
                document.getElementById(v).classList.add('hidden')
            );
            Object.keys(tabs).forEach(b => {
                const btn = document.getElementById(b);
                btn.classList.remove('text-white', 'bg-indigo-600');
                btn.classList.add('text-gray-600');
            });
            document.getElementById(viewId).classList.remove('hidden');
            const btn = document.getElementById(btnId);
            btn.classList.add('text-white', 'bg-indigo-600');
            btn.classList.remove('text-gray-600');

            if (viewId === 'view-week' && !calState.weekStart) {
                loadWeek(null);
            }
            if (viewId === 'view-feed') {
                window.dispatchEvent(new Event('feed-tab-activated'));
            }
        });
    });
}

// ── Week navigation ──────────────────────────────────────────────

function addDays(dateStr, n) {
    const d = new Date(dateStr + 'T00:00:00');
    d.setDate(d.getDate() + n);
    return d.toISOString().split('T')[0];
}

document.addEventListener('DOMContentLoaded', () => {
    setupTabs();
    loadMonth(calState.year, calState.month);

    document.getElementById('prev-month').addEventListener('click', () => {
        calState.month--;
        if (calState.month < 1) { calState.month = 12; calState.year--; }
        loadMonth(calState.year, calState.month);
    });
    document.getElementById('next-month').addEventListener('click', () => {
        calState.month++;
        if (calState.month > 12) { calState.month = 1; calState.year++; }
        loadMonth(calState.year, calState.month);
    });

    document.getElementById('prev-week').addEventListener('click', () => {
        loadWeek(addDays(calState.weekStart, -7));
    });
    document.getElementById('next-week').addEventListener('click', () => {
        loadWeek(addDays(calState.weekStart, 7));
    });

    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') closeModal();
    });
});
