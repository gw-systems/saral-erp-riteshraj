import json
import logging
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from integrations.expense_log.models import GoogleSheetsToken
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
                'url': f"{os.getenv('APP_URL', '')}/transport-sheet/worker/sync/",
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
    Settings page for transport sheet sync.
    Staff-only. Shows available GoogleSheetsTokens to pick from,
    is_active toggle, manual sync button, and last sync stats.
    """
    if not request.user.is_staff:
        messages.error(request, "Admin access required.")
        return redirect('expense_log:dashboard')

    config = TransportSheetConfig.load()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'save_config':
            token_id_str = request.POST.get('token_id', '').strip()
            config.token_id = int(token_id_str) if token_id_str else None
            config.is_active = request.POST.get('is_active') == 'on'
            config.updated_by = request.user
            config.save()
            messages.success(request, "Transport sheet config saved.")

        elif action == 'sync_now':
            if not config.token_id:
                messages.error(request, "Please select and save a sheet token first.")
            else:
                try:
                    _trigger_transport_sync(triggered_by_user=request.user.username)
                    messages.success(request, "Transport sheet sync started.")
                except Exception as e:
                    messages.error(request, f"Sync failed: {e}")

        return redirect('transport_sheet:settings')

    # Get all active GoogleSheetsTokens for the dropdown
    available_tokens = GoogleSheetsToken.objects.filter(is_active=True).order_by('email_account', 'sheet_id')

    # Get selected token info
    selected_token = None
    if config.token_id:
        try:
            selected_token = GoogleSheetsToken.objects.get(pk=config.token_id)
        except GoogleSheetsToken.DoesNotExist:
            pass

    return render(request, 'transport_sheet/settings.html', {
        'config': config,
        'available_tokens': available_tokens,
        'selected_token': selected_token,
    })
