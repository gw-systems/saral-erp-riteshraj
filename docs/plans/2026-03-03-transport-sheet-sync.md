# Transport Sheet Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Sync a manual transport Google Sheet into `ExpenseRecord` so its data appears automatically in the transport project-wise view, with manual trigger buttons in settings and hourly auto-sync in production via Cloud Scheduler.

**Architecture:** New `integrations/transport_sheet/` app. Creates a dedicated `GoogleSheetsToken` + a singleton `TransportSheetConfig` model storing sheet_id/tab. Sync engine reads sheet rows, maps columns to `ExpenseRecord` fields, upserts with `unique_expense_number = TS-{md5hash}` and `approval_status='Approved'`. A new worker endpoint handles Cloud Tasks/Scheduler calls. Manual trigger added to expense_log settings page. Management command for CLI use.

**Tech Stack:** Django, Google Sheets API v4 (existing `SheetsAPIClient` + `SheetsOAuthManager`), existing `ExpenseLogSettings` OAuth credentials, existing `GoogleSheetsToken` model.

---

### Task 1: Create the `transport_sheet` Django app skeleton

**Files:**
- Create: `integrations/transport_sheet/__init__.py`
- Create: `integrations/transport_sheet/apps.py`
- Modify: `minierp/settings.py` — add to INSTALLED_APPS

**Step 1: Create `__init__.py`**

```python
# integrations/transport_sheet/__init__.py
```

**Step 2: Create `apps.py`**

```python
# integrations/transport_sheet/apps.py
from django.apps import AppConfig

class TransportSheetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations.transport_sheet'
    verbose_name = 'Transport Sheet Sync'
```

**Step 3: Add to INSTALLED_APPS in `minierp/settings.py`**

Find the line:
```python
'integrations.expense_log',  # Google Sheets Expense Log
```
Add after it:
```python
'integrations.transport_sheet',  # Transport Sheet Sync
```

**Step 4: Verify**
```bash
cd /Users/apple/Documents/DataScienceProjects/ERP && source venv/bin/activate && python manage.py check
```
Expected: `System check identified no issues (0 silenced).`

**Step 5: Commit**
```bash
git add integrations/transport_sheet/ minierp/settings.py
git commit -m "feat: add transport_sheet app skeleton"
```

---

### Task 2: Create `TransportSheetConfig` model + migration

**Files:**
- Create: `integrations/transport_sheet/models.py`
- Create: `integrations/transport_sheet/migrations/__init__.py`
- Create: `integrations/transport_sheet/migrations/0001_initial.py` (generated)

**Step 1: Create `models.py`**

```python
# integrations/transport_sheet/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class TransportSheetConfig(models.Model):
    """
    Singleton config for the manual transport Google Sheet.
    Uses ExpenseLogSettings OAuth credentials — no separate OAuth needed.
    """
    sheet_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Google Sheet ID (from URL: /spreadsheets/d/{SHEET_ID}/)"
    )
    tab_name = models.CharField(
        max_length=255,
        default='Sheet1',
        help_text="Tab/sheet name to read from"
    )
    header_row = models.PositiveIntegerField(
        default=1,
        help_text="Row number containing column headers (1-indexed)"
    )
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_rows = models.IntegerField(default=0, help_text="Rows processed in last sync")
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transport_sheet_config_updates'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Transport Sheet Config'

    def __str__(self):
        return f"Transport Sheet: {self.sheet_id} / {self.tab_name}"

    @classmethod
    def load(cls):
        """Load singleton config"""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
```

**Step 2: Generate migration**
```bash
python manage.py makemigrations transport_sheet
```

**Step 3: Apply migration**
```bash
python manage.py migrate transport_sheet
```

**Step 4: Verify**
```bash
python manage.py check
```

**Step 5: Commit**
```bash
git add integrations/transport_sheet/models.py integrations/transport_sheet/migrations/
git commit -m "feat: add TransportSheetConfig singleton model"
```

---

### Task 3: Create the sync engine

**Files:**
- Create: `integrations/transport_sheet/sync_engine.py`

**Step 1: Create `sync_engine.py`**

