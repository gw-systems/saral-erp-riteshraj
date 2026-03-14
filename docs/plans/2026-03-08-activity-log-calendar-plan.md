# Enterprise Activity Log & Calendar — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the existing operations-only calendar with a standalone `activity_logs` Django app that logs every user action across all 13 roles, visualizes it as a daily performance calendar, and serves a live activity feed with role-based visibility.

**Architecture:** Standalone `activity_logs` app with an `ActivityLog` model (monthly PostgreSQL partitions, 1-year retention). Capture via middleware (HTTP context) + Django signals (model-level detail) + `@log_activity` decorator (exports/emails). Frontend is a 3-tab page (Month / Week / Activity Feed) at `/activity/` replacing `/operations/calendar/`. Visibility enforced at the query layer via a visibility matrix.

**Tech Stack:** Django 5.2, PostgreSQL (partitioned tables), Tailwind CSS, Vanilla JS (fetch + polling), pytest-django. No Redis — write buffer uses Django's DB cache.

**Key constraint:** No Redis installed. Cache backend is `django.core.cache.backends.db.DatabaseCache`. Buffer strategy: direct `bulk_create` with `ignore_conflicts=True` instead of Redis queue.

---

## Phase 1: App Scaffold & Model

### Task 1: Create the `activity_logs` Django app

**Files:**
- Create: `activity_logs/__init__.py`
- Create: `activity_logs/apps.py`
- Create: `activity_logs/models.py`
- Create: `activity_logs/admin.py`
- Create: `activity_logs/urls.py`
- Create: `activity_logs/views.py`
- Create: `activity_logs/visibility.py`
- Create: `activity_logs/utils.py`
- Create: `activity_logs/middleware.py`
- Create: `activity_logs/signals.py`
- Create: `activity_logs/decorators.py`
- Modify: `minierp/settings.py`
- Modify: `minierp/urls.py`

**Step 1: Create app directory structure**

```bash
mkdir -p activity_logs/management/commands
touch activity_logs/__init__.py
touch activity_logs/apps.py
touch activity_logs/models.py
touch activity_logs/admin.py
touch activity_logs/urls.py
touch activity_logs/views.py
touch activity_logs/visibility.py
touch activity_logs/utils.py
touch activity_logs/middleware.py
touch activity_logs/signals.py
touch activity_logs/decorators.py
touch activity_logs/management/__init__.py
touch activity_logs/management/commands/__init__.py
```

**Step 2: Write `activity_logs/apps.py`**

```python
from django.apps import AppConfig


class ActivityLogsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'activity_logs'
    verbose_name = 'Activity Logs'

    def ready(self):
        import activity_logs.signals  # noqa: F401 — register signal handlers
```

**Step 3: Write `activity_logs/models.py`**

```python
from django.db import models
from django.conf import settings


class ActivityLog(models.Model):
    # Choices
    SOURCE_CHOICES = [
        ('web', 'Web'),
        ('api', 'API'),
        ('cron', 'Cron'),
        ('management_command', 'Management Command'),
        ('signal', 'Signal'),
    ]
    CATEGORY_CHOICES = [
        ('auth', 'Auth'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('view', 'View'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('export', 'Export'),
        ('email', 'Email'),
        ('system', 'System'),
        ('permission_denied', 'Permission Denied'),
        ('file_upload', 'File Upload'),
        ('search', 'Search'),
        ('bulk_action', 'Bulk Action'),
    ]

    # Who
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='activity_logs'
    )
    user_display_name = models.CharField(max_length=150)
    role_snapshot = models.CharField(max_length=50)

    # Source
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='web')

    # What
    action_category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    action_type = models.CharField(max_length=100)
    module = models.CharField(max_length=50)

    # Target object
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.IntegerField(null=True, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)

    # Related object (e.g. project the object belongs to)
    related_object_type = models.CharField(max_length=100, blank=True)
    related_object_id = models.IntegerField(null=True, blank=True)

    # Human description
    description = models.TextField()

    # Request context (nullable for cron/signal sources)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    session_key = models.CharField(max_length=40, blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    url_path = models.CharField(max_length=500, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    response_time_ms = models.IntegerField(null=True, blank=True)

    # Flexible payload (old/new values, file names, etc.)
    extra_data = models.JSONField(default=dict, blank=True)

    # Flags
    is_suspicious = models.BooleanField(default=False)
    is_backfilled = models.BooleanField(default=False)
    backfill_source = models.CharField(max_length=100, blank=True)
    anonymized = models.BooleanField(default=False)

    # Time
    timestamp = models.DateTimeField(db_index=True)
    date = models.DateField(db_index=True)

    class Meta:
        db_table = 'activity_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'date'], name='al_user_date_idx'),
            models.Index(fields=['date', 'action_category'], name='al_date_cat_idx'),
            models.Index(fields=['user', 'timestamp'], name='al_user_ts_idx'),
            models.Index(fields=['module', 'date'], name='al_module_date_idx'),
            models.Index(fields=['is_suspicious', 'date'], name='al_suspicious_idx'),
        ]

    def __str__(self):
        return f'{self.user_display_name} — {self.action_type} @ {self.timestamp}'
```

**Step 4: Register in `minierp/settings.py`**

Add `'activity_logs'` to `INSTALLED_APPS` after `'operations'`:

```python
'activity_logs',
```

Add middleware after `AuthenticationMiddleware`:

```python
'activity_logs.middleware.ActivityLogMiddleware',
```

Add retention setting at bottom of settings:

```python
ACTIVITY_LOG_RETENTION_DAYS = 365
```

**Step 5: Add URL include in `minierp/urls.py`**

```python
path('activity/', include('activity_logs.urls', namespace='activity_logs')),
```

**Step 6: Write minimal `activity_logs/urls.py`**

```python
from django.urls import path
from . import views

app_name = 'activity_logs'

urlpatterns = [
    path('', views.activity_calendar_view, name='calendar'),
    path('api/month/', views.api_month, name='api_month'),
    path('api/week/', views.api_week, name='api_week'),
    path('api/day/<str:date_str>/', views.api_day, name='api_day'),
    path('api/feed/', views.api_feed, name='api_feed'),
    path('api/user/<int:user_id>/day/<str:date_str>/', views.api_user_day, name='api_user_day'),
]
```

**Step 7: Write stub `activity_logs/views.py`**

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone

from .visibility import get_visible_logs


@login_required
def activity_calendar_view(request):
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    return render(request, 'activity_logs/calendar.html', {
        'year': year, 'month': month, 'today': today,
        'user_role': request.user.role,
    })


@login_required
def api_month(request):
    return JsonResponse({'weeks': [], 'year': 2026, 'month': 3})


@login_required
def api_week(request):
    return JsonResponse({'days': []})


@login_required
def api_day(request, date_str):
    return JsonResponse({'date': date_str, 'users': []})


@login_required
def api_feed(request):
    return JsonResponse({'logs': []})


@login_required
def api_user_day(request, user_id, date_str):
    return JsonResponse({'logs': []})
```

**Step 8: Write `activity_logs/visibility.py`**

```python
from django.conf import settings

User = None  # lazy import to avoid circular


def _get_user_model():
    from django.contrib.auth import get_user_model
    return get_user_model()


VISIBILITY_ROLES = {
    'admin': '__all__',
    'super_user': '__all_except_admin__',
    'director': '__all__',
    'operation_controller': ['operation_controller', 'operation_manager',
                             'operation_coordinator', 'warehouse_manager'],
    'operation_manager': ['operation_manager', 'operation_coordinator', 'warehouse_manager'],
    'finance_manager': '__self__',
    'sales_manager': '__self__',
    'supply_manager': '__self__',
    'operation_coordinator': '__self__',
    'warehouse_manager': '__self__',
    'backoffice': '__self__',
    'crm_executive': '__self__',
    'digital_marketing': '__self__',
}


