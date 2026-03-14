# Enterprise Activity Log & Calendar — Design Document

**Date:** 2026-03-08
**Status:** Approved for implementation
**Replaces:** `operations/calendar_utils.py`, `operations/views.py` (calendar views), `templates/operations/calendar_page.html`

---

## 1. Overview

Replace the existing operations-only calendar with an enterprise-grade activity log and calendar system. The new `activity_logs` standalone Django app captures every user action across the ERP, visualizes it as a daily performance calendar, and provides a live activity feed — all with role-based visibility enforcement.

**Goals:**
- Zero data loss — existing operational models untouched
- Minute-level activity logging for all 13 roles
- Role-gated visibility hierarchy
- 1-year retention with monthly PostgreSQL partitioning
- Single URL replacing the old calendar
- Backfill all existing audit model data on migration

---

## 2. Scope

### What Gets Deleted
- `operations/calendar_utils.py`
- Calendar views in `operations/views.py` (lines ~2402–2586)
- `operations/urls.py` calendar routes
- `templates/operations/calendar_page.html`
- `templates/operations/calendar_components/week_widget.html`
- `static/js/calendar.js`

### What Stays Untouched
- `DailySpaceUtilization`, `DisputeLog`, `AdhocBillingEntry`, `WarehouseHoliday` models and all data
- All existing audit models (`DailyEntryAuditLog`, `LRAuditLog`, `QuotationAudit`, `ProjectCodeChangeLog`)
- All dashboards (week widget replaced with new widget)

### What Gets Built
- New Django app: `activity_logs/`
- New model: `ActivityLog` with monthly partitioning
- Middleware, signals, decorators for capture
- Redis write buffer for high-volume writes
- 3-tab UI: Month Calendar, Week View, Activity Feed
- Management commands: partition creation, retention purge, backfill
- Backfill migration from all existing audit models

---

## 3. Data Model

### 3.1 ActivityLog

```python
class ActivityLog(models.Model):
    # Who
    user                = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    user_display_name   = models.CharField(max_length=150)       # snapshot at time of action
    role_snapshot       = models.CharField(max_length=50)        # snapshot — role can change

    # Source
    source              = models.CharField(max_length=20)
    # choices: 'web', 'api', 'cron', 'management_command', 'signal'

    # What
    action_category     = models.CharField(max_length=50)
    # choices: auth, create, update, delete, view, approve, reject,
    #          export, email, system, permission_denied, file_upload,
    #          search, bulk_action

    action_type         = models.CharField(max_length=100)
    # e.g. 'daily_entry_created', 'dispute_status_changed', 'billing_approved'

    module              = models.CharField(max_length=50)
    # e.g. 'operations', 'projects', 'billing', 'accounts', 'supply'

    # Target object
    object_type         = models.CharField(max_length=100, blank=True)
    object_id           = models.IntegerField(null=True, blank=True)
    object_repr         = models.CharField(max_length=255, blank=True)

    # Related object (secondary, e.g. project the object belongs to)
    related_object_type = models.CharField(max_length=100, blank=True)
    related_object_id   = models.IntegerField(null=True, blank=True)

    # Human description
    description         = models.TextField()

    # Request context (nullable for cron/signal sources)
    ip_address          = models.GenericIPAddressField(null=True, blank=True)
    user_agent          = models.CharField(max_length=500, blank=True)
    session_key         = models.CharField(max_length=40, blank=True)
    request_method      = models.CharField(max_length=10, blank=True)
    url_path            = models.CharField(max_length=500, blank=True)
    status_code         = models.IntegerField(null=True, blank=True)
    response_time_ms    = models.IntegerField(null=True, blank=True)

    # Flexible detail payload
    extra_data          = models.JSONField(default=dict, blank=True)
    # stores: old_values/new_values for updates, file names for exports,
    #         email recipients, bulk record IDs, error messages, etc.

    # Flags
    is_suspicious       = models.BooleanField(default=False)
    is_backfilled       = models.BooleanField(default=False)
    backfill_source     = models.CharField(max_length=100, blank=True)
    anonymized          = models.BooleanField(default=False)

    # Time (partition key)
    timestamp           = models.DateTimeField(db_index=True)
    date                = models.DateField(db_index=True)  # computed from timestamp

    class Meta:
        db_table = 'activity_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['date', 'action_category']),
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['module', 'date']),
            models.Index(fields=['is_suspicious', 'date']),
        ]
```

### 3.2 PostgreSQL Monthly Partitioning

The `activity_logs` table is partitioned by `timestamp` range, one partition per month:

```sql
CREATE TABLE activity_logs (
    ...
    timestamp TIMESTAMPTZ NOT NULL
) PARTITION BY RANGE (timestamp);

CREATE TABLE activity_logs_2026_03
    PARTITION OF activity_logs
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

**Management commands:**
- `create_activity_partitions` — creates next 3 months of partitions (run monthly via cron)
- `purge_old_activity_partitions` — drops partitions older than 365 days (run monthly)
- `backfill_activity_logs` — one-time migration from existing audit models

### 3.3 ActivityLogBuffer (Redis)

High-frequency writes go to Redis first, flushed to DB every 5 seconds:

```python
# activity_logs/buffer.py
class ActivityLogBuffer:
    BUFFER_KEY = 'activity_log_buffer'
    FLUSH_INTERVAL = 5  # seconds
    MAX_BUFFER_SIZE = 500  # flush early if buffer exceeds this

    def push(self, log_data: dict): ...
    def flush(self): ...  # bulk_create to DB
    def flush_worker(self): ...  # called by management command / celery beat