```python
# integrations/transport_sheet/sync_engine.py
"""
Sync engine for manual transport Google Sheet → ExpenseRecord.

Column mapping (sheet → ExpenseRecord):
    Month               → service_month
    Operation Personnel → submitted_by
    Date                → timestamp (stored as DateTimeField)
    Client Name         → client_name
    Client              → client
    Transporter Name    → transporter_name
    From                → from_address
    To                  → to_address
    Vehicle Type (MT)   → transport_type
    Vehicle No.         → vehicle_no
    Invoice No.         → invoice_no
    Charges@GW          → charges_at_gw
    Charges@Client      → charges_at_client
    Remark              → remark
    Warai Charges       → warai_charges
    Labour Charges      → labour_charges

Fixed values on all imported rows:
    nature_of_expense = 'Transport'
    approval_status   = 'Approved'
    unique_expense_number = 'TS-{md5hash}'
"""
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from django.utils import timezone as django_timezone

from integrations.expense_log.models import ExpenseLogSettings, GoogleSheetsToken, ExpenseRecord
from integrations.expense_log.utils.sheets_client import SheetsAPIClient
from integrations.expense_log.utils.sheets_auth import SheetsOAuthManager
from integrations.models import SyncLog
from .models import TransportSheetConfig

logger = logging.getLogger(__name__)

# Expected sheet column headers (lowercase, stripped for matching)
COLUMN_MAP = {
    'month': 'service_month',
    'operation personnel': 'submitted_by',
    'date': '_date',           # parsed separately
    'client name': 'client_name',
    'client': 'client',
    'transporter name': 'transporter_name',
    'from': 'from_address',
    'to': 'to_address',
    'vehicle type (mt)': 'transport_type',
    'vehicle no.': 'vehicle_no',
    'invoice no.': 'invoice_no',
    'charges@gw': 'charges_at_gw',
    'charges@client': 'charges_at_client',
    'margin %': '_margin',     # ignored — recalculated
    'remark': 'remark',
    'warai charges': 'warai_charges',
    'labour charges': 'labour_charges',
}

DECIMAL_FIELDS = {'charges_at_gw', 'charges_at_client', 'warai_charges', 'labour_charges'}


def _parse_amount(value):
    """Parse amount string like '1,815.00' or '₹1815' → Decimal"""
    if not value:
        return None
    cleaned = str(value).replace(',', '').replace('₹', '').replace('%', '').strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_date(value):
    """Parse date string like '02/Jan/2026' → datetime"""
    if not value:
        return django_timezone.now()
    for fmt in ('%d/%b/%Y', '%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    logger.warning(f"Could not parse date: {value!r}, using now()")
    return django_timezone.now()


def _make_unique_key(row_data):
    """Generate TS-{md5} deduplication key from stable row fields."""
    key_str = '|'.join([
        str(row_data.get('client_name', '')),
        str(row_data.get('_date', '')),
        str(row_data.get('vehicle_no', '')),
        str(row_data.get('charges_at_gw', '')),
    ])
    md5 = hashlib.md5(key_str.encode()).hexdigest()[:12]
    return f'TS-{md5}'


def _get_or_create_transport_token(config):
    """
    Get or create a system GoogleSheetsToken for the transport sheet.
    Uses the first admin user as owner (system token).
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Use first superuser as token owner
    admin = User.objects.filter(is_superuser=True).first()
    if not admin:
        raise RuntimeError("No superuser found — cannot create transport sheet token")

    settings_obj = ExpenseLogSettings.load()
    if not settings_obj.client_id:
        raise RuntimeError("ExpenseLogSettings has no client_id — configure OAuth first")

    # Get or create a placeholder token for this sheet
    # The actual API calls use service-level credentials refreshed via OAuth
    token, created = GoogleSheetsToken.objects.get_or_create(
        email_account='transport-sheet-system',
        sheet_id=config.sheet_id,
        defaults={
            'user': admin,
            'encrypted_token': '',   # populated on first successful auth
            'sheet_name': config.tab_name,
            'is_active': True,
        }
    )
    if not created and token.sheet_name != config.tab_name:
        token.sheet_name = config.tab_name
        token.save(update_fields=['sheet_name'])
    return token


class TransportSheetSyncEngine:
    """
    Reads transport sheet rows and upserts into ExpenseRecord.
    Uses existing ExpenseLogSettings OAuth credentials.
    """

    def __init__(self, triggered_by_user=None):
        self.config = TransportSheetConfig.load()
        self.triggered_by_user = triggered_by_user or 'system'
        self.stats = {
            'total_rows': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
        }
        self.batch_log = SyncLog.objects.create(
            integration='transport_sheet',
            sync_type='transport_sheet_sync',
            log_kind='batch',
            status='running',
            triggered_by_user=self.triggered_by_user,
            overall_progress_percent=0,
        )

    def sync(self):
        """Main sync entry point. Returns stats dict."""
        try:
            if not self.config.sheet_id:
                raise ValueError("Transport sheet ID not configured. Set it in Transport Sheet Settings.")

            token = _get_or_create_transport_token(self.config)
            client = SheetsAPIClient(token)

            # Fetch all data from sheet
            range_name = f"{self.config.tab_name}!A1:Z10000"
            rows = client.get_sheet_data(range_name)

            if not rows or len(rows) < 2:
                logger.info("Transport sheet: no data rows found")
                self._finalize('completed')
                return self.stats

            # Parse header row
            header_idx = self.config.header_row - 1
            headers = [str(h).strip().lower() for h in rows[header_idx]]
            data_rows = rows[header_idx + 1:]

            self.stats['total_rows'] = len(data_rows)
            logger.info(f"Transport sheet: {len(data_rows)} data rows found")

            for i, row in enumerate(data_rows):
                try:
                    self._process_row(row, headers, token)
                except Exception as e:
                    self.stats['errors'] += 1
                    logger.error(f"Row {i+2} error: {e}", exc_info=True)

            # Update config last_synced_at
            self.config.last_synced_at = django_timezone.now()
            self.config.last_sync_rows = self.stats['total_rows']
            self.config.save(update_fields=['last_synced_at', 'last_sync_rows'])

            self._finalize('completed')
            return self.stats

        except Exception as e:
            logger.error(f"TransportSheetSyncEngine failed: {e}", exc_info=True)
            self._finalize('error', str(e))
            raise

    def _process_row(self, row, headers, token):
        """Parse one sheet row and upsert into ExpenseRecord."""
        # Build raw dict from headers
        raw = {}
        for col_idx, header in enumerate(headers):
            value = row[col_idx].strip() if col_idx < len(row) else ''
            mapped = COLUMN_MAP.get(header)
            if mapped:
                raw[mapped] = value

        # Skip completely empty rows
        if not any(raw.values()):
            self.stats['skipped'] += 1
            return

        # Skip rows missing essential fields
        if not raw.get('client_name') and not raw.get('charges_at_gw'):
            self.stats['skipped'] += 1
            return

        # Parse special fields
        raw['_date'] = raw.get('_date', '')
        timestamp = _parse_date(raw.pop('_date', ''))
        raw.pop('_margin', None)  # discard margin from sheet

        # Parse decimal fields
        for field in DECIMAL_FIELDS:
            if field in raw:
                raw[field] = _parse_amount(raw[field])

        # Build unique key
        uen = _make_unique_key({**raw, '_date': str(timestamp.date())})

        # Upsert
        defaults = {
            'token': token,
            'timestamp': timestamp,
            'nature_of_expense': 'Transport',
            'approval_status': 'Approved',
            'submitted_by': raw.get('submitted_by', ''),
            'service_month': raw.get('service_month', ''),
            'client_name': raw.get('client_name', ''),
            'client': raw.get('client', ''),
            'transporter_name': raw.get('transporter_name', ''),
            'from_address': raw.get('from_address', ''),
            'to_address': raw.get('to_address', ''),
            'transport_type': raw.get('transport_type', ''),
            'vehicle_no': raw.get('vehicle_no', ''),
            'invoice_no': raw.get('invoice_no', ''),
            'charges_at_gw': raw.get('charges_at_gw'),
            'charges_at_client': raw.get('charges_at_client'),
            'warai_charges': raw.get('warai_charges'),
            'labour_charges': raw.get('labour_charges'),
            'remark': raw.get('remark', ''),
            'raw_data': {'_source': 'transport_sheet', **{k: str(v) for k, v in raw.items()}},
        }

        obj, created = ExpenseRecord.objects.update_or_create(
            unique_expense_number=uen,
            defaults=defaults,
        )

        if created:
            self.stats['created'] += 1
        else:
            self.stats['updated'] += 1

    def _finalize(self, status, error_msg=None):
        self.batch_log.status = status
        self.batch_log.overall_progress_percent = 100
        if error_msg:
            self.batch_log.notes = error_msg
        self.batch_log.save(update_fields=['status', 'overall_progress_percent', 'notes'])
        logger.info(f"Transport sheet sync {status}: {self.stats}")
```