def get_visible_users(request_user):
    User = _get_user_model()
    rule = VISIBILITY_ROLES.get(request_user.role, '__self__')
    if rule == '__all__':
        return User.objects.all()
    if rule == '__all_except_admin__':
        return User.objects.exclude(role='admin')
    if rule == '__self__':
        return User.objects.filter(pk=request_user.pk)
    return User.objects.filter(role__in=rule)


def get_visible_logs(request_user):
    from .models import ActivityLog
    visible_users = get_visible_users(request_user)
    return ActivityLog.objects.filter(user__in=visible_users)
```

**Step 9: Create migration**

```bash
python manage.py makemigrations activity_logs
```

Expected output: `Migrations for 'activity_logs': activity_logs/migrations/0001_initial.py`

**Step 10: Run migration**

```bash
python manage.py migrate activity_logs
```

**Step 11: Verify app loads**

```bash
python manage.py check activity_logs
```

Expected: `System check identified no issues.`

---

### Task 2: PostgreSQL monthly partitioning setup

**Files:**
- Create: `activity_logs/migrations/0002_partition_setup.py`
- Create: `activity_logs/management/commands/create_activity_partitions.py`
- Create: `activity_logs/management/commands/purge_old_activity_partitions.py`

**Step 1: Write `create_activity_partitions` management command**

```python
# activity_logs/management/commands/create_activity_partitions.py
from django.core.management.base import BaseCommand
from django.db import connection
from datetime import date
from dateutil.relativedelta import relativedelta


class Command(BaseCommand):
    help = 'Create monthly PostgreSQL partitions for activity_logs table'

    def add_arguments(self, parser):
        parser.add_argument('--months', type=int, default=3,
                            help='Number of future months to create partitions for')

    def handle(self, *args, **options):
        months_ahead = options['months']
        today = date.today()

        with connection.cursor() as cursor:
            for i in range(months_ahead):
                target = today + relativedelta(months=i)
                start = target.replace(day=1)
                end = start + relativedelta(months=1)

                partition_name = f"activity_logs_{start.strftime('%Y_%m')}"
                start_str = start.strftime('%Y-%m-%d')
                end_str = end.strftime('%Y-%m-%d')

                sql = f"""
                    CREATE TABLE IF NOT EXISTS {partition_name}
                    PARTITION OF activity_logs
                    FOR VALUES FROM ('{start_str} 00:00:00+00') TO ('{end_str} 00:00:00+00');
                """
                try:
                    cursor.execute(sql)
                    self.stdout.write(
                        self.style.SUCCESS(f'Created partition: {partition_name}')
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'Partition {partition_name} may already exist: {e}')
                    )
```

**Step 2: Write `purge_old_activity_partitions` management command**

```python
# activity_logs/management/commands/purge_old_activity_partitions.py
from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
from datetime import date
from dateutil.relativedelta import relativedelta


class Command(BaseCommand):
    help = 'Drop activity_logs partitions older than ACTIVITY_LOG_RETENTION_DAYS'

    def handle(self, *args, **options):
        retention_days = getattr(settings, 'ACTIVITY_LOG_RETENTION_DAYS', 365)
        cutoff = date.today() - relativedelta(days=retention_days)

        with connection.cursor() as cursor:
            # Find partition tables
            cursor.execute("""
                SELECT tablename FROM pg_tables
                WHERE tablename LIKE 'activity_logs_%%'
                AND schemaname = 'public'
                ORDER BY tablename;
            """)
            partitions = [row[0] for row in cursor.fetchall()]

        for partition in partitions:
            # Parse year/month from name: activity_logs_2025_01
            parts = partition.split('_')
            if len(parts) < 4:
                continue
            try:
                year, month = int(parts[-2]), int(parts[-1])
                partition_date = date(year, month, 1)
            except (ValueError, IndexError):
                continue

            if partition_date < cutoff.replace(day=1):
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP TABLE IF EXISTS {partition};')
                self.stdout.write(
                    self.style.SUCCESS(f'Dropped old partition: {partition}')
                )