```

If Redis is unavailable, falls back to direct DB write — no data loss.

---

## 4. Capture Mechanism

### 4.1 Middleware — `ActivityLogMiddleware`

Captures every HTTP request/response pair:

```python
# activity_logs/middleware.py
class ActivityLogMiddleware:
    def __init__(self, get_response): ...

    def __call__(self, request):
        start_time = time.time()
        response = self.get_response(request)
        elapsed_ms = int((time.time() - start_time) * 1000)

        if self._should_log(request, response):
            self._log(request, response, elapsed_ms)

        return response

    def _should_log(self, request, response):
        # Skip: static files, media, favicon, health checks
        # Skip: GET requests to non-significant pages (list views logged via signals)
        # Always log: POST/PUT/DELETE, auth events, exports, 403s
        ...

    def process_exception(self, request, exception):
        # Log 500 errors to ActivityLog with is_suspicious=True if unusual
        ...
```

**What middleware logs:**
- All POST/PUT/PATCH/DELETE requests
- Login, logout, failed login (via `user_login_failed` signal)
- 403 permission denied responses → `action_category='permission_denied'`
- 500 errors → `action_category='system'`
- Export/download responses (detected by Content-Disposition header)

**What middleware skips:**
- Static/media file requests
- AJAX polling requests (activity feed, sync status bar)
- Health check endpoints

### 4.2 Django Signals — Per-Model Capture

Signals capture the rich "what changed" detail middleware cannot see:

```python
# activity_logs/signals.py

# Operations
@receiver(post_save, sender=DailySpaceUtilization)
def log_daily_entry(sender, instance, created, **kwargs): ...

@receiver(post_save, sender=DisputeLog)
def log_dispute(sender, instance, created, **kwargs): ...

@receiver(post_save, sender=AdhocBillingEntry)
def log_adhoc_billing(sender, instance, created, **kwargs): ...

# Projects
@receiver(post_save, sender=ProjectCode)
def log_project_change(sender, instance, created, **kwargs): ...

@receiver(post_save, sender=ProjectCard)
def log_project_card(sender, instance, created, **kwargs): ...

# Billing
@receiver(post_save, sender=MonthlyBilling)
def log_monthly_billing(sender, instance, created, **kwargs): ...

# Quotations
@receiver(post_save, sender=Quotation)
def log_quotation(sender, instance, created, **kwargs): ...

# Auth
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed

@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs): ...

@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs): ...

@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs): ...
```

**Signal pattern for all model signals:**
```python
def log_daily_entry(sender, instance, created, **kwargs):
    # Get thread-local request context set by middleware
    request = get_current_request()  # via threading.local()

    ActivityLogBuffer.push({
        'user': instance.entered_by,
        'user_display_name': instance.entered_by.get_full_name(),
        'role_snapshot': instance.entered_by.role,
        'source': 'web' if request else 'signal',
        'action_category': 'create' if created else 'update',
        'action_type': 'daily_entry_created' if created else 'daily_entry_updated',
        'module': 'operations',
        'object_type': 'DailySpaceUtilization',
        'object_id': instance.pk,
        'object_repr': f'Daily Entry — {instance.project.project_code} ({instance.entry_date})',
        'related_object_type': 'ProjectCode',
        'related_object_id': instance.project_id,
        'description': f'{"Created" if created else "Updated"} daily entry for {instance.project.project_code}',
        'extra_data': {
            'project_code': instance.project.project_code,
            'entry_date': str(instance.entry_date),
            'space_utilized': str(instance.space_utilized),
            'inventory_value': str(instance.inventory_value),
        },
        'timestamp': timezone.now(),
        'date': timezone.now().date(),
        # request context filled by middleware thread-local
        'ip_address': get_client_ip(request) if request else None,
        'url_path': request.path if request else '',
        'request_method': request.method if request else '',
    })
```

### 4.3 `@log_activity` Decorator

For actions that don't map to a model save (exports, email sends, bulk actions):

```python
# activity_logs/decorators.py

def log_activity(action_category, action_type, module, description_fn=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)
            ActivityLogBuffer.push({
                'user': request.user,
                'action_category': action_category,
                'action_type': action_type,
                'module': module,
                'description': description_fn(request, response) if description_fn else action_type,
                ...
            })
            return response
        return wrapper
    return decorator

# Usage:
@log_activity('export', 'quotation_pdf_exported', 'projects',
              description_fn=lambda req, res: f'Exported PDF for Quotation #{req.resolver_match.kwargs["pk"]}')
def quotation_pdf_view(request, pk): ...
```

### 4.4 Thread-Local Request Context

Signals don't receive the HTTP request. Middleware stores it in thread-local so signals can access it:

```python
# activity_logs/middleware.py
import threading
_thread_locals = threading.local()

def get_current_request():
    return getattr(_thread_locals, 'request', None)

class ActivityLogMiddleware:
    def __call__(self, request):
        _thread_locals.request = request
        try:
            response = self.get_response(request)
        finally:
            _thread_locals.request = None  # always clean up
        return response
```

### 4.5 Cron / Management Command Actions

Background tasks log directly (no HTTP context):

```python
# Inside any management command or cron:
from activity_logs.utils import log_system_action

