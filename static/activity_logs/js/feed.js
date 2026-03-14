// static/activity_logs/js/feed.js

const feedState = {
    lastId: null,
    loading: false,
    filters: {},
    pollTimer: null,
};

const POLL_INTERVAL = 30000;

// ── Rendering ────────────────────────────────────────────────────

function buildFeedItem(log) {
    const dotColor = log.is_suspicious ? 'bg-red-500'
        : log.action_category === 'create' ? 'bg-green-500'
        : log.action_category === 'delete' ? 'bg-red-400'
        : log.action_category === 'auth' ? 'bg-purple-400'
        : log.action_category === 'approve' ? 'bg-emerald-400'
        : log.action_category === 'export' ? 'bg-yellow-400'
        : 'bg-blue-400';

    const badgeClass = categoryBadgeClass(log.action_category);

    return `
        <div class="feed-item flex gap-3 p-3 rounded-xl bg-white border border-gray-100 hover:border-gray-200 transition">
            <div class="shrink-0 mt-2">
                <span class="inline-block w-2.5 h-2.5 rounded-full ${dotColor}"></span>
            </div>
            <div class="flex-1 min-w-0">
                <div class="flex flex-wrap items-center gap-2 mb-0.5">
                    <span class="font-semibold text-sm text-gray-900">${log.user_display_name}</span>
                    <span class="text-xs text-gray-400">${formatRole(log.role_snapshot)}</span>
                    <span class="inline-block px-1.5 py-0.5 rounded text-xs font-medium ${badgeClass}">
                        ${log.action_category}
                    </span>
                    ${log.is_suspicious
                        ? '<span class="text-xs font-semibold text-red-600">🚨 Flagged</span>'
                        : ''}
                </div>
                <div class="text-sm text-gray-700">${log.description}</div>
                <div class="text-xs text-gray-400 mt-1">
                    ${log.module} · ${timeAgo(log.timestamp)}
                </div>
            </div>
            <div class="shrink-0 text-xs text-gray-300 mt-1">${formatTime(log.timestamp)}</div>
        </div>
    `;
}

// ── Load / Poll ──────────────────────────────────────────────────

async function loadFeed(append = false) {
    if (feedState.loading) return;
    feedState.loading = true;

    const params = new URLSearchParams(feedState.filters);
    if (append) {
        params.set('offset', document.querySelectorAll('.feed-item').length);
    }

    try {
        const data = await fetchJSON(`${ACTIVITY_CONFIG.apiFeed}?${params}`);

        if (!append) {
            document.getElementById('feed-list').innerHTML = '';
        }

        if (data.logs.length === 0 && !append) {
            document.getElementById('feed-empty').classList.remove('hidden');
            document.getElementById('feed-load-more').classList.add('hidden');
        } else {
            document.getElementById('feed-empty').classList.add('hidden');
            const list = document.getElementById('feed-list');
            data.logs.forEach(log => {
                list.insertAdjacentHTML('beforeend', buildFeedItem(log));
            });

            if (data.logs.length > 0) {
                const ids = data.logs.map(l => l.id);
                feedState.lastId = Math.max(...ids);
            }

            document.getElementById('feed-load-more')
                .classList.toggle('hidden', data.logs.length < 50);
        }
    } catch (e) {
        console.error('Feed load failed:', e);
    } finally {
        feedState.loading = false;
    }
}

async function pollFeed() {
    const feedVisible = !document.getElementById('view-feed').classList.contains('hidden');
    if (!feedVisible) return;

    const params = new URLSearchParams(feedState.filters);
    if (feedState.lastId) params.set('since_id', feedState.lastId);

    try {
        const data = await fetchJSON(`${ACTIVITY_CONFIG.apiFeed}?${params}`);
        if (data.logs.length > 0) {
            const list = document.getElementById('feed-list');
            document.getElementById('feed-empty').classList.add('hidden');
            [...data.logs].reverse().forEach(log => {
                const wrapper = document.createElement('div');
                wrapper.innerHTML = buildFeedItem(log);
                const item = wrapper.firstElementChild;
                item.classList.add('ring-2', 'ring-indigo-200');
                list.prepend(item);
                setTimeout(() => item.classList.remove('ring-2', 'ring-indigo-200'), 5000);
            });
            feedState.lastId = Math.max(...data.logs.map(l => l.id));
            showNewBanner(data.logs.length);
        }
    } catch (e) {
        // silent poll failure
    }
}

function showNewBanner(count) {
    const existing = document.getElementById('new-activity-banner');
    if (existing) existing.remove();
    const banner = document.createElement('div');
    banner.id = 'new-activity-banner';
    banner.className = 'text-center text-xs text-indigo-600 bg-indigo-50 rounded-lg py-1.5 mb-2 font-medium';
    banner.textContent = `↑ ${count} new ${count === 1 ? 'activity' : 'activities'}`;
    document.getElementById('feed-list').prepend(banner);
    setTimeout(() => banner.remove(), 4000);
}

// ── Filters ──────────────────────────────────────────────────────

function getFilters() {
    return {
        module:    document.getElementById('filter-module')?.value || '',
        category:  document.getElementById('filter-category')?.value || '',
        date_from: document.getElementById('filter-date-from')?.value || '',
        date_to:   document.getElementById('filter-date-to')?.value || '',
        flagged:   document.getElementById('filter-flagged')?.checked ? '1' : '',
    };
}

function applyFilters() {
    feedState.filters = Object.fromEntries(
        Object.entries(getFilters()).filter(([, v]) => v)
    );
    feedState.lastId = null;
    loadFeed(false);
}

['filter-module', 'filter-category', 'filter-date-from', 'filter-date-to'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', applyFilters);
});
document.getElementById('filter-flagged')?.addEventListener('change', applyFilters);
document.getElementById('feed-reset')?.addEventListener('click', () => {
    document.getElementById('filter-module').value = '';
    document.getElementById('filter-category').value = '';
    document.getElementById('filter-date-from').value = '';
    document.getElementById('filter-date-to').value = '';
    document.getElementById('filter-flagged').checked = false;
    feedState.filters = {};
    feedState.lastId = null;
    loadFeed(false);
});

document.getElementById('feed-load-more')?.addEventListener('click', () => loadFeed(true));

// ── Init ─────────────────────────────────────────────────────────

window.addEventListener('feed-tab-activated', () => {
    if (feedState.lastId === null) loadFeed(false);
    if (!feedState.pollTimer) {
        feedState.pollTimer = setInterval(pollFeed, POLL_INTERVAL);
    }
});