```

**Step 3: Write data migration `0002_partition_setup.py` to convert table to partitioned**

```python
# activity_logs/migrations/0002_partition_setup.py
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('activity_logs', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- Convert activity_logs to partitioned table
            -- 1. Rename existing table
            ALTER TABLE activity_logs RENAME TO activity_logs_unpartitioned;

            -- 2. Create partitioned parent table
            CREATE TABLE activity_logs (
                LIKE activity_logs_unpartitioned INCLUDING ALL
            ) PARTITION BY RANGE (timestamp);

            -- 3. Create initial partitions (current month + next 2)
            CREATE TABLE activity_logs_2026_03
                PARTITION OF activity_logs
                FOR VALUES FROM ('2026-03-01 00:00:00+00') TO ('2026-04-01 00:00:00+00');

            CREATE TABLE activity_logs_2026_04
                PARTITION OF activity_logs
                FOR VALUES FROM ('2026-04-01 00:00:00+00') TO ('2026-05-01 00:00:00+00');

            CREATE TABLE activity_logs_2026_05
                PARTITION OF activity_logs
                FOR VALUES FROM ('2026-05-01 00:00:00+00') TO ('2026-06-01 00:00:00+00');

            -- 4. Migrate any existing data
            INSERT INTO activity_logs SELECT * FROM activity_logs_unpartitioned;

            -- 5. Drop old table
            DROP TABLE activity_logs_unpartitioned;
            """,
            reverse_sql="""
            -- Reverse: merge partitions back to single table (data preserved)
            CREATE TABLE activity_logs_plain (LIKE activity_logs INCLUDING ALL);
            INSERT INTO activity_logs_plain SELECT * FROM activity_logs;
            DROP TABLE activity_logs CASCADE;
            ALTER TABLE activity_logs_plain RENAME TO activity_logs;
            """,
        ),
    ]
```

**Step 4: Run migration**

```bash
python manage.py migrate activity_logs 0002
```

**Step 5: Verify partitioning**

```bash
python manage.py dbshell
```

```sql
\d+ activity_logs
-- Expected: "Partitioned table" in output
\q
```

---

## Phase 2: Capture Infrastructure

### Task 3: Middleware — HTTP request context capture

**Files:**
- Modify: `activity_logs/middleware.py`

**Step 1: Write the middleware**

```python
# activity_logs/middleware.py
import threading
import time

_thread_locals = threading.local()


def get_current_request():
    """Get HTTP request stored by middleware. Returns None for cron/signal sources."""
    return getattr(_thread_locals, 'request', None)


def get_client_ip(request):
    """Extract real IP handling proxies."""
    if not request:
        return None
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


# URLs to skip — never log these
SKIP_PREFIXES = (
    '/static/', '/media/', '/favicon',
    '/activity/api/feed/',      # feed polling — too noisy
    '/activity/api/month/',     # calendar API — read-only
    '/activity/api/week/',
    '/health', '/__debug__',
)

SKIP_EXTENSIONS = ('.js', '.css', '.png', '.jpg', '.ico', '.woff', '.woff2', '.map')


class ActivityLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store request in thread-local so signals can access it
        _thread_locals.request = request
        _thread_locals.request_start = time.time()

        try:
            response = self.get_response(request)
        except Exception:
            _thread_locals.request = None
            raise

        elapsed_ms = int((time.time() - _thread_locals.request_start) * 1000)

        try:
            if self._should_log(request, response):
                self._log_request(request, response, elapsed_ms)
        except Exception:
            pass  # never let logging crash the response

        _thread_locals.request = None
        return response

    def process_exception(self, request, exception):
        """Log unhandled 500 errors."""
        try:
            from .utils import log_activity_direct
            log_activity_direct(
                user=getattr(request, 'user', None),
                source='web',
                action_category='system',
                action_type='unhandled_exception',
                module='system',
                description=f'Unhandled exception: {type(exception).__name__}: {str(exception)[:200]}',
                request=request,
                is_suspicious=True,
                extra_data={'exception_type': type(exception).__name__,
                            'exception_msg': str(exception)[:500]},
            )
        except Exception:
            pass

    def _should_log(self, request, response):
        path = request.path

        # Skip static/media/polling
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return False
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            return False

        # Skip anonymous users (not logged in)
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            # Still log failed logins (handled by auth signal)
            return False

        # Always log state-changing requests
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return True

        # Log permission denied
        if response.status_code == 403:
            return True

        # Skip GET requests (model signals handle the interesting ones)
        return False

    def _log_request(self, request, response, elapsed_ms):
        from .utils import log_activity_direct

        # Determine category from response
        if response.status_code == 403:
            category = 'permission_denied'
            action_type = 'access_denied'
        elif request.method == 'DELETE':
            category = 'delete'
            action_type = 'record_deleted'
        elif request.method == 'POST':
            category = 'create'
            action_type = 'form_submitted'
        else:
            category = 'update'
            action_type = 'record_updated'

        # Check for file download (export)
        content_disp = response.get('Content-Disposition', '')
        if 'attachment' in content_disp:
            category = 'export'
            action_type = 'file_downloaded'

        log_activity_direct(
            user=request.user,
            source='web',
            action_category=category,
            action_type=action_type,
            module=_guess_module(request.path),
            description=f'{request.method} {request.path}',
            request=request,
            extra_data={
                'content_disposition': content_disp[:200] if content_disp else '',
            },
            status_code=response.status_code,
            response_time_ms=elapsed_ms,
        )


def _guess_module(path):
    """Infer module name from URL path."""
    parts = path.strip('/').split('/')
    if not parts or not parts[0]:
        return 'unknown'
    mapping = {
        'activity': 'activity_logs',
        'operations': 'operations',
        'projects': 'projects',
        'accounts': 'accounts',
        'supply': 'supply',
        'integrations': 'integrations',
        'billing': 'billing',
    }
    return mapping.get(parts[0], parts[0])
```

---

### Task 4: `utils.py` — core logging helper

**Files:**
- Modify: `activity_logs/utils.py`

**Step 1: Write `activity_logs/utils.py`**

```python
# activity_logs/utils.py
from django.utils import timezone


def log_activity_direct(
    *,
    user,
    source,
    action_category,
    action_type,
    module,
    description,
    request=None,
    object_type='',
    object_id=None,
    object_repr='',
    related_object_type='',
    related_object_id=None,
    extra_data=None,
    is_suspicious=False,
    status_code=None,
    response_time_ms=None,
):
    """
    Core function to create an ActivityLog entry.
    Safe to call from signals, middleware, management commands.
    Never raises — errors are swallowed to avoid breaking the main request.
    """
    from .models import ActivityLog
    from .middleware import get_client_ip

    try:
        now = timezone.now()

        # Resolve user display info
        if user and user.is_authenticated:
            user_display = user.get_full_name() or user.username
            role = getattr(user, 'role', 'unknown')
            user_obj = user
        else:
            user_display = 'Anonymous'
            role = 'anonymous'
            user_obj = None

        # Request context
        ip = None
        ua = ''
        session_key = ''
        method = ''
        path = ''

        if request:
            ip = get_client_ip(request)
            ua = request.META.get('HTTP_USER_AGENT', '')[:500]
            session_key = request.session.session_key or ''
            method = request.method
            path = request.path

        ActivityLog.objects.create(
            user=user_obj,
            user_display_name=user_display,
            role_snapshot=role,
            source=source,
            action_category=action_category,
            action_type=action_type,
            module=module,
            object_type=object_type,
            object_id=object_id,
            object_repr=object_repr,
            related_object_type=related_object_type,
            related_object_id=related_object_id,
            description=description,
            ip_address=ip,
            user_agent=ua,
            session_key=session_key,
            request_method=method,
            url_path=path,
            status_code=status_code,
            response_time_ms=response_time_ms,
            extra_data=extra_data or {},
            is_suspicious=is_suspicious,
            timestamp=now,
            date=now.date(),
        )
    except Exception:
        pass  # logging must never crash the caller


def log_system_action(*, action_type, module, description, extra_data=None):
    """Convenience for cron/management command logging (no user, no request)."""
    from .models import ActivityLog

    now = timezone.now()
    try:
        ActivityLog.objects.create(
            user=None,
            user_display_name='System',
            role_snapshot='system',
            source='cron',
            action_category='system',
            action_type=action_type,
            module=module,
            description=description,
            extra_data=extra_data or {},
            timestamp=now,
            date=now.date(),
        )
    except Exception:
        pass
```

---

### Task 5: Django signals — model-level capture

**Files:**
- Modify: `activity_logs/signals.py`

**Step 1: Write signal handlers for all key models**

```python
# activity_logs/signals.py
from django.db.models.signals import post_save, post_delete
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone

from .utils import log_activity_direct
from .middleware import get_current_request


# ── Auth signals ─────────────────────────────────────────────────────────────

@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    log_activity_direct(
        user=user, source='web',
        action_category='auth', action_type='login',
        module='accounts', description=f'{user.get_full_name() or user.username} logged in',
        request=request,
    )


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user:
        log_activity_direct(
            user=user, source='web',
            action_category='auth', action_type='logout',
            module='accounts', description=f'{user.get_full_name() or user.username} logged out',
            request=request,
        )


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    from .models import ActivityLog
    from .middleware import get_client_ip
    from django.contrib.auth import get_user_model
    User = get_user_model()

    username_tried = credentials.get('username', '')
    now = timezone.now()
    try:
        ActivityLog.objects.create(
            user=None,
            user_display_name=f'Failed login: {username_tried}',
            role_snapshot='anonymous',
            source='web',
            action_category='auth',
            action_type='login_failed',
            module='accounts',
            description=f'Failed login attempt for username: {username_tried}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            url_path=request.path,
            request_method=request.method,
            extra_data={'username_tried': username_tried},
            is_suspicious=True,
            timestamp=now,
            date=now.date(),
        )
    except Exception:
        pass


# ── Operations signals ────────────────────────────────────────────────────────

def _log_model(*, instance, created, action_type_create, action_type_update,
               module, object_type, object_repr_fn, description_fn,
               user_field='entered_by', extra_data_fn=None,
               related_type='', related_id_fn=None):
    """Generic helper to log a model post_save."""
    request = get_current_request()
    user = getattr(instance, user_field, None)
    if user is None:
        user = getattr(instance, 'created_by', None)
    if user is None:
        user = getattr(instance, 'raised_by', None)

    action_type = action_type_create if created else action_type_update
    category = 'create' if created else 'update'

    extra = extra_data_fn(instance) if extra_data_fn else {}
    related_id = related_id_fn(instance) if related_id_fn else None

    log_activity_direct(
        user=user,
        source='web' if request else 'signal',
        action_category=category,
        action_type=action_type,
        module=module,
        object_type=object_type,
        object_id=instance.pk,
        object_repr=object_repr_fn(instance),
        related_object_type=related_type,
        related_object_id=related_id,
        description=description_fn(instance, created),
        request=request,
        extra_data=extra,
    )


try:
    from operations.models import DailySpaceUtilization

    @receiver(post_save, sender=DailySpaceUtilization)
    def log_daily_entry(sender, instance, created, **kwargs):
        _log_model(
            instance=instance, created=created,
            action_type_create='daily_entry_created',
            action_type_update='daily_entry_updated',
            module='operations',
            object_type='DailySpaceUtilization',
            object_repr_fn=lambda i: f'Daily Entry — {i.project.project_code} ({i.entry_date})',
            description_fn=lambda i, c: (
                f'{"Created" if c else "Updated"} daily entry for {i.project.project_code} on {i.entry_date}'
            ),
            user_field='entered_by',
            related_type='ProjectCode',
            related_id_fn=lambda i: i.project_id,
            extra_data_fn=lambda i: {
                'project_code': i.project.project_code,
                'entry_date': str(i.entry_date),
                'space_utilized': str(i.space_utilized),
                'inventory_value': str(i.inventory_value),
            },
        )
except ImportError:
    pass


try:
    from operations.models import DisputeLog

    @receiver(post_save, sender=DisputeLog)
    def log_dispute(sender, instance, created, **kwargs):
        _log_model(
            instance=instance, created=created,
            action_type_create='dispute_raised',
            action_type_update='dispute_updated',
            module='operations',
            object_type='DisputeLog',
            object_repr_fn=lambda i: f'Dispute — {i.title or i.pk}',
            description_fn=lambda i, c: (
                f'{"Raised" if c else "Updated"} dispute: {i.title or i.pk}'
            ),
            user_field='raised_by',
            related_type='ProjectCode',
            related_id_fn=lambda i: i.project_id,
            extra_data_fn=lambda i: {
                'project_code': i.project.project_code if i.project_id else '',
                'status': str(i.status) if i.status_id else '',
                'priority': str(i.priority) if i.priority_id else '',
            },
        )
except ImportError:
    pass


try:
    from operations.models_adhoc import AdhocBillingEntry

    @receiver(post_save, sender=AdhocBillingEntry)
    def log_adhoc_billing(sender, instance, created, **kwargs):
        _log_model(
            instance=instance, created=created,
            action_type_create='adhoc_billing_created',
            action_type_update='adhoc_billing_updated',
            module='operations',
            object_type='AdhocBillingEntry',
            object_repr_fn=lambda i: f'Adhoc Billing — {i.project.project_code} ({i.event_date})',
            description_fn=lambda i, c: (
                f'{"Created" if c else "Updated"} adhoc billing for {i.project.project_code}'
            ),
            user_field='created_by',
            related_type='ProjectCode',
            related_id_fn=lambda i: i.project_id,
            extra_data_fn=lambda i: {
                'project_code': i.project.project_code,
                'event_date': str(i.event_date),
                'total_client_amount': str(i.total_client_amount or 0),
            },
        )
except ImportError:
    pass


# ── Projects signals ──────────────────────────────────────────────────────────

try:
    from projects.models import ProjectCode

    @receiver(post_save, sender=ProjectCode)
    def log_project(sender, instance, created, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='project_created' if created else 'project_updated',
            module='projects',
            object_type='ProjectCode',
            object_id=instance.pk,
            object_repr=f'Project — {instance.project_code}',
            description=f'{"Created" if created else "Updated"} project {instance.project_code}',
            request=request,
            extra_data={
                'project_code': instance.project_code,
                'status': instance.status if hasattr(instance, 'status') else '',
            },
        )
except ImportError:
    pass


# ── Quotation signals ─────────────────────────────────────────────────────────

try:
    from projects.models_quotation import Quotation

    @receiver(post_save, sender=Quotation)
    def log_quotation(sender, instance, created, **kwargs):
        request = get_current_request()
        user = request.user if request and request.user.is_authenticated else None
        log_activity_direct(
            user=user,
            source='web' if request else 'signal',
            action_category='create' if created else 'update',
            action_type='quotation_created' if created else 'quotation_updated',
            module='projects',
            object_type='Quotation',
            object_id=instance.pk,
            object_repr=f'Quotation — {instance.quotation_number if hasattr(instance, "quotation_number") else instance.pk}',
            description=f'{"Created" if created else "Updated"} quotation {instance.pk}',
            request=request,
        )
except ImportError:
    pass
```

---

### Task 6: `@log_activity` decorator for explicit actions

**Files:**
- Modify: `activity_logs/decorators.py`

**Step 1: Write the decorator**

```python
# activity_logs/decorators.py
from functools import wraps
from .utils import log_activity_direct


def log_activity(action_category, action_type, module, description_fn=None, extra_data_fn=None):
    """
    Decorator to log a view action.

    Usage:
        @log_activity('export', 'quotation_pdf', 'projects',
                      description_fn=lambda req, kw: f'Exported PDF for quotation {kw["pk"]}')
        def quotation_pdf_view(request, pk):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)

            # Only log successful responses
            if response.status_code < 400:
                desc = (
                    description_fn(request, kwargs)
                    if description_fn
                    else f'{action_category}: {action_type}'
                )
                extra = extra_data_fn(request, kwargs) if extra_data_fn else {}

                log_activity_direct(
                    user=request.user,
                    source='web',
                    action_category=action_category,
                    action_type=action_type,
                    module=module,
                    description=desc,
                    request=request,
                    extra_data=extra,
                    status_code=response.status_code,
                )
            return response
        return wrapper
    return decorator