log_system_action(
    action_type='gmail_leads_sync_completed',
    module='integrations',
    description=f'Gmail leads sync completed — {count} leads imported',
    extra_data={'leads_imported': count, 'duration_ms': elapsed}
)
```

---

## 5. Visibility Layer

### 5.1 Visibility Matrix

```python
# activity_logs/visibility.py

VISIBILITY_MATRIX = {
    'admin':                ['*'],   # all roles
    'super_user':           ['super_user', 'director', 'finance_manager', 'operation_controller',
                             'operation_manager', 'sales_manager', 'supply_manager',
                             'operation_coordinator', 'warehouse_manager', 'backoffice',
                             'crm_executive', 'digital_marketing'],
    'director':             ['*'],   # all roles, read-only
    'operation_controller': ['operation_controller', 'operation_manager',
                             'operation_coordinator', 'warehouse_manager'],
    'operation_manager':    ['operation_manager', 'operation_coordinator', 'warehouse_manager'],
    'finance_manager':      ['self'],
    'sales_manager':        ['self'],
    'supply_manager':       ['self'],
    'operation_coordinator':['self'],
    'warehouse_manager':    ['self'],
    'backoffice':           ['self'],
    'crm_executive':        ['self'],
    'digital_marketing':    ['self'],
}

def get_visible_users(request_user):
    role = request_user.role
    allowed = VISIBILITY_MATRIX.get(role, ['self'])
    if '*' in allowed:
        if role == 'super_user':
            return User.objects.exclude(role='admin')
        return User.objects.all()
    if allowed == ['self']:
        return User.objects.filter(pk=request_user.pk)
    return User.objects.filter(role__in=allowed)

def get_visible_logs(request_user):
    visible_users = get_visible_users(request_user)
    return ActivityLog.objects.filter(user__in=visible_users)
```

All views, all API endpoints call `get_visible_logs(request.user)` — no exceptions.

---

## 6. Backend Views & APIs

### 6.1 URL Structure

```python
# activity_logs/urls.py
app_name = 'activity_logs'

urlpatterns = [
    path('', views.activity_calendar_view, name='calendar'),

    # API endpoints
    path('api/month/',                  views.api_month,        name='api_month'),
    path('api/week/',                   views.api_week,         name='api_week'),
    path('api/day/<str:date_str>/',     views.api_day,          name='api_day'),
    path('api/feed/',                   views.api_feed,         name='api_feed'),
    path('api/user/<int:user_id>/day/<str:date_str>/', views.api_user_day, name='api_user_day'),
]
```

Registered in `minierp/urls.py`:
```python
path('activity/', include('activity_logs.urls', namespace='activity_logs')),
```

Old calendar route in `operations/urls.py` removed.

### 6.2 View: `activity_calendar_view`

```python
@login_required
def activity_calendar_view(request):
    today = timezone.now().date()
    year  = int(request.GET.get('year',  today.year))
    month = int(request.GET.get('month', today.month))
    return render(request, 'activity_logs/calendar.html', {
        'year': year, 'month': month,
        'today': today,
        'user_role': request.user.role,
    })
    # All data loaded via JS → API calls (no server-side calendar computation)
```

### 6.3 API: `api_month`

Returns month grid — one dict per day:

```python
@login_required
def api_month(request):
    year  = int(request.GET.get('year',  today.year))
    month = int(request.GET.get('month', today.month))
    logs  = get_visible_logs(request.user)

    # Single aggregate query across all days of the month
    daily_agg = (
        logs
        .filter(date__year=year, date__month=month)
        .values('date')
        .annotate(
            total_actions=Count('id'),
            unique_users=Count('user_id', distinct=True),
            suspicious_count=Count('id', filter=Q(is_suspicious=True)),
        )
        .order_by('date')
    )

    # Build month grid (list of weeks, each week is list of days)
    ...
    return JsonResponse({'weeks': weeks, 'year': year, 'month': month})
```

### 6.4 API: `api_day`

Returns day summary — list of visible user cards:

```python
@login_required
def api_day(request, date_str):
    date = parse_date(date_str)
    logs = get_visible_logs(request.user).filter(date=date)

    per_user = (
        logs
        .values('user_id', 'user_display_name', 'role_snapshot')
        .annotate(
            total=Count('id'),
            creates=Count('id', filter=Q(action_category='create')),
            updates=Count('id', filter=Q(action_category='update')),
            deletes=Count('id', filter=Q(action_category='delete')),
            exports=Count('id', filter=Q(action_category='export')),
            suspicious=Count('id', filter=Q(is_suspicious=True)),
        )
        .order_by('-total')
    )

    return JsonResponse({
        'date': date_str,
        'date_display': date.strftime('%A, %B %d, %Y'),
        'total_actions': logs.count(),
        'total_users': per_user.count(),
        'users': list(per_user),
    })
```

### 6.5 API: `api_user_day`

Returns single user's timeline for a day (level 2 drill-down):

```python
@login_required
def api_user_day(request, user_id, date_str):
    # Verify request.user can see user_id
    visible = get_visible_users(request.user)
    if not visible.filter(pk=user_id).exists():
        return JsonResponse({'error': 'Not authorized'}, status=403)

    logs = (
        ActivityLog.objects
        .filter(user_id=user_id, date=parse_date(date_str))
        .order_by('timestamp')
        .values('id', 'action_category', 'action_type', 'module',
                'object_repr', 'description', 'timestamp', 'is_suspicious',
                'ip_address', 'extra_data')
    )
    return JsonResponse({'logs': list(logs)})