**Step 2: Verify import chain**
```bash
python manage.py check
```

**Step 3: Commit**
```bash
git add integrations/transport_sheet/sync_engine.py
git commit -m "feat: transport sheet sync engine — reads sheet, upserts ExpenseRecord with TS- keys"
```

---

### Task 4: Create worker endpoint + management command

**Files:**
- Create: `integrations/transport_sheet/workers.py`
- Create: `integrations/transport_sheet/management/__init__.py`
- Create: `integrations/transport_sheet/management/commands/__init__.py`
- Create: `integrations/transport_sheet/management/commands/sync_transport_sheet.py`
- Create: `integrations/transport_sheet/urls.py`
- Modify: `minierp/urls.py` — include new URLs

**Step 1: Create `workers.py`**

```python
# integrations/transport_sheet/workers.py
"""
Cloud Tasks / Cloud Scheduler worker endpoint for transport sheet sync.
Hourly in production only (DEBUG=False).
"""
import json
import logging
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .sync_engine import TransportSheetSyncEngine

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(['POST'])
def transport_sync_worker(request):
    """
    Worker endpoint for transport sheet sync.
    Called by Cloud Scheduler hourly (production only).
    Manual trigger also posts here via _trigger_transport_sync().

    POST body (optional):
        {"triggered_by_user": "username", "sync_type": "full"}
    """
    # In DEBUG mode, only allow if explicitly enabled
    if settings.DEBUG:
        enforce = getattr(settings, 'ENFORCE_CLOUD_TASKS_AUTH', False)
        if enforce:
            return JsonResponse({'error': 'Not available in DEBUG mode'}, status=403)

    try:
        payload = {}
        if request.body:
            try:
                payload = json.loads(request.body)
            except json.JSONDecodeError:
                pass

        triggered_by_user = payload.get('triggered_by_user', 'scheduler')
        logger.info(f"Transport sheet sync triggered by: {triggered_by_user}")

        engine = TransportSheetSyncEngine(triggered_by_user=triggered_by_user)
        stats = engine.sync()

        return JsonResponse({'status': 'success', 'stats': stats})

    except Exception as e:
        logger.error(f"Transport sync worker error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'error': str(e)}, status=500)
```