```

---

## Phase 3: Admin Registration

### Task 7: Register ActivityLog in Django admin

**Files:**
- Modify: `activity_logs/admin.py`

**Step 1: Write admin**

```python
# activity_logs/admin.py
from django.contrib import admin
from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = [
        'timestamp', 'user_display_name', 'role_snapshot',
        'action_category', 'action_type', 'module',
        'object_repr', 'is_suspicious', 'source',
    ]
    list_filter = [
        'action_category', 'module', 'role_snapshot',
        'source', 'is_suspicious', 'is_backfilled', 'date',
    ]
    search_fields = ['user_display_name', 'description', 'object_repr', 'ip_address']
    readonly_fields = [
        'timestamp', 'date', 'user', 'user_display_name', 'role_snapshot',
        'extra_data', 'ip_address', 'user_agent', 'session_key',
        'action_category', 'action_type', 'module', 'source',
        'object_type', 'object_id', 'object_repr', 'description',
        'is_backfilled', 'backfill_source', 'is_suspicious', 'anonymized',
    ]
    date_hierarchy = 'date'
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.role == 'admin'
```

---

## Phase 4: Backend API Views

### Task 8: Implement all API views

**Files:**
- Modify: `activity_logs/views.py`

**Step 1: Write full `views.py`**

```python
# activity_logs/views.py
import calendar as cal
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import ActivityLog
from .visibility import get_visible_logs, get_visible_users


@login_required
def activity_calendar_view(request):
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    return render(request, 'activity_logs/calendar.html', {
        'year': year, 'month': month, 'today': today,
        'user_role': request.user.role,
    })