```

### 6.6 API: `api_feed`

Paginated, reverse-chronological feed (30s polling):

```python
@login_required
def api_feed(request):
    logs = get_visible_logs(request.user)

    # Filters from query params
    user_id   = request.GET.get('user')
    module    = request.GET.get('module')
    category  = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to   = request.GET.get('date_to')
    flagged   = request.GET.get('flagged')
    since_id  = request.GET.get('since_id')   # for polling: only newer than last seen

    if user_id:  logs = logs.filter(user_id=user_id)
    if module:   logs = logs.filter(module=module)
    if category: logs = logs.filter(action_category=category)
    if date_from: logs = logs.filter(date__gte=date_from)
    if date_to:   logs = logs.filter(date__lte=date_to)
    if flagged:   logs = logs.filter(is_suspicious=True)
    if since_id:  logs = logs.filter(id__gt=since_id)  # poll: only new items

    logs = logs.order_by('-timestamp')[:50]  # page size 50

    return JsonResponse({'logs': list(logs.values(...)), 'count': logs.count()})
```

---

## 7. Frontend

### 7.1 Template Structure

```
templates/activity_logs/
    calendar.html           # main page — extends base.html
    components/
        month_grid.html     # Jinja/Django template partial (rendered server-side on first load)
        week_widget.html    # replaces operations/calendar_components/week_widget.html
```

```
static/activity_logs/
    js/
        calendar.js         # month/week tab logic, day modal (3 levels)
        feed.js             # activity feed tab, polling, filters
    css/
        calendar.css        # minimal custom styles (Tailwind-first)
```

### 7.2 `calendar.html` Skeleton

```html
{% extends 'base.html' %}

{% block content %}
<div class="max-w-7xl mx-auto px-4 py-8">

    <!-- Header + Tab switcher -->
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-2xl font-bold text-gray-900">Activity Log</h1>
        <div class="flex gap-2">
            <button id="tab-month" class="tab-btn active">Month</button>
            <button id="tab-week"  class="tab-btn">Week</button>
            <button id="tab-feed"  class="tab-btn">
                Live Feed
                <span id="feed-dot" class="inline-block w-2 h-2 rounded-full bg-green-400 ml-1 animate-pulse"></span>
            </button>
        </div>
    </div>

    <!-- Tab: Month -->
    <div id="view-month">
        <!-- Navigation -->
        <div class="flex items-center justify-between mb-4">
            <button id="prev-month">← Prev</button>
            <h2 id="month-title" class="text-lg font-semibold"></h2>
            <button id="next-month">Next →</button>
        </div>
        <!-- Calendar grid — built by JS -->
        <div id="month-grid" class="grid grid-cols-7 gap-1"></div>
        <!-- Legend -->
        <div class="flex gap-4 mt-4 text-xs text-gray-500">
            <span><span class="inline-block w-3 h-3 rounded bg-green-400 mr-1"></span>High Activity</span>
            <span><span class="inline-block w-3 h-3 rounded bg-yellow-400 mr-1"></span>Partial</span>
            <span><span class="inline-block w-3 h-3 rounded bg-red-400 mr-1"></span>Low / Flagged</span>
            <span><span class="inline-block w-3 h-3 rounded bg-purple-400 mr-1"></span>Holiday</span>
            <span><span class="inline-block w-3 h-3 rounded bg-gray-200 mr-1"></span>Future</span>
        </div>
    </div>

    <!-- Tab: Week -->
    <div id="view-week" class="hidden">
        <div class="flex items-center justify-between mb-4">
            <button id="prev-week">← Prev Week</button>
            <h2 id="week-title" class="text-lg font-semibold"></h2>
            <button id="next-week">Next Week →</button>
        </div>
        <div id="week-grid" class="grid grid-cols-7 gap-2"></div>
    </div>

    <!-- Tab: Feed -->
    <div id="view-feed" class="hidden">
        <!-- Filters bar -->
        <div class="flex flex-wrap gap-3 mb-4">
            <select id="filter-user"     class="filter-select">...</select>
            <select id="filter-module"   class="filter-select">...</select>
            <select id="filter-category" class="filter-select">...</select>
            <input  id="filter-date-from" type="date" class="filter-input">
            <input  id="filter-date-to"   type="date" class="filter-input">
            <label class="flex items-center gap-1">
                <input id="filter-flagged" type="checkbox"> Flagged only
            </label>
            <button id="feed-reset">Reset</button>
        </div>
        <!-- Feed list — built by JS -->
        <div id="feed-list" class="space-y-2"></div>
        <button id="feed-load-more" class="mt-4">Load more...</button>
    </div>

</div>

<!-- Day Modal (3-level, shared) -->
<div id="day-modal" class="hidden fixed inset-0 z-50 ...">
    <div id="modal-content" class="..."></div>
</div>
{% endblock %}

{% block extra_js %}
<script src="{% static 'activity_logs/js/calendar.js' %}"></script>
<script src="{% static 'activity_logs/js/feed.js' %}"></script>
<script>
    const ACTIVITY_CONFIG = {
        apiMonth:   "{% url 'activity_logs:api_month' %}",
        apiWeek:    "{% url 'activity_logs:api_week' %}",
        apiDay:     "{% url 'activity_logs:api_day' date_str='DATE' %}",
        apiUserDay: "{% url 'activity_logs:api_user_day' user_id=0 date_str='DATE' %}",
        apiFeed:    "{% url 'activity_logs:api_feed' %}",
        userRole:   "{{ request.user.role }}",
        today:      "{{ today|date:'Y-m-d' }}",
        year:       {{ year }},
        month:      {{ month }},
    };