**Step 2: Create management command directories and files**

```python
# integrations/transport_sheet/management/__init__.py
# integrations/transport_sheet/management/commands/__init__.py
```

```python
# integrations/transport_sheet/management/commands/sync_transport_sheet.py
from django.core.management.base import BaseCommand
from integrations.transport_sheet.sync_engine import TransportSheetSyncEngine


class Command(BaseCommand):
    help = 'Sync manual transport Google Sheet into ExpenseRecord'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            default='management_command',
            help='Username to attribute the sync to (default: management_command)',
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting transport sheet sync...')
        try:
            engine = TransportSheetSyncEngine(triggered_by_user=options['user'])
            stats = engine.sync()
            self.stdout.write(self.style.SUCCESS(
                f"Sync complete: {stats['created']} created, "
                f"{stats['updated']} updated, "
                f"{stats['skipped']} skipped, "
                f"{stats['errors']} errors "
                f"(total: {stats['total_rows']} rows)"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Sync failed: {e}"))
            raise
```

**Step 3: Create `urls.py`**

```python
# integrations/transport_sheet/urls.py
from django.urls import path
from . import views, workers

app_name = 'transport_sheet'

urlpatterns = [
    path('settings/', views.transport_sheet_settings, name='settings'),
    path('worker/sync/', workers.transport_sync_worker, name='sync_worker'),
]
```

**Step 4: Include in `minierp/urls.py`**

Find where expense_log is included (look for `expense-log` or `expense_log`) and add after it:
```python
path('transport-sheet/', include('integrations.transport_sheet.urls', namespace='transport_sheet')),
```

**Step 5: Verify**
```bash
python manage.py check
python manage.py sync_transport_sheet --help
```