@login_required
def api_month(request):
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    logs = get_visible_logs(request.user)

    # Single aggregate query for the whole month
    daily_agg = {
        row['date']: row
        for row in logs.filter(date__year=year, date__month=month)
        .values('date')
        .annotate(
            total_actions=Count('id'),
            unique_users=Count('user_id', distinct=True),
            suspicious_count=Count('id', filter=Q(is_suspicious=True)),
        )
    }

    # Build weeks grid
    cal_obj = cal.Calendar(firstweekday=0)  # Monday first
    weeks = []
    for week in cal_obj.monthdatescalendar(year, month):
        week_data = []
        for d in week:
            agg = daily_agg.get(d, {})
            total = agg.get('total_actions', 0)
            users = agg.get('unique_users', 0)
            suspicious = agg.get('suspicious_count', 0)

            if d.weekday() == 6:  # Sunday
                level = 'holiday'
            elif d > today:
                level = 'future'
            elif d.month != month:
                level = 'other_month'
            elif total == 0:
                level = 'none'
            elif users >= 5:
                level = 'high'
            elif users >= 2:
                level = 'medium'
            else:
                level = 'low'

            week_data.append({
                'date': d.isoformat(),
                'day': d.day,
                'is_current_month': d.month == month,
                'is_future': d > today,
                'is_sunday': d.weekday() == 6,
                'total_actions': total,
                'unique_users': users,
                'suspicious_count': suspicious,
                'activity_level': level,
            })
        weeks.append(week_data)

    return JsonResponse({
        'year': year, 'month': month,
        'month_name': date(year, month, 1).strftime('%B %Y'),
        'weeks': weeks,
    })


@login_required
def api_week(request):
    today = timezone.now().date()
    start_str = request.GET.get('start_date')

    if start_str:
        start = parse_date(start_str)
        if not start:
            start = today - timedelta(days=today.weekday())
    else:
        start = today - timedelta(days=today.weekday())  # Monday

    logs = get_visible_logs(request.user)
    days = []

    for i in range(7):
        d = start + timedelta(days=i)
        agg = logs.filter(date=d).aggregate(
            total_actions=Count('id'),
            unique_users=Count('user_id', distinct=True),
            suspicious_count=Count('id', filter=Q(is_suspicious=True)),
        )
        days.append({
            'date': d.isoformat(),
            'day_name': d.strftime('%a'),
            'day_num': d.day,
            'is_today': d == today,
            'is_future': d > today,
            **agg,
        })

    return JsonResponse({
        'week_start': start.isoformat(),
        'week_end': (start + timedelta(days=6)).isoformat(),
        'days': days,
    })