</script>
{% endblock %}
```

### 7.3 `calendar.js` — Month & Week Logic

```javascript
// calendar.js

const state = {
    year: ACTIVITY_CONFIG.year,
    month: ACTIVITY_CONFIG.month,
    weekStart: null,        // Monday of current week
    modalLevel: 1,          // 1=day summary, 2=user timeline, 3=activity detail
    modalStack: [],         // for back navigation
};

// ── Month View ──────────────────────────────────────────────

async function loadMonth(year, month) {
    const data = await fetchJSON(`${ACTIVITY_CONFIG.apiMonth}?year=${year}&month=${month}`);
    renderMonthGrid(data);
    document.getElementById('month-title').textContent =
        new Date(year, month - 1).toLocaleString('default', { month: 'long', year: 'numeric' });
}

function renderMonthGrid(data) {
    const grid = document.getElementById('month-grid');
    grid.innerHTML = '';

    // Day headers
    ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].forEach(d => {
        grid.insertAdjacentHTML('beforeend',
            `<div class="text-center text-xs font-semibold text-gray-500 py-2">${d}</div>`);
    });

    // Day cells
    data.weeks.flat().forEach(day => {
        const cell = buildDayCell(day);
        grid.appendChild(cell);
    });
}

function buildDayCell(day) {
    const el = document.createElement('div');
    const colorClass = getDayColor(day);

    el.className = `rounded-xl p-3 min-h-20 cursor-pointer transition hover:shadow-md ${colorClass}`;
    el.dataset.date = day.date;

    if (day.is_current_month && !day.is_future) {
        el.innerHTML = `
            <div class="text-sm font-bold mb-1">${day.day}</div>
            <div class="text-xs opacity-80">👥 ${day.unique_users} users</div>
            <div class="text-xs opacity-80">⚡ ${day.total_actions} acts</div>
            ${day.suspicious_count > 0
                ? `<div class="text-xs text-red-600 font-semibold">🚨 ${day.suspicious_count}</div>`
                : ''}
        `;
        el.addEventListener('click', () => openDayModal(day.date));
    } else {
        el.className = el.className + ' opacity-40 cursor-default';
        el.innerHTML = `<div class="text-sm font-bold">${day.day}</div>`;
    }
    return el;
}

function getDayColor(day) {
    if (day.is_holiday || day.is_sunday) return 'bg-purple-100 text-purple-800';
    if (day.is_future || !day.is_current_month) return 'bg-gray-100 text-gray-400';
    if (day.suspicious_count > 0) return 'bg-red-100 text-red-800';
    if (day.unique_users === 0) return 'bg-red-50 text-red-400';
    if (day.activity_level === 'high') return 'bg-green-100 text-green-800';
    if (day.activity_level === 'medium') return 'bg-yellow-100 text-yellow-800';
    return 'bg-red-100 text-red-700';
}

// Month navigation
document.getElementById('prev-month').addEventListener('click', () => {
    state.month--;
    if (state.month < 1) { state.month = 12; state.year--; }
    loadMonth(state.year, state.month);
});
document.getElementById('next-month').addEventListener('click', () => {
    state.month++;
    if (state.month > 12) { state.month = 1; state.year++; }
    loadMonth(state.year, state.month);
});

// ── Day Modal — 3 Levels ─────────────────────────────────────

async function openDayModal(dateStr) {
    showModal();
    setModalLoading();
    const data = await fetchJSON(`${ACTIVITY_CONFIG.apiDay.replace('DATE', dateStr)}`);
    renderModalLevel1(data, dateStr);
    state.modalStack = [{ level: 1, dateStr }];
}

function renderModalLevel1(data, dateStr) {
    // Summary cards + user grid
    const usersHtml = data.users.map(u => `
        <div class="bg-white rounded-lg p-4 shadow-sm cursor-pointer hover:shadow-md transition"
             onclick="openUserDay(${u.user_id}, '${dateStr}')">
            <div class="font-semibold text-gray-900">${u.user_display_name}</div>
            <div class="text-xs text-gray-500 mb-2">${formatRole(u.role_snapshot)}</div>
            <div class="grid grid-cols-2 gap-1 text-xs">
                <span>⚡ ${u.total} actions</span>
                <span>✏️ ${u.creates} created</span>
                <span>🔄 ${u.updates} updated</span>
                ${u.suspicious > 0
                    ? `<span class="text-red-600 font-semibold">🚨 ${u.suspicious} flagged</span>`
                    : ''}
            </div>
        </div>
    `).join('');

    setModalContent(`
        <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-bold">${data.date_display}</h2>
            <button onclick="closeModal()" class="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <!-- Summary bar -->
        <div class="grid grid-cols-3 gap-3 mb-6">
            <div class="bg-blue-50 rounded-lg p-3 text-center">
                <div class="text-2xl font-bold text-blue-700">${data.total_actions}</div>
                <div class="text-xs text-blue-500">Total Actions</div>
            </div>
            <div class="bg-green-50 rounded-lg p-3 text-center">
                <div class="text-2xl font-bold text-green-700">${data.total_users}</div>
                <div class="text-xs text-green-500">Active Users</div>
            </div>
            <div class="bg-red-50 rounded-lg p-3 text-center">
                <div class="text-2xl font-bold text-red-700">${data.suspicious_total || 0}</div>
                <div class="text-xs text-red-500">Flagged</div>
            </div>
        </div>
        <!-- User cards grid -->
        <div class="grid grid-cols-2 md:grid-cols-3 gap-3">${usersHtml}</div>
    `);
}