**Step 6: Commit**
```bash
git add integrations/transport_sheet/workers.py integrations/transport_sheet/management/ integrations/transport_sheet/urls.py minierp/urls.py
git commit -m "feat: transport sheet worker endpoint, management command, urls"
```

---

### Task 5: Create settings view + template

**Files:**
- Create: `integrations/transport_sheet/views.py`
- Create: `integrations/transport_sheet/templates/transport_sheet/settings.html`

**Step 1: Create `views.py`**

```python
# integrations/transport_sheet/views.py
import json
import logging
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import TransportSheetConfig
from .sync_engine import TransportSheetSyncEngine

logger = logging.getLogger(__name__)


def _trigger_transport_sync(triggered_by_user=None):
    """Run transport sync — via Cloud Tasks if available, else synchronously."""
    try:
        from google.cloud import tasks_v2
        client = tasks_v2.CloudTasksClient()
        project = os.getenv('GOOGLE_CLOUD_PROJECT')
        location = os.getenv('CLOUD_TASKS_LOCATION', 'asia-south1')
        queue = os.getenv('CLOUD_TASKS_QUEUE', 'default')
        parent = client.queue_path(project, location, queue)

        payload = {'triggered_by_user': triggered_by_user or 'manual'}
        task = {
            'http_request': {
                'http_method': tasks_v2.HttpMethod.POST,
                'url': f"{os.getenv('APP_URL')}/transport-sheet/worker/sync/",
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(payload).encode(),
            }
        }
        client.create_task(request={'parent': parent, 'task': task})
        logger.info("Transport sync task queued via Cloud Tasks")
    except Exception:
        # Fallback: run synchronously
        logger.warning("Cloud Tasks unavailable — running transport sync synchronously")
        engine = TransportSheetSyncEngine(triggered_by_user=triggered_by_user)
        engine.sync()


@login_required
def transport_sheet_settings(request):
    """
    Settings page for transport sheet config.
    Admin-only: configure sheet_id, tab_name, trigger manual sync.
    """
    if not request.user.is_staff:
        messages.error(request, "Admin access required.")
        return redirect('expense_log:dashboard')

    config = TransportSheetConfig.load()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'save_config':
            config.sheet_id = request.POST.get('sheet_id', '').strip()
            config.tab_name = request.POST.get('tab_name', 'Sheet1').strip()
            config.header_row = int(request.POST.get('header_row', 1))
            config.is_active = request.POST.get('is_active') == 'on'
            config.updated_by = request.user
            config.save()
            messages.success(request, "Transport sheet config saved.")

        elif action == 'sync_now':
            if not config.sheet_id:
                messages.error(request, "Please save a Sheet ID first.")
            else:
                try:
                    _trigger_transport_sync(triggered_by_user=request.user.username)
                    messages.success(request, "Transport sheet sync started.")
                except Exception as e:
                    messages.error(request, f"Sync failed: {e}")

        return redirect('transport_sheet:settings')

    return render(request, 'transport_sheet/settings.html', {'config': config})
```

**Step 2: Create template directory and file**
```bash
mkdir -p /Users/apple/Documents/DataScienceProjects/ERP/integrations/transport_sheet/templates/transport_sheet/
```

Create `integrations/transport_sheet/templates/transport_sheet/settings.html`:

```html
{% extends 'base.html' %}
{% load static %}

{% block title %}Transport Sheet Settings{% endblock %}

{% block content %}
<div class="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
<div class="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

    <div class="flex items-center justify-between mb-8">
        <div>
            <h1 class="text-3xl font-bold text-gray-900">🚚 Transport Sheet Settings</h1>
            <p class="text-gray-600 mt-1">Connect the manual transport Google Sheet</p>
        </div>
        <a href="{% url 'expense_log:dashboard' %}" class="inline-flex items-center px-4 py-2 bg-gray-600 text-white rounded-lg text-sm font-medium hover:bg-gray-700 transition">
            Back to Dashboard
        </a>
    </div>

    {% if messages %}
    {% for message in messages %}
    <div class="mb-4 px-4 py-3 rounded-lg {% if message.tags == 'error' %}bg-red-100 text-red-800{% else %}bg-green-100 text-green-800{% endif %}">
        {{ message }}
    </div>
    {% endfor %}
    {% endif %}

    <!-- Config Form -->
    <div class="bg-white rounded-xl shadow-md p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-800 mb-4">Sheet Configuration</h2>
        <form method="post">
            {% csrf_token %}
            <input type="hidden" name="action" value="save_config">

            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-1">Google Sheet ID</label>
                <input type="text" name="sheet_id" value="{{ config.sheet_id }}"
                    placeholder="e.g. 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
                    class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500">
                <p class="text-xs text-gray-500 mt-1">Found in the sheet URL: /spreadsheets/d/<strong>{SHEET_ID}</strong>/edit</p>
            </div>

            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-1">Tab Name</label>
                <input type="text" name="tab_name" value="{{ config.tab_name }}"
                    placeholder="Sheet1"
                    class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500">
            </div>

            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-1">Header Row Number</label>
                <input type="number" name="header_row" value="{{ config.header_row }}" min="1"
                    class="w-32 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500">
            </div>

            <div class="mb-4 flex items-center gap-2">
                <input type="checkbox" name="is_active" id="is_active" {% if config.is_active %}checked{% endif %}
                    class="h-4 w-4 text-teal-600 border-gray-300 rounded">
                <label for="is_active" class="text-sm text-gray-700">Active (include in auto-sync)</label>
            </div>

            <button type="submit" class="px-6 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition font-medium">
                Save Configuration
            </button>
        </form>
    </div>

    <!-- Sync Controls -->
    <div class="bg-white rounded-xl shadow-md p-6 mb-6">
        <h2 class="text-lg font-semibold text-gray-800 mb-2">Manual Sync</h2>
        {% if config.last_synced_at %}
        <p class="text-sm text-gray-500 mb-4">Last synced: {{ config.last_synced_at|date:"d M Y H:i" }} — {{ config.last_sync_rows }} rows processed</p>
        {% else %}
        <p class="text-sm text-gray-500 mb-4">Never synced</p>
        {% endif %}

        <form method="post">
            {% csrf_token %}
            <input type="hidden" name="action" value="sync_now">
            <button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
                {% if not config.sheet_id %}disabled title="Save a Sheet ID first"{% endif %}>
                Sync Now
            </button>
        </form>
    </div>

    <!-- Auto-sync Info -->
    <div class="bg-blue-50 border border-blue-200 rounded-xl p-4">
        <h3 class="text-sm font-semibold text-blue-800 mb-1">Auto-sync Schedule</h3>
        <p class="text-sm text-blue-700">
            Production: runs hourly via Google Cloud Scheduler<br>
            Target: <code>POST /transport-sheet/worker/sync/</code>
        </p>
    </div>

</div>
</div>
{% endblock %}
```

**Step 3: Verify**
```bash
python manage.py check
```

**Step 4: Commit**
```bash
git add integrations/transport_sheet/views.py integrations/transport_sheet/templates/
git commit -m "feat: transport sheet settings view and template"
```

---

### Task 6: Add Cloud Scheduler comment + push

**Files:**
- Modify: `minierp/settings.py` — add Cloud Scheduler setup comment

**Step 1: Find the Cloud Scheduler comments section in settings.py (around line 273) and add:**

```python
# Transport Sheet Sync — hourly (production only)
# Cloud Scheduler job:
#   Name: transport-sheet-sync-hourly
#   Schedule: 0 * * * *  (every hour)
#   Target: POST {APP_URL}/transport-sheet/worker/sync/
#   Body: {"triggered_by_user": "scheduler"}
#   Auth: OIDC token
```

**Step 2: Final check**
```bash
python manage.py check
python manage.py migrate --check
```

**Step 3: Final commit + push**
```bash
git add minierp/settings.py
git commit -m "feat: transport sheet sync complete — sheet config, sync engine, worker, settings UI, scheduler comment"
git push origin main
```

---

## Post-Implementation: Cloud Scheduler Setup (manual step)

After deploying to production, create the Cloud Scheduler job in GCP Console:

- **Name:** `transport-sheet-sync-hourly`
- **Frequency:** `0 * * * *` (every hour)
- **Target:** HTTP POST to `{APP_URL}/transport-sheet/worker/sync/`
- **Body:** `{"triggered_by_user": "scheduler"}`
- **Auth:** OIDC token (same service account as other schedulers)

Also: the transport sheet must be shared with the Google account used in `ExpenseLogSettings` OAuth so the API can read it.