@login_required
def api_day(request, date_str):
    d = parse_date(date_str)
    if not d:
        return JsonResponse({'error': 'Invalid date'}, status=400)

    logs = get_visible_logs(request.user).filter(date=d)

    per_user = list(
        logs.values('user_id', 'user_display_name', 'role_snapshot')
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

    totals = logs.aggregate(
        total_actions=Count('id'),
        total_users=Count('user_id', distinct=True),
        suspicious_total=Count('id', filter=Q(is_suspicious=True)),
    )

    return JsonResponse({
        'date': date_str,
        'date_display': d.strftime('%A, %B %d, %Y'),
        **totals,
        'users': per_user,
    })


@login_required
def api_user_day(request, user_id, date_str):
    # Verify caller can see this user
    visible = get_visible_users(request.user)
    if not visible.filter(pk=user_id).exists():
        return JsonResponse({'error': 'Not authorized'}, status=403)

    d = parse_date(date_str)
    if not d:
        return JsonResponse({'error': 'Invalid date'}, status=400)

    logs = list(
        ActivityLog.objects.filter(user_id=user_id, date=d)
        .order_by('timestamp')
        .values(
            'id', 'action_category', 'action_type', 'module',
            'object_type', 'object_repr', 'description',
            'timestamp', 'is_suspicious', 'ip_address',
            'extra_data', 'source', 'url_path',
        )
    )

    # Category summary
    from django.db.models import Count, Q
    cat_counts = dict(
        ActivityLog.objects.filter(user_id=user_id, date=d)
        .values('action_category')
        .annotate(count=Count('id'))
        .values_list('action_category', 'count')
    )

    # Get user info from first log
    user_info = {}
    if logs:
        user_info = {
            'user_display_name': logs[0].get('user_display_name', ''),
            'role_snapshot': logs[0].get('role_snapshot', ''),
        }
    else:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            u = User.objects.get(pk=user_id)
            user_info = {
                'user_display_name': u.get_full_name() or u.username,
                'role_snapshot': u.role,
            }
        except User.DoesNotExist:
            user_info = {'user_display_name': 'Unknown', 'role_snapshot': ''}

    # Serialize timestamps
    for log in logs:
        if log.get('timestamp'):
            log['timestamp'] = log['timestamp'].isoformat()

    return JsonResponse({
        'date': date_str,
        **user_info,
        'category_counts': cat_counts,
        'logs': logs,
    })


@login_required
def api_feed(request):
    logs = get_visible_logs(request.user)

    # Filters
    user_id = request.GET.get('user')
    module = request.GET.get('module')
    category = request.GET.get('category')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    flagged = request.GET.get('flagged')
    since_id = request.GET.get('since_id')
    offset = int(request.GET.get('offset', 0))

    if user_id:
        logs = logs.filter(user_id=user_id)
    if module:
        logs = logs.filter(module=module)
    if category:
        logs = logs.filter(action_category=category)
    if date_from:
        logs = logs.filter(date__gte=date_from)
    if date_to:
        logs = logs.filter(date__lte=date_to)
    if flagged:
        logs = logs.filter(is_suspicious=True)
    if since_id:
        logs = logs.filter(id__gt=int(since_id))

    page = list(
        logs.order_by('-timestamp')[offset:offset + 50]
        .values(
            'id', 'user_id', 'user_display_name', 'role_snapshot',
            'action_category', 'action_type', 'module',
            'object_repr', 'description', 'timestamp',
            'is_suspicious', 'source',
        )
    )

    for log in page:
        if log.get('timestamp'):
            log['timestamp'] = log['timestamp'].isoformat()

    return JsonResponse({'logs': page, 'count': len(page)})
```

---

## Phase 5: Frontend

### Task 9: Create templates and static files

**Files:**
- Create: `templates/activity_logs/calendar.html`
- Create: `templates/activity_logs/components/week_widget.html`
- Create: `static/activity_logs/js/calendar.js`
- Create: `static/activity_logs/js/feed.js`

**Step 1: Create directories**

```bash
mkdir -p templates/activity_logs/components
mkdir -p static/activity_logs/js
```

**Step 2: Write `templates/activity_logs/calendar.html`**

```html
{% extends 'base.html' %}
{% load static %}

{% block title %}Activity Log — {{ APP_FULL_NAME }}{% endblock %}

{% block content %}
<div class="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
        <div>
            <h1 class="text-2xl font-bold text-gray-900">Activity Log</h1>
            <p class="text-sm text-gray-500 mt-1">Daily performance across all users</p>
        </div>
        <div class="flex rounded-lg overflow-hidden border border-gray-200 bg-white shadow-sm">
            <button id="tab-month"
                class="tab-btn px-4 py-2 text-sm font-medium text-white bg-indigo-600">
                Month
            </button>
            <button id="tab-week"
                class="tab-btn px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50">
                Week
            </button>
            <button id="tab-feed"
                class="tab-btn px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 flex items-center gap-1">
                Live Feed
                <span class="inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
            </button>
        </div>
    </div>

    <!-- ── Month View ─────────────────────────────────────────── -->
    <div id="view-month">
        <div class="flex items-center justify-between mb-4">
            <button id="prev-month"
                class="px-3 py-1.5 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
                ← Prev
            </button>
            <h2 id="month-title" class="text-lg font-semibold text-gray-800"></h2>
            <button id="next-month"
                class="px-3 py-1.5 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
                Next →
            </button>
        </div>

        <!-- Grid header -->
        <div class="grid grid-cols-7 gap-1 mb-1">
            {% for day in "Mon,Tue,Wed,Thu,Fri,Sat,Sun"|split:"," %}
            <div class="text-center text-xs font-semibold text-gray-400 py-2">{{ day }}</div>
            {% endfor %}
        </div>

        <!-- Calendar cells — built by JS -->
        <div id="month-grid" class="grid grid-cols-7 gap-1"></div>

        <!-- Legend -->
        <div class="flex flex-wrap gap-4 mt-4 text-xs text-gray-500">
            <span class="flex items-center gap-1">
                <span class="inline-block w-3 h-3 rounded bg-green-200"></span>High Activity
            </span>
            <span class="flex items-center gap-1">
                <span class="inline-block w-3 h-3 rounded bg-yellow-200"></span>Moderate
            </span>
            <span class="flex items-center gap-1">
                <span class="inline-block w-3 h-3 rounded bg-red-200"></span>Low / Flagged
            </span>
            <span class="flex items-center gap-1">
                <span class="inline-block w-3 h-3 rounded bg-purple-200"></span>Holiday / Sunday
            </span>
            <span class="flex items-center gap-1">
                <span class="inline-block w-3 h-3 rounded bg-gray-100"></span>Future / Other month
            </span>
        </div>
    </div>

    <!-- ── Week View ──────────────────────────────────────────── -->
    <div id="view-week" class="hidden">
        <div class="flex items-center justify-between mb-4">
            <button id="prev-week"
                class="px-3 py-1.5 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
                ← Prev Week
            </button>
            <h2 id="week-title" class="text-lg font-semibold text-gray-800"></h2>
            <button id="next-week"
                class="px-3 py-1.5 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
                Next Week →
            </button>
        </div>
        <div id="week-grid" class="grid grid-cols-7 gap-2"></div>
    </div>

    <!-- ── Feed View ──────────────────────────────────────────── -->
    <div id="view-feed" class="hidden">
        <!-- Filters -->
        <div class="flex flex-wrap gap-3 mb-4 p-4 bg-white rounded-xl border border-gray-200">
            <select id="filter-module"
                class="text-sm border border-gray-200 rounded-lg px-3 py-1.5">
                <option value="">All Modules</option>
                <option value="operations">Operations</option>
                <option value="projects">Projects</option>
                <option value="accounts">Accounts</option>
                <option value="supply">Supply</option>
                <option value="integrations">Integrations</option>
            </select>
            <select id="filter-category"
                class="text-sm border border-gray-200 rounded-lg px-3 py-1.5">
                <option value="">All Actions</option>
                <option value="auth">Auth</option>
                <option value="create">Create</option>
                <option value="update">Update</option>
                <option value="delete">Delete</option>
                <option value="export">Export</option>
                <option value="approve">Approve</option>
                <option value="reject">Reject</option>
                <option value="permission_denied">Permission Denied</option>
            </select>
            <input id="filter-date-from" type="date"
                class="text-sm border border-gray-200 rounded-lg px-3 py-1.5">
            <input id="filter-date-to" type="date"
                class="text-sm border border-gray-200 rounded-lg px-3 py-1.5">
            <label class="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
                <input id="filter-flagged" type="checkbox"
                    class="rounded border-gray-300">
                Flagged only
            </label>
            <button id="feed-reset"
                class="text-sm text-gray-500 hover:text-gray-700 underline">
                Reset
            </button>
        </div>

        <div id="feed-list" class="space-y-2"></div>

        <div class="text-center mt-4">
            <button id="feed-load-more"
                class="hidden px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100">
                Load more...
            </button>
            <div id="feed-empty" class="hidden text-sm text-gray-400 py-8">
                No activities found.
            </div>
        </div>
    </div>

</div>
</div>

<!-- ── Day Modal ──────────────────────────────────────────────── -->
<div id="day-modal"
    class="hidden fixed inset-0 z-50 overflow-y-auto"
    onclick="handleModalOutsideClick(event)">
    <div class="flex min-h-screen items-center justify-center p-4">
        <div class="fixed inset-0 bg-black bg-opacity-40"></div>
        <div id="modal-content"
            class="relative bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-screen-90 overflow-y-auto p-6 z-10">
            <div class="text-center py-8 text-gray-400">Loading...</div>
        </div>
    </div>
</div>
{% endblock %}

{% block extra_js %}
<script>
const ACTIVITY_CONFIG = {
    apiMonth:   "{% url 'activity_logs:api_month' %}",
    apiWeek:    "{% url 'activity_logs:api_week' %}",
    apiDay:     "{% url 'activity_logs:api_day' date_str='__DATE__' %}",
    apiUserDay: "{% url 'activity_logs:api_user_day' user_id=0 date_str='__DATE__' %}",
    apiFeed:    "{% url 'activity_logs:api_feed' %}",
    today:      "{{ today|date:'Y-m-d' }}",
    year:       {{ year }},
    month:      {{ month }},
    csrfToken:  "{{ csrf_token }}",
};
</script>
<script src="{% static 'activity_logs/js/calendar.js' %}"></script>
<script src="{% static 'activity_logs/js/feed.js' %}"></script>
{% endblock %}
```

**Step 3: Write `static/activity_logs/js/calendar.js`**

```javascript
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
            // Hide all views
            Object.values(tabs).forEach(v =>
                document.getElementById(v).classList.add('hidden')
            );
            // Deactivate all tabs
            Object.keys(tabs).forEach(b => {
                const btn = document.getElementById(b);
                btn.classList.remove('text-white', 'bg-indigo-600');
                btn.classList.add('text-gray-600');
            });
            // Activate selected
            document.getElementById(viewId).classList.remove('hidden');
            const btn = document.getElementById(btnId);
            btn.classList.add('text-white', 'bg-indigo-600');
            btn.classList.remove('text-gray-600');

            // Load data on first activate
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
```

**Step 4: Write `static/activity_logs/js/feed.js`**

```javascript
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
                // Remove highlight after 5s
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
```

**Step 5: Write `templates/activity_logs/components/week_widget.html`**

```html
{% load static %}
{% load activity_log_tags %}

<div class="bg-white rounded-xl border border-gray-200 p-4">
    <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-gray-700">This Week's Activity</h3>
        <a href="{% url 'activity_logs:calendar' %}"
           class="text-xs text-indigo-600 hover:underline">View Full →</a>
    </div>
    <div id="widget-week-grid" class="grid grid-cols-7 gap-1">
        {% for day in widget_week_data %}
        <div class="text-center">
            <div class="text-xs text-gray-400">{{ day.day_name }}</div>
            <div class="rounded-lg py-1 mt-1 text-xs font-semibold
                {% if day.is_future %}bg-gray-50 text-gray-300
                {% elif day.total_actions > 20 %}bg-green-100 text-green-800
                {% elif day.total_actions > 5 %}bg-yellow-100 text-yellow-800
                {% elif day.total_actions > 0 %}bg-red-100 text-red-800
                {% else %}bg-gray-100 text-gray-400{% endif %}">
                {{ day.total_actions }}
            </div>
        </div>
        {% endfor %}
    </div>
</div>
```

---

## Phase 6: Backfill & Migration

### Task 10: Backfill management command

**Files:**
- Create: `activity_logs/management/commands/backfill_activity_logs.py`

**Step 1: Write the command**

```python
# activity_logs/management/commands/backfill_activity_logs.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from activity_logs.models import ActivityLog

BATCH_SIZE = 500


class Command(BaseCommand):
    help = 'Backfill ActivityLog from existing audit models'

    def add_arguments(self, parser):
        parser.add_argument('--source', default='all',
            choices=['all', 'DailyEntryAuditLog', 'LRAuditLog',
                     'QuotationAudit', 'ProjectCodeChangeLog'],
            help='Which source to backfill from')
        parser.add_argument('--dry-run', action='store_true',
            help='Show counts without inserting')

    def handle(self, *args, **options):
        source = options['source']
        dry_run = options['dry_run']

        if source in ('all', 'DailyEntryAuditLog'):
            self._backfill_daily_entry(dry_run)
        if source in ('all', 'LRAuditLog'):
            self._backfill_lr(dry_run)
        if source in ('all', 'QuotationAudit'):
            self._backfill_quotation(dry_run)
        if source in ('all', 'ProjectCodeChangeLog'):
            self._backfill_project_changes(dry_run)

        self.stdout.write(self.style.SUCCESS('Backfill complete.'))

    def _bulk_insert(self, records, dry_run, source_name):
        if dry_run:
            self.stdout.write(f'[DRY RUN] Would insert {len(records)} from {source_name}')
            return
        ActivityLog.objects.bulk_create(records, ignore_conflicts=True, batch_size=BATCH_SIZE)
        self.stdout.write(self.style.SUCCESS(f'Inserted {len(records)} from {source_name}'))

    def _backfill_daily_entry(self, dry_run):
        try:
            from operations.models import DailyEntryAuditLog
        except ImportError:
            self.stdout.write('DailyEntryAuditLog not found — skipping')
            return

        records = []
        for log in DailyEntryAuditLog.objects.select_related('changed_by', 'daily_entry').iterator():
            ts = log.changed_at or timezone.now()
            user = log.changed_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='signal',
                action_category='create' if log.action == 'CREATED' else 'update',
                action_type='daily_entry_' + log.action.lower(),
                module='operations',
                object_type='DailySpaceUtilization',
                object_id=log.daily_entry_id,
                object_repr=f'Daily Entry #{log.daily_entry_id}',
                description=f'{log.action} daily entry',
                extra_data={
                    'old_values': log.old_values or {},
                    'new_values': log.new_values or {},
                    'change_reason': log.change_reason or '',
                },
                is_backfilled=True,
                backfill_source='DailyEntryAuditLog',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'DailyEntryAuditLog')

    def _backfill_lr(self, dry_run):
        try:
            from operations.models_lr import LRAuditLog
        except ImportError:
            self.stdout.write('LRAuditLog not found — skipping')
            return

        records = []
        for log in LRAuditLog.objects.select_related('changed_by').iterator():
            ts = log.changed_at or timezone.now()
            user = log.changed_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='signal',
                action_category={
                    'CREATED': 'create', 'UPDATED': 'update', 'DELETED': 'delete'
                }.get(log.action, 'update'),
                action_type='lr_' + log.action.lower(),
                module='operations',
                object_type='LorryReceipt',
                object_id=log.lr_id,
                object_repr=f'LR #{log.lr_id}',
                description=f'{log.action} lorry receipt #{log.lr_id}',
                extra_data={
                    'old_values': log.old_values or {},
                    'new_values': log.new_values or {},
                },
                is_backfilled=True,
                backfill_source='LRAuditLog',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'LRAuditLog')

    def _backfill_quotation(self, dry_run):
        try:
            from projects.models_quotation import QuotationAudit
        except ImportError:
            self.stdout.write('QuotationAudit not found — skipping')
            return

        records = []
        for log in QuotationAudit.objects.select_related('user').iterator():
            ts = log.timestamp or timezone.now()
            user = log.user
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='create' if 'created' in log.action else (
                    'export' if log.action in ('pdf_generated', 'docx_generated', 'downloaded') else
                    'email' if log.action == 'email_sent' else
                    'approve' if log.action == 'client_accepted' else
                    'update'
                ),
                action_type='quotation_' + log.action,
                module='projects',
                object_type='Quotation',
                object_id=log.quotation_id,
                object_repr=f'Quotation #{log.quotation_id}',
                description=f'Quotation {log.action.replace("_", " ")}',
                ip_address=log.ip_address if hasattr(log, 'ip_address') else None,
                extra_data=log.changes or {},
                is_backfilled=True,
                backfill_source='QuotationAudit',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'QuotationAudit')

    def _backfill_project_changes(self, dry_run):
        try:
            from projects.models import ProjectCodeChangeLog
        except ImportError:
            self.stdout.write('ProjectCodeChangeLog not found — skipping')
            return

        records = []
        for log in ProjectCodeChangeLog.objects.select_related('changed_by').iterator():
            ts = log.changed_at or timezone.now()
            user = log.changed_by
            records.append(ActivityLog(
                user=user,
                user_display_name=user.get_full_name() if user else 'Unknown',
                role_snapshot=getattr(user, 'role', 'unknown') if user else 'unknown',
                source='web',
                action_category='update',
                action_type='project_field_changed',
                module='projects',
                object_type='ProjectCode',
                object_id=log.project_id,
                object_repr=f'Project #{log.project_id}',
                description=f'Changed {log.field_name} on project',
                ip_address=getattr(log, 'ip_address', None),
                extra_data={
                    'field_name': log.field_name,
                    'old': {log.field_name: log.old_value},
                    'new': {log.field_name: log.new_value},
                },
                is_backfilled=True,
                backfill_source='ProjectCodeChangeLog',
                timestamp=ts,
                date=ts.date(),
            ))
        self._bulk_insert(records, dry_run, 'ProjectCodeChangeLog')