async function openUserDay(userId, dateStr) {
    setModalLoading();
    const url = ACTIVITY_CONFIG.apiUserDay
        .replace('0', userId).replace('DATE', dateStr);
    const data = await fetchJSON(url);
    renderModalLevel2(data, userId, dateStr);
    state.modalStack.push({ level: 2, userId, dateStr });
}

function renderModalLevel2(data, userId, dateStr) {
    // Category summary chips + timeline
    const timelineHtml = data.logs.map(log => `
        <div class="flex gap-3 py-2 border-b border-gray-100 cursor-pointer hover:bg-gray-50 px-2 rounded"
             onclick="openActivityDetail(${log.id})">
            <div class="text-xs text-gray-400 w-16 shrink-0 pt-0.5">
                ${formatTime(log.timestamp)}
            </div>
            <div class="flex-1">
                <span class="inline-block px-1.5 py-0.5 rounded text-xs font-medium mr-1 ${getCategoryBadgeClass(log.action_category)}">
                    ${log.action_category}
                </span>
                <span class="text-sm text-gray-800">${log.description}</span>
                ${log.is_suspicious
                    ? '<span class="ml-1 text-red-500 text-xs">🚨</span>'
                    : ''}
            </div>
        </div>
    `).join('');

    setModalContent(`
        <div class="flex items-center gap-2 mb-4">
            <button onclick="modalBack()" class="text-gray-400 hover:text-gray-700">← Back</button>
            <h2 class="text-lg font-bold flex-1">${data.user_display_name}</h2>
            <button onclick="closeModal()" class="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <div class="text-sm text-gray-500 mb-4">${formatRole(data.role_snapshot)} · ${dateStr}</div>
        <!-- Category chips -->
        <div class="flex gap-2 flex-wrap mb-4">
            ${buildCategoryChips(data.category_counts)}
        </div>
        <!-- Timeline -->
        <div class="max-h-96 overflow-y-auto">${timelineHtml}</div>
    `);
}

function openActivityDetail(logId) {
    // Find log in cached data and render level 3
    const log = state.cachedLogs[logId];
    renderModalLevel3(log);
    state.modalStack.push({ level: 3, logId });
}

function renderModalLevel3(log) {
    const changesHtml = log.extra_data?.old
        ? Object.entries(log.extra_data.old).map(([k, v]) => `
            <tr>
                <td class="py-1 pr-4 text-sm font-medium text-gray-600">${k}</td>
                <td class="py-1 pr-4 text-sm text-red-600 line-through">${v}</td>
                <td class="py-1 text-sm text-green-700">${log.extra_data.new?.[k] ?? '—'}</td>
            </tr>`).join('')
        : '<tr><td colspan="3" class="text-sm text-gray-400">No field-level changes recorded</td></tr>';

    setModalContent(`
        <div class="flex items-center gap-2 mb-4">
            <button onclick="modalBack()" class="text-gray-400 hover:text-gray-700">← Back</button>
            <h2 class="text-lg font-bold flex-1">Activity Detail</h2>
            <button onclick="closeModal()" class="text-gray-400 hover:text-gray-600">✕</button>
        </div>
        <div class="space-y-3">
            <div class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <div class="text-gray-500">Action</div>
                <div class="font-medium">${log.action_type}</div>
                <div class="text-gray-500">Module</div>
                <div>${log.module}</div>
                <div class="text-gray-500">Record</div>
                <div>${log.object_repr || '—'}</div>
                <div class="text-gray-500">Time</div>
                <div>${formatDateTime(log.timestamp)}</div>
                <div class="text-gray-500">IP Address</div>
                <div class="font-mono text-xs">${log.ip_address || '—'}</div>
                <div class="text-gray-500">Source</div>
                <div>${log.source}</div>
            </div>
            <!-- Changes table -->
            <div class="mt-4">
                <div class="text-sm font-semibold text-gray-700 mb-2">Changes</div>
                <table class="w-full">
                    <thead>
                        <tr class="text-xs text-gray-400">
                            <th class="text-left py-1">Field</th>
                            <th class="text-left py-1">Before</th>
                            <th class="text-left py-1">After</th>
                        </tr>
                    </thead>
                    <tbody>${changesHtml}</tbody>
                </table>
            </div>
        </div>
    `);
}

function modalBack() {
    state.modalStack.pop();
    const prev = state.modalStack[state.modalStack.length - 1];
    if (prev.level === 1) openDayModal(prev.dateStr);
    else if (prev.level === 2) openUserDay(prev.userId, prev.dateStr);
}

// ── Shared helpers ───────────────────────────────────────────

async function fetchJSON(url) {
    const res = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

function showModal() { document.getElementById('day-modal').classList.remove('hidden'); }
function closeModal() { document.getElementById('day-modal').classList.add('hidden'); }
function setModalLoading() { setModalContent('<div class="text-center py-12 text-gray-400">Loading...</div>'); }
function setModalContent(html) { document.getElementById('modal-content').innerHTML = html; }

// Init
document.addEventListener('DOMContentLoaded', () => {
    loadMonth(state.year, state.month);
    setupTabSwitcher();
});
```

### 7.4 `feed.js` — Activity Feed Logic

```javascript
// feed.js

const feedState = {
    lastId: null,       // for polling: track newest seen ID
    filters: {},
    loading: false,
    allLoaded: false,
};

const POLL_INTERVAL = 30000; // 30 seconds

async function loadFeed(append = false) {
    if (feedState.loading) return;
    feedState.loading = true;

    const params = new URLSearchParams({
        ...feedState.filters,
        ...(append ? { offset: document.querySelectorAll('.feed-item').length } : {}),
    });

    const data = await fetchJSON(`${ACTIVITY_CONFIG.apiFeed}?${params}`);

    if (!append) {
        document.getElementById('feed-list').innerHTML = '';
        feedState.lastId = null;
    }

    renderFeedItems(data.logs, append);

    if (data.logs.length > 0) {
        feedState.lastId = Math.max(...data.logs.map(l => l.id));
    }

    feedState.allLoaded = data.logs.length < 50;
    document.getElementById('feed-load-more').classList.toggle('hidden', feedState.allLoaded);
    feedState.loading = false;
}

async function pollFeed() {
    if (!document.getElementById('view-feed').classList.contains('hidden')) {
        const params = new URLSearchParams({
            ...feedState.filters,
            ...(feedState.lastId ? { since_id: feedState.lastId } : {}),
        });
        const data = await fetchJSON(`${ACTIVITY_CONFIG.apiFeed}?${params}`);
        if (data.logs.length > 0) {
            prependFeedItems(data.logs);
            feedState.lastId = Math.max(...data.logs.map(l => l.id));
            flashNewItems(data.logs.length);
        }
    }
    setTimeout(pollFeed, POLL_INTERVAL);
}

function renderFeedItems(logs, append = false) {
    const list = document.getElementById('feed-list');
    logs.forEach(log => {
        list.insertAdjacentHTML(append ? 'beforeend' : 'afterbegin', buildFeedItem(log));
    });
}

function prependFeedItems(logs) {
    const list = document.getElementById('feed-list');
    [...logs].reverse().forEach(log => {
        const el = document.createElement('div');
        el.innerHTML = buildFeedItem(log);
        el.firstElementChild.classList.add('ring-2', 'ring-blue-300'); // highlight new
        list.prepend(el.firstElementChild);
    });
}

function buildFeedItem(log) {
    const dotColor = log.is_suspicious ? 'bg-red-500'
        : log.action_category === 'create' ? 'bg-green-500'
        : log.action_category === 'delete' ? 'bg-red-400'
        : log.action_category === 'auth' ? 'bg-blue-400'
        : 'bg-yellow-400';

    return `
        <div class="feed-item flex gap-3 p-3 rounded-lg bg-white border border-gray-100 hover:border-gray-200 transition">
            <div class="shrink-0 mt-1.5">
                <span class="inline-block w-2.5 h-2.5 rounded-full ${dotColor}"></span>
            </div>
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                    <span class="font-semibold text-sm text-gray-900">${log.user_display_name}</span>
                    <span class="text-xs text-gray-400">${formatRole(log.role_snapshot)}</span>
                    ${log.is_suspicious ? '<span class="text-xs text-red-600 font-semibold">🚨 Flagged</span>' : ''}
                </div>
                <div class="text-sm text-gray-700">${log.description}</div>
                <div class="text-xs text-gray-400 mt-1">${log.module} · ${timeAgo(log.timestamp)}</div>
            </div>
            <div class="shrink-0 text-xs text-gray-300">${formatTime(log.timestamp)}</div>
        </div>
    `;
}

function flashNewItems(count) {
    // Brief "N new items" banner at top of feed
    const banner = document.createElement('div');
    banner.className = 'text-center text-xs text-blue-600 py-1 animate-pulse';
    banner.textContent = `↑ ${count} new ${count === 1 ? 'activity' : 'activities'}`;
    document.getElementById('feed-list').prepend(banner);
    setTimeout(() => banner.remove(), 3000);
}

// Filters
['filter-user','filter-module','filter-category','filter-flagged'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', () => {
        feedState.filters = getFilters();
        feedState.lastId = null;
        loadFeed();
    });
});

document.getElementById('feed-reset')?.addEventListener('click', () => {
    feedState.filters = {};
    feedState.lastId = null;
    loadFeed();
});

document.getElementById('feed-load-more')?.addEventListener('click', () => loadFeed(true));