```

---

## Phase 7: Old Calendar Removal

### Task 11: Remove old calendar code

**Files:**
- Delete: `operations/calendar_utils.py`
- Modify: `operations/views.py` (remove 3 calendar views)
- Modify: `operations/urls.py` (remove 3 calendar routes)
- Delete: `templates/operations/calendar_page.html`
- Delete: `templates/operations/calendar_components/week_widget.html`
- Delete: `static/js/calendar.js`

**Step 1: Remove calendar routes from `operations/urls.py`**

Delete these 3 lines:
```python
path('calendar/', views.calendar_page_view, name='calendar_page'),
path('calendar/day/<str:date_str>/', views.calendar_day_detail_api, name='calendar_day_detail'),
path('calendar/week/', views.calendar_week_api, name='calendar_week'),
```

**Step 2: Remove calendar views from `operations/views.py`**

Remove `calendar_page_view`, `calendar_day_detail_api`, `calendar_week_api` functions (lines ~2402–2586).

**Step 3: Delete old files**

```bash
rm operations/calendar_utils.py
rm templates/operations/calendar_page.html
rm templates/operations/calendar_components/week_widget.html
rm static/js/calendar.js
```

**Step 4: Replace week widget includes in dashboards**

In these 3 files, replace:
```django
{% include 'operations/calendar_components/week_widget.html' %}
```
With:
```django
{% include 'activity_logs/components/week_widget.html' %}
```

Files to update:
- `templates/dashboards/operation_coordinator_dashboard.html`
- `templates/dashboards/warehouse_manager_dashboard.html`
- `templates/dashboards/operation_manager_dashboard.html`

**Step 5: Update navbar link**

In `templates/components/navbar.html`, change the calendar URL from:
```
{% url 'operations:calendar_page' %}
```
To:
```
{% url 'activity_logs:calendar' %}
```

**Step 6: Verify no references remain**

```bash
grep -r "calendar_page\|calendar_day_detail\|calendar_week\|calendar_utils" \
    --include="*.py" --include="*.html" .
```

Expected: no matches.

---

## Phase 8: Management Commands & Cleanup

### Task 12: Anonymize deleted user logs command

**Files:**
- Create: `activity_logs/management/commands/anonymize_deleted_user_logs.py`

```python
from django.core.management.base import BaseCommand
from activity_logs.models import ActivityLog


class Command(BaseCommand):
    help = 'Anonymize activity logs for a deleted user (GDPR compliance)'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, required=True)

    def handle(self, *args, **options):
        user_id = options['user_id']
        updated = ActivityLog.objects.filter(user_id=user_id).update(
            user=None,
            user_display_name='Deleted User',
            anonymized=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Anonymized {updated} activity log entries for user_id={user_id}'
        ))