// Start polling when feed tab is shown
function onFeedTabActivated() {
    loadFeed();
    setTimeout(pollFeed, POLL_INTERVAL);
}
```

---

## 8. Management Commands

### 8.1 `create_activity_partitions`
```
python manage.py create_activity_partitions --months=3
```
Creates next N months of PostgreSQL partitions. Run monthly via cron.

### 8.2 `purge_old_activity_partitions`
```
python manage.py purge_old_activity_partitions
```
Detaches and drops partitions older than 365 days. Run monthly via cron.

### 8.3 `flush_activity_buffer`
```
python manage.py flush_activity_buffer
```
Flushes Redis write buffer to DB. Run every 5 seconds via cron or Celery Beat.

### 8.4 `backfill_activity_logs`
```
python manage.py backfill_activity_logs --source=all
python manage.py backfill_activity_logs --source=DailyEntryAuditLog
python manage.py backfill_activity_logs --source=LRAuditLog
python manage.py backfill_activity_logs --source=QuotationAudit
python manage.py backfill_activity_logs --source=ProjectCodeChangeLog
```
One-time migration. Sets `is_backfilled=True` and `backfill_source` on all migrated records. Idempotent — safe to re-run.

### 8.5 `anonymize_deleted_user_logs`
```
python manage.py anonymize_deleted_user_logs --user-id=<id>
```
Sets `anonymized=True`, nullifies `user` FK, keeps `user_display_name` as "Deleted User". For GDPR compliance when a user account is deleted.

---

## 9. App Structure

```
activity_logs/
    __init__.py
    apps.py
    models.py               # ActivityLog model
    admin.py                # Admin registration with list_display, filters, search
    middleware.py           # ActivityLogMiddleware + thread-local request context
    signals.py              # post_save / post_delete handlers for all tracked models
    decorators.py           # @log_activity decorator
    visibility.py           # get_visible_users(), get_visible_logs()
    buffer.py               # Redis write buffer + flush logic
    utils.py                # log_system_action(), get_client_ip(), format helpers
    views.py                # calendar_view, api_month, api_week, api_day, api_feed, api_user_day
    urls.py
    migrations/
        0001_initial.py     # ActivityLog model + partitioning setup
        0002_backfill.py    # Data migration from existing audit models
    management/
        commands/
            create_activity_partitions.py
            purge_old_activity_partitions.py
            flush_activity_buffer.py
            backfill_activity_logs.py
            anonymize_deleted_user_logs.py

templates/activity_logs/
    calendar.html
    components/
        week_widget.html    # replaces operations week_widget

static/activity_logs/
    js/
        calendar.js
        feed.js
```

---

## 10. Settings & Integration

### 10.1 `minierp/settings.py` additions

```python
INSTALLED_APPS = [
    ...
    'activity_logs',
]

MIDDLEWARE = [
    ...
    'activity_logs.middleware.ActivityLogMiddleware',   # after SessionMiddleware
]

# Activity log retention
ACTIVITY_LOG_RETENTION_DAYS = 365

# Redis buffer (uses existing CACHES config)
ACTIVITY_LOG_BUFFER_ENABLED = True
ACTIVITY_LOG_BUFFER_FLUSH_INTERVAL = 5   # seconds
ACTIVITY_LOG_BUFFER_MAX_SIZE = 500
```

### 10.2 `minierp/urls.py`

```python
path('activity/', include('activity_logs.urls', namespace='activity_logs')),
```

Remove from `operations/urls.py`:
```python
# DELETE these 3 lines:
path('calendar/', views.calendar_page_view, name='calendar_page'),
path('calendar/day/<str:date_str>/', views.calendar_day_detail_api, name='calendar_day_detail'),
path('calendar/week/', views.calendar_week_api, name='calendar_week'),
```

### 10.3 Navbar Update

Update `components/navbar.html` — replace `/operations/calendar/` link with `/activity/`.

### 10.4 Dashboard Week Widget

All 3 dashboards currently include `calendar_components/week_widget.html`. Replace with:
```django
{% include 'activity_logs/components/week_widget.html' %}
```

---

## 11. Migration Strategy (Zero Data Loss)

### Order of operations in production:

1. **Deploy new app** — `activity_logs` installed, middleware active, signals active. New logs start flowing to `ActivityLog` immediately.
2. **Run partition setup** — `python manage.py create_activity_partitions --months=3`
3. **Run backfill** — `python manage.py backfill_activity_logs --source=all` (historical data migrated)
4. **Verify** — confirm backfill counts match source audit tables
5. **Deploy new URLs** — `/activity/` goes live, old `/operations/calendar/` routes removed
6. **Update navbar** — users redirected to new page
7. **Remove old code** — `calendar_utils.py`, old views, old templates, old JS deleted

Rollback at any step: old calendar code is untouched until step 5. Steps 1–4 are purely additive.

---

## 12. Admin Registration

```python
@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display  = ['timestamp', 'user_display_name', 'role_snapshot', 'action_category',
                     'action_type', 'module', 'object_repr', 'is_suspicious', 'source']
    list_filter   = ['action_category', 'module', 'role_snapshot', 'source',
                     'is_suspicious', 'is_backfilled', 'date']
    search_fields = ['user_display_name', 'description', 'object_repr', 'ip_address']
    readonly_fields = ['timestamp', 'date', 'user', 'user_display_name', 'extra_data',
                       'ip_address', 'user_agent', 'session_key']
    date_hierarchy = 'date'
    ordering = ['-timestamp']

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None):
        return request.user.role == 'admin'
```

---

## 13. Performance Considerations

| Concern | Solution |
|---------|----------|
| High-write peak (20 coordinators simultaneously) | Redis write buffer, bulk_create flush every 5s |
| Month query scanning millions of rows | Monthly partitions — query touches only 1 partition |
| Day modal loading slow | Compound index `(user, date)` + `(date, action_category)` |
| Feed polling 30s from many users | `since_id` filter returns only new rows — minimal scan |
| Backfill blocking production | Backfill command runs in batches of 500, low priority |
| Middleware overhead on every request | Skip list for static/media/polling endpoints |

---

## 14. Security Considerations

| Concern | Solution |
|---------|----------|
| User sees other users' logs | `get_visible_logs()` enforced at every API endpoint |
| Log tampering | Admin: no edit/add permissions; only admin can delete |
| Sensitive data in extra_data | Password fields, tokens never logged (middleware exclusion list) |
| Log poisoning via user input | `object_repr` and `description` built server-side, never from user input directly |
| GDPR user deletion | `anonymize_deleted_user_logs` management command |