```

---

## Phase 9: Tests

### Task 13: Write tests

**Files:**
- Create: `tests/unit/test_activity_logs.py`

```python
# tests/unit/test_activity_logs.py
import pytest
from django.utils import timezone
from django.test import RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def coordinator(db):
    return User.objects.create_user(
        username='coord1', password='pass', role='operation_coordinator'
    )


@pytest.fixture
def manager(db):
    return User.objects.create_user(
        username='mgr1', password='pass', role='operation_manager'
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username='admin1', password='pass', role='admin'
    )


@pytest.fixture
def controller(db):
    return User.objects.create_user(
        username='ctrl1', password='pass', role='operation_controller'
    )


@pytest.fixture
def activity_log(db, coordinator):
    from activity_logs.models import ActivityLog
    now = timezone.now()
    return ActivityLog.objects.create(
        user=coordinator,
        user_display_name='Coord One',
        role_snapshot='operation_coordinator',
        source='web',
        action_category='create',
        action_type='daily_entry_created',
        module='operations',
        description='Created daily entry for GW-001',
        timestamp=now,
        date=now.date(),
    )


# ── Visibility tests ─────────────────────────────────────────────

class TestVisibility:

    def test_coordinator_sees_only_own_logs(self, db, coordinator, manager):
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(coordinator)
        assert coordinator in visible
        assert manager not in visible

    def test_admin_sees_all(self, db, coordinator, manager, admin_user):
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(admin_user)
        assert coordinator in visible
        assert manager in visible
        assert admin_user in visible

    def test_operation_controller_sees_ops_chain(self, db, coordinator, manager, controller):
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(controller)
        assert coordinator in visible
        assert manager in visible
        assert controller in visible

    def test_operation_manager_sees_coordinators(self, db, coordinator, manager, controller):
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(manager)
        assert coordinator in visible
        assert manager in visible
        assert controller not in visible

    def test_super_user_cannot_see_admin(self, db, admin_user):
        super_user = User.objects.create_user(
            username='su1', password='pass', role='super_user'
        )
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(super_user)
        assert admin_user not in visible
        assert super_user in visible


# ── log_activity_direct tests ────────────────────────────────────

class TestLogActivityDirect:

    def test_creates_log_entry(self, db, coordinator):
        from activity_logs.utils import log_activity_direct
        from activity_logs.models import ActivityLog
        log_activity_direct(
            user=coordinator,
            source='web',
            action_category='create',
            action_type='test_action',
            module='test',
            description='Test log entry',
        )
        assert ActivityLog.objects.filter(
            user=coordinator, action_type='test_action'
        ).exists()

    def test_never_raises_on_bad_input(self, db):
        from activity_logs.utils import log_activity_direct
        # Should not raise even with None user
        log_activity_direct(
            user=None,
            source='cron',
            action_category='system',
            action_type='test',
            module='test',
            description='test',
        )

    def test_sets_date_from_timestamp(self, db, coordinator):
        from activity_logs.utils import log_activity_direct
        from activity_logs.models import ActivityLog
        log_activity_direct(
            user=coordinator, source='web',
            action_category='create', action_type='dated_test',
            module='test', description='date test',
        )
        log = ActivityLog.objects.get(action_type='dated_test')
        assert log.date == log.timestamp.date()


# ── API view tests ───────────────────────────────────────────────

class TestAPIViews:

    def test_api_month_requires_login(self, client):
        res = client.get('/activity/api/month/')
        assert res.status_code == 302  # redirect to login

    def test_api_month_returns_json(self, db, client, coordinator):
        client.force_login(coordinator)
        res = client.get('/activity/api/month/?year=2026&month=3')
        assert res.status_code == 200
        data = res.json()
        assert 'weeks' in data
        assert 'month_name' in data

    def test_api_day_returns_json(self, db, client, coordinator, activity_log):
        client.force_login(coordinator)
        res = client.get(f'/activity/api/day/{activity_log.date.isoformat()}/')
        assert res.status_code == 200
        data = res.json()
        assert 'users' in data
        assert 'date_display' in data

    def test_api_user_day_unauthorized(self, db, client, coordinator, manager):
        """Coordinator cannot see manager's day detail."""
        client.force_login(coordinator)
        res = client.get(f'/activity/api/user/{manager.pk}/day/2026-03-08/')
        assert res.status_code == 403

    def test_api_user_day_authorized(self, db, client, coordinator, activity_log):
        """Coordinator can see their own day detail."""
        client.force_login(coordinator)
        res = client.get(
            f'/activity/api/user/{coordinator.pk}/day/{activity_log.date.isoformat()}/'
        )
        assert res.status_code == 200

    def test_api_feed_filters_by_visibility(self, db, client, coordinator, manager):
        from activity_logs.models import ActivityLog
        now = timezone.now()
        # Manager log — should NOT be visible to coordinator
        ActivityLog.objects.create(
            user=manager, user_display_name='Mgr', role_snapshot='operation_manager',
            source='web', action_category='create', action_type='mgr_action',
            module='test', description='Manager action',
            timestamp=now, date=now.date(),
        )
        client.force_login(coordinator)
        res = client.get('/activity/api/feed/')
        data = res.json()
        user_ids = [l['user_id'] for l in data['logs']]
        assert manager.pk not in user_ids
```

**Step 2: Run tests**

```bash
pytest tests/unit/test_activity_logs.py -v
```

Expected: all tests pass.

---

## Phase 10: Production Deployment Checklist

### Task 14: Pre-deployment verification

**Step 1: Run system check**
```bash
python manage.py check --deploy
```
Expected: no errors.

**Step 2: Verify migrations**
```bash
python manage.py showmigrations activity_logs
```
Expected: `[X] 0001_initial`, `[X] 0002_partition_setup`

**Step 3: Dry-run backfill**
```bash
python manage.py backfill_activity_logs --source=all --dry-run
```
Verify counts match source tables.

**Step 4: Run actual backfill**
```bash
python manage.py backfill_activity_logs --source=all
```

**Step 5: Create next 3 months of partitions**
```bash
python manage.py create_activity_partitions --months=3
```

**Step 6: Verify partition table exists**
```bash
python manage.py dbshell
```
```sql
SELECT tablename FROM pg_tables WHERE tablename LIKE 'activity_logs_%' ORDER BY tablename;
\q
```

**Step 7: Final smoke test — navigate to `/activity/` and verify:**
- Month view loads with correct grid
- Clicking a day opens modal
- User cards appear in modal
- Back navigation works
- Feed tab loads and shows entries
- Feed filters work
- Old `/operations/calendar/` returns 404 or redirects

---

## Cron Jobs to Set Up (after deployment)

Add to crontab or Cloud Scheduler:

```bash
# Create partitions — run 1st of every month
0 0 1 * * /path/to/venv/bin/python manage.py create_activity_partitions --months=3

# Purge old partitions — run 1st of every month
0 1 1 * * /path/to/venv/bin/python manage.py purge_old_activity_partitions
```

---

## Summary

| Phase | Tasks | Key Output |
|-------|-------|-----------|
| 1 | 1–2 | `activity_logs` app, `ActivityLog` model, partitioned table |
| 2 | 3–6 | Middleware, signals, utils, decorator |
| 3 | 7 | Admin registration |
| 4 | 8 | All 5 API views |
| 5 | 9 | Templates + JS (calendar.js, feed.js) |
| 6 | 10 | Backfill command (4 source models) |
| 7 | 11 | Old calendar removed, navbar updated |
| 8 | 12 | Anonymize command |
| 9 | 13 | Full test suite |
| 10 | 14 | Deployment checklist |
