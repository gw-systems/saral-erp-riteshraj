from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Sum, Count, Q, F, Case, When, IntegerField
from decimal import Decimal
from functools import wraps
from collections import defaultdict
from django.core.cache import cache
import logging
import json

from integrations.bigin.models import BiginRecord, BiginContact
from integrations.bigin.bigin_sync import fetch_contact_notes
from integrations.models import SyncLog
from integration_workers import create_task

logger = logging.getLogger(__name__)


# Rate limiting decorator
def rate_limit(limit=1, period=60):
    """
    Rate limit decorator - allows 'limit' requests per 'period' seconds per user.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return func(request, *args, **kwargs)

            cache_key = f"rate_limit_{func.__name__}_{request.user.id}"
            request_count = cache.get(cache_key, 0)

            if request_count >= limit:
                return JsonResponse({
                    'error': 'Rate limit exceeded. Please try again later.',
                    'retry_after': period
                }, status=429)

            cache.set(cache_key, request_count + 1, period)
            return func(request, *args, **kwargs)

        return wrapper
    return decorator


@login_required
@require_http_methods(["GET"])
def api_sales_lead_summary(request):
    """
    Get Bigin lead summary for logged-in sales manager
    
    Query Parameters:
    - start_date: YYYY-MM-DD (default: current month start)
    - end_date: YYYY-MM-DD (default: current month end)
    
    Filters:
    - contact_type = '3pl' only
    - If area_requirement = 0 or NULL → use 500 sqft
    
    Returns:
    - Status summary (Hot/Warm/Cold/Converted/Closed/Junk) with count + sqft
    - Stage summary with count + sqft
    """
    try:
        # Get salesperson name
        salesperson_name = request.GET.get('sales_manager') or request.user.get_full_name()
        
        if not salesperson_name:
            return JsonResponse({
                'error': 'User profile not complete'
            }, status=400)
        
        # Parse date parameters (default to current month)
        today = timezone.now().date()
        first_day_current_month = today.replace(day=1)
        
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'error': 'Invalid start_date format. Use YYYY-MM-DD'}, status=400)
        else:
            start_date = first_day_current_month
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'error': 'Invalid end_date format. Use YYYY-MM-DD'}, status=400)
        else:
            end_date = today
        
        # Validate date range
        if start_date > end_date:
            return JsonResponse({'error': 'start_date cannot be after end_date'}, status=400)
        
        # Base queryset: 3PL leads for this salesperson in date range
        leads = BiginRecord.objects.filter(
            owner=salesperson_name,
            contact_type='3pl',
            created_time__date__gte=start_date,
            created_time__date__lte=end_date
        )
        
        # Calculate effective area manually (area_requirement is CharField)
        def get_effective_area(area_str):
            """Convert area_requirement string to int, default 500 if empty/0"""
            try:
                area = int(area_str or 0)
                return 500 if area == 0 else area
            except (ValueError, TypeError):
                return 500
        
        # Materialize once — avoids N+1 from repeated status/stage filters
        leads_data = list(leads.only('status', 'area_requirement', 'lead_stage'))

        # Status Summary — Python filter over materialized list (0 extra DB queries)
        status_summary = {}
        status_fields = ['hot', 'warm', 'cold', 'converted', 'closed', 'junk']

        for status_value in status_fields:
            status_leads = [l for l in leads_data if status_value in (l.status or '').lower()]
            total_sqft = sum(get_effective_area(lead.area_requirement) for lead in status_leads)
            status_summary[status_value] = {
                'count': len(status_leads),
                'total_sqft': total_sqft
            }

        # Stage Summary — Python groupby (0 extra DB queries)
        stage_groups = defaultdict(list)
        for lead in leads_data:
            stage_groups[lead.lead_stage].append(lead)

        stage_summary = {}
        for stage_key, stage_leads in stage_groups.items():
            stage = stage_key or 'No Stage'
            total_sqft = sum(get_effective_area(lead.area_requirement) for lead in stage_leads)
            stage_summary[stage] = {
                'count': len(stage_leads),
                'total_sqft': total_sqft
            }

        # Total summary — Python (0 extra DB queries)
        total_leads = len(leads_data)
        total_sqft = sum(get_effective_area(lead.area_requirement) for lead in leads_data)
        
        response_data = {
            'summary': {
                'total_leads': total_leads,
                'total_sqft': total_sqft
            },
            'status_summary': status_summary,
            'stage_summary': stage_summary,
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_all_users_summary(request):
    """
    Get Bigin lead summary for ALL users combined (for CRM Executive)

    Query Parameters:
    - start_date: YYYY-MM-DD (default: current month start)
    - end_date: YYYY-MM-DD (default: current month end)

    Filters:
    - contact_type = '3pl' only
    - If area_requirement = 0 or NULL → use 500 sqft

    Returns:
    - Status summary (Hot/Warm/Cold/Converted/Closed/Junk) with count + sqft for ALL users
    - Stage summary with count + sqft for ALL users
    """
    try:
        # Parse date parameters (default to current month)
        today = timezone.now().date()
        first_day_current_month = today.replace(day=1)

        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'error': 'Invalid start_date format. Use YYYY-MM-DD'}, status=400)
        else:
            start_date = first_day_current_month

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'error': 'Invalid end_date format. Use YYYY-MM-DD'}, status=400)
        else:
            end_date = today

        # Validate date range
        if start_date > end_date:
            return JsonResponse({'error': 'start_date cannot be after end_date'}, status=400)

        # Base queryset: 3PL leads for ALL users in date range
        leads = BiginRecord.objects.filter(
            contact_type='3pl',
            created_time__date__gte=start_date,
            created_time__date__lte=end_date
        )

        # Calculate effective area manually (area_requirement is CharField)
        def get_effective_area(area_str):
            """Convert area_requirement string to int, default 500 if empty/0"""
            try:
                area = int(area_str or 0)
                return 500 if area == 0 else area
            except (ValueError, TypeError):
                return 500

        # Materialize once — avoids N+1 from repeated status/stage filters
        leads_data = list(leads.only('status', 'area_requirement', 'lead_stage'))

        # Status Summary — Python filter (0 extra DB queries)
        status_summary = {}
        status_fields = ['hot', 'warm', 'cold', 'converted', 'closed', 'junk']

        for status_value in status_fields:
            status_leads = [l for l in leads_data if status_value in (l.status or '').lower()]
            total_sqft = sum(get_effective_area(lead.area_requirement) for lead in status_leads)
            status_summary[status_value] = {
                'count': len(status_leads),
                'total_sqft': total_sqft
            }

        # Stage Summary — Hot + Warm only, Python groupby (0 extra DB queries)
        hot_warm_data = [
            l for l in leads_data
            if 'hot' in (l.status or '').lower() or 'warm' in (l.status or '').lower()
        ]

        stage_groups = defaultdict(list)
        for lead in hot_warm_data:
            stage_groups[lead.lead_stage].append(lead)

        stage_summary = {}
        for stage_key, stage_leads in stage_groups.items():
            stage = stage_key or 'No Stage'
            total_sqft = sum(get_effective_area(lead.area_requirement) for lead in stage_leads)
            stage_summary[stage] = {
                'count': len(stage_leads),
                'total_sqft': total_sqft
            }

        # Total summary — Python (0 extra DB queries)
        total_leads = len(leads_data)
        total_sqft = sum(get_effective_area(lead.area_requirement) for lead in leads_data)

        response_data = {
            'summary': {
                'total_leads': total_leads,
                'total_sqft': total_sqft
            },
            'status_summary': status_summary,
            'stage_summary': stage_summary,
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }

        return JsonResponse(response_data)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_area_breakdown(request):
    """
    Get Area Breakdown data for sales manager (used in sales_manager dashboard)

    Query Parameters:
    - start_date: YYYY-MM-DD (default: current month start)
    - end_date: YYYY-MM-DD (default: current month end)

    Filters:
    - owner = logged-in user's full name
    - contact_type = '3pl' only
    - If area_requirement = 0 or NULL → use 500 sqft

    Returns:
    - Area breakdown by range (Blanks, 0-1K, 1K-3K, etc.) for each status filter (All, Hot, Warm, Cold, Converted, Closed, Junk)
    """
    try:
        # Get salesperson name
        salesperson_name = request.user.get_full_name()

        if not salesperson_name:
            return JsonResponse({
                'error': 'User profile not complete'
            }, status=400)

        # Parse date parameters (default to current month)
        today = timezone.now().date()
        first_day_current_month = today.replace(day=1)

        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'error': 'Invalid start_date format. Use YYYY-MM-DD'}, status=400)
        else:
            start_date = first_day_current_month

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'error': 'Invalid end_date format. Use YYYY-MM-DD'}, status=400)
        else:
            end_date = today

        # Validate date range
        if start_date > end_date:
            return JsonResponse({'error': 'start_date cannot be after end_date'}, status=400)

        # Base queryset: 3PL leads for this salesperson in date range
        leads = BiginRecord.objects.filter(
            owner=salesperson_name,
            contact_type='3pl',
            created_time__date__gte=start_date,
            created_time__date__lte=end_date
        )

        # Calculate effective area manually (area_requirement is CharField)
        def get_effective_area(area_str):
            """Convert area_requirement string to int, default 500 if empty/0"""
            try:
                area = int(area_str or 0)
                return 500 if area == 0 else area
            except (ValueError, TypeError):
                return 500

        # Area ranges
        area_ranges = [
            ('blanks', None, None),
            ('range_0_1000', 0, 1000),
            ('range_1001_3000', 1001, 3000),
            ('range_3001_5000', 3001, 5000),
            ('range_5001_10000', 5001, 10000),
            ('range_10001_20000', 10001, 20000),
            ('range_20001_30000', 20001, 30000),
            ('range_30001_plus', 30001, 999999999),
        ]

        # Status filters
        status_filters = ['all', 'hot', 'warm', 'cold', 'converted', 'closed', 'junk']

        # Materialize once — avoids 1 + N_statuses DB queries
        leads_data = list(leads.only('status', 'area_requirement'))

        # Build breakdown data
        breakdown = {}

        for status_key in status_filters:
            # Filter leads by status in Python (0 extra DB queries)
            if status_key == 'all':
                status_leads = leads_data
            else:
                status_leads = [l for l in leads_data if status_key in (l.status or '').lower()]

            row_data = {}
            total_sqft = 0
            total_count = 0

            for range_key, min_area, max_area in area_ranges:
                if range_key == 'blanks':
                    # Blank/zero area requirements - count only, sqft always 0
                    range_leads = [lead for lead in status_leads if not lead.area_requirement or lead.area_requirement == '0']
                    range_count = len(range_leads)
                    range_sqft = 0  # Blanks always show 0 for sqft
                else:
                    # Regular ranges
                    range_leads = [lead for lead in status_leads if min_area <= get_effective_area(lead.area_requirement) <= max_area]
                    range_count = len(range_leads)
                    range_sqft = sum(get_effective_area(lead.area_requirement) for lead in range_leads)

                row_data[range_key + '_count'] = range_count
                row_data[range_key + '_sqft'] = range_sqft

                total_sqft += range_sqft
                total_count += range_count

            row_data['total_sqft'] = total_sqft
            row_data['total_count'] = total_count
            row_data['name'] = salesperson_name

            breakdown[status_key] = row_data

        response_data = {
            'breakdown': breakdown,
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        }

        return JsonResponse(response_data)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_owners_list(request):
    """
    Get list of distinct owners from BiginRecord

    Returns:
    - List of owner names
    """
    try:
        owners = BiginRecord.objects.filter(
            owner__isnull=False
        ).exclude(
            owner=''
        ).values_list('owner', flat=True).distinct().order_by('owner')

        return JsonResponse({
            'owners': list(owners)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@rate_limit(limit=1, period=60)
@require_http_methods(["POST", "GET"])
def trigger_bigin_sync(request):
    """
    Trigger Bigin sync for all modules.
    Designed to be called by Cloud Scheduler.

    Query Parameters:
    - full: true/false (default: false for incremental sync)

    Returns:
    - JSON with sync status
    """
    try:
        # Role-based access control
        if request.user.role not in ['admin', 'super_user', 'crm_executive', 'digital_marketing']:
            logger.warning(f"Unauthorized sync attempt by {request.user.username}")
            return JsonResponse({
                'error': 'Insufficient permissions'
            }, status=403)

        # Environment check: Disable auto-sync in local/development mode (optional)
        from django.conf import settings
        disable_sync_local = getattr(settings, 'DISABLE_BIGIN_SYNC_LOCAL', False)
        is_development = getattr(settings, 'DEBUG', False) and not getattr(settings, 'USE_CLOUD_TASKS', False)

        if disable_sync_local and is_development:
            logger.info(f"[API] Bigin sync skipped in local development (DISABLE_BIGIN_SYNC_LOCAL=True)")
            return JsonResponse({
                'status': 'skipped',
                'message': 'Bigin sync is disabled in local development mode. Set DISABLE_BIGIN_SYNC_LOCAL=False in settings to enable.',
                'timestamp': timezone.now().isoformat()
            })

        # Parse parameters
        run_full = request.GET.get('full', 'false').lower() == 'true'

        logger.info(f"[API] Starting Bigin sync (full={run_full}) triggered by {request.user.username}")

        # Pre-check: reject if another sync is already running — avoids unhandled thread exception
        from integrations.models import SyncLog as _SyncLog
        from datetime import timedelta as _td
        _STALE_MINUTES = 3
        _existing = _SyncLog.objects.filter(integration='bigin', log_kind='batch', status='running').first()
        if _existing:
            _stale_cutoff = timezone.now() - _td(minutes=_STALE_MINUTES)
            if _existing.last_updated >= _stale_cutoff:
                logger.warning("[API] Bigin sync rejected — another sync already running (ID: %s)", _existing.id)
                return JsonResponse({
                    'status': 'conflict',
                    'message': f'A sync is already running (started {_existing.started_at.strftime("%H:%M:%S")}). Please wait for it to finish.',
                    'sync_id': _existing.id,
                }, status=409)

        task_name = create_task(
            endpoint='/integrations/bigin/workers/sync-all-modules/',
            payload={
                'run_full': run_full,
                'triggered_by_user': request.user.username
            },
            task_name=f'bigin-sync-{int(timezone.now().timestamp())}',
            timeout=1800  # 30 minutes for Bigin sync
        )

        logger.info("[API] Bigin sync task created successfully")

        return JsonResponse({
            'status': 'success',
            'message': f'Bigin sync started ({"full" if run_full else "incremental"})',
            'task_name': task_name,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.exception("[API] Bigin sync failed")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
@require_http_methods(["POST"])
def trigger_module_sync(request):
    """
    Trigger Bigin sync for a single module.

    POST Parameters:
    - module: Module name (Contacts, Pipelines, Accounts, Products, Notes)
    - full: true/false (default: false for incremental sync)

    Returns:
    - JSON with sync status
    """
    try:
        # Get module from POST data
        module = request.POST.get('module')

        if not module:
            return JsonResponse({
                'error': 'module parameter is required'
            }, status=400)

        # Validate module name
        valid_modules = ['Contacts', 'Pipelines', 'Accounts', 'Products', 'Notes']
        module = module.capitalize()

        if module not in valid_modules:
            return JsonResponse({
                'error': f'Invalid module. Must be one of: {", ".join(valid_modules)}'
            }, status=400)

        # Parse full sync parameter
        run_full = request.POST.get('full', 'false').lower() == 'true'

        logger.info(f"[API] Starting {module} sync (full={run_full})")

        # Check for existing running syncs
        existing_sync = SyncLog.objects.filter(status='running').first()
        if existing_sync:
            return JsonResponse({
                'status': 'error',
                'error': f'Another sync is already running (started at {existing_sync.started_at})'
            }, status=400)

        # Create SyncLog entry for module sync
        sync_type = 'bigin_module'
        sync_log = SyncLog.objects.create(
            sync_type=sync_type,
            status='running',
            triggered_by='api',
            modules=[module],
            overall_progress_percent=0,
        )

        try:
            # Run the module sync
            from integrations.bigin.tasks import sync_module
            stats = sync_module(module, run_full=run_full, sync_log_id=sync_log.id)

            # Update sync log with results
            duration = (timezone.now() - sync_log.started_at).total_seconds()
            sync_log.status = 'completed' if stats['errors'] == 0 else 'partial'
            sync_log.completed_at = timezone.now()
            sync_log.duration_seconds = int(duration)
            sync_log.total_records_synced = stats['synced']
            sync_log.records_created = stats['created']
            sync_log.records_updated = stats['updated']
            sync_log.errors_count = stats['errors']
            sync_log.module_results = {module: stats}
            sync_log.overall_progress_percent = 100
            sync_log.current_module = None
            sync_log.save()

            logger.info(f"[API] {module} sync completed: {stats}")

            return JsonResponse({
                'status': 'success',
                'message': f'{module} sync completed ({"full" if run_full else "incremental"})',
                'sync_id': sync_log.id,
                'stats': stats,
                'timestamp': timezone.now().isoformat()
            })

        except Exception as e:
            # Mark sync as failed
            sync_log.status = 'failed'
            sync_log.completed_at = timezone.now()
            sync_log.duration_seconds = int((timezone.now() - sync_log.started_at).total_seconds())
            sync_log.error_message = str(e)
            sync_log.save()
            raise

    except Exception as e:
        logger.exception(f"[API] {module} sync failed")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
@require_http_methods(["POST", "GET"])
def trigger_token_refresh(request):
    """
    Trigger Bigin OAuth token refresh.
    Designed to be called by Cloud Scheduler.

    Returns:
    - JSON with refresh status
    """
    try:
        # Check for authorization header (optional security)
        auth_header = request.headers.get('Authorization')
        expected_token = getattr(timezone.get_current_timezone(), 'BIGIN_SYNC_TOKEN', None)

        # If token is configured, validate it
        if expected_token and auth_header != f"Bearer {expected_token}":
            logger.warning("Unauthorized token refresh attempt")
            return JsonResponse({
                'error': 'Unauthorized'
            }, status=401)

        logger.info("[API] Refreshing Bigin token")

        # Trigger Cloud Tasks worker
        task_name = create_task(
            endpoint='/integrations/bigin/workers/refresh-token/',
            payload={},
            task_name=f'bigin-token-refresh-{int(timezone.now().timestamp())}'
        )

        logger.info("[API] Token refresh task created successfully")

        return JsonResponse({
            'status': 'success',
            'message': 'Token refresh started',
            'task_name': task_name,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.exception("[API] Token refresh failed")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
@require_http_methods(["POST", "GET"])
def force_token_refresh(request):
    """
    Force Bigin OAuth token refresh (ignores expiry check).

    Returns:
    - JSON with refresh status
    """
    try:
        from integrations.bigin.models import BiginAuthToken
        from django.conf import settings
        import requests

        logger.info("[API] Force refreshing Bigin token")

        token = BiginAuthToken.objects.first()

        if not token:
            return JsonResponse({
                'error': 'No BiginAuthToken found - OAuth flow needed'
            }, status=400)

        # Force refresh token — use DB settings (priority) over env vars
        from integrations.bigin.utils.settings_helper import get_bigin_config
        bigin_cfg = get_bigin_config()
        data = {
            "refresh_token": token.refresh_token,
            "client_id": bigin_cfg['client_id'] or getattr(settings, 'ZOHO_CLIENT_ID', ''),
            "client_secret": bigin_cfg['client_secret'] or getattr(settings, 'ZOHO_CLIENT_SECRET', ''),
            "grant_type": "refresh_token",
        }

        token_url = bigin_cfg.get('token_url') or getattr(settings, 'ZOHO_TOKEN_URL', 'https://accounts.zoho.com/oauth/v2/token')
        response = requests.post(token_url, data=data)

        if response.status_code == 200:
            token_data = response.json()

            token.access_token = token_data.get("access_token")
            token.expires_at = timezone.now() + timedelta(seconds=token_data.get("expires_in", 3600))
            token.save()

            logger.info(f"[API] Token force refreshed successfully, expires at {token.expires_at}")

            return JsonResponse({
                'status': 'success',
                'message': 'Token force refreshed successfully',
                'access_token_preview': token.access_token[:20] + '...',
                'expires_at': token.expires_at.isoformat(),
                'is_expired': token.is_expired(),
                'timestamp': timezone.now().isoformat()
            })
        else:
            logger.error(f"[API] Token refresh failed: {response.text}")
            return JsonResponse({
                'status': 'error',
                'error': f'Token refresh failed: {response.text}',
                'timestamp': timezone.now().isoformat()
            }, status=500)

    except Exception as e:
        logger.exception("[API] Force token refresh failed")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
@require_http_methods(["POST"])
def manual_token_update(request):
    """
    Manually update Bigin OAuth tokens (access + refresh).

    POST Parameters:
    - access_token: The access token
    - refresh_token: The refresh token
    - expires_hours: Hours until expiry (default: 1)

    Returns:
    - JSON with update status
    """
    try:
        from integrations.bigin.models import BiginAuthToken

        access_token = request.POST.get('access_token')
        refresh_token = request.POST.get('refresh_token')
        expires_hours = int(request.POST.get('expires_hours', 1))

        if not access_token or not refresh_token:
            return JsonResponse({
                'error': 'Both access_token and refresh_token are required'
            }, status=400)

        logger.info("[API] Manually updating Bigin tokens")

        # Update token
        token, created = BiginAuthToken.objects.update_or_create(
            id=1,
            defaults={
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_at': timezone.now() + timedelta(hours=expires_hours)
            }
        )

        logger.info(f"[API] Token {'created' if created else 'updated'} successfully")

        return JsonResponse({
            'status': 'success',
            'message': f'Token {"created" if created else "updated"} successfully',
            'token_id': token.id,
            'expires_at': token.expires_at.isoformat(),
            'is_expired': token.is_expired(),
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.exception("[API] Manual token update failed")
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
@require_http_methods(["GET"])
def sync_history_api(request):
    """
    API endpoint to fetch sync history and summary stats.

    Returns:
    - summary: Overall stats (syncs today, success rate, etc.)
    - syncs: List of recent sync logs with details
    """
    try:
        # Check if user is admin
        if not request.user.is_superuser:
            return JsonResponse({
                'error': 'Access denied. Admin only.'
            }, status=403)

        # Get today's date range
        today = timezone.now().date()
        today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        today_end = timezone.make_aware(datetime.combine(today, datetime.max.time()))

        # Get syncs from last 24 hours for success rate
        last_24h = timezone.now() - timedelta(hours=24)

        # Calculate summary stats
        syncs_today = SyncLog.objects.filter(started_at__gte=today_start, started_at__lte=today_end).count()
        running_syncs = SyncLog.objects.filter(status='running').count()

        # Success rate (last 24 hours)
        last_24h_syncs = SyncLog.objects.filter(started_at__gte=last_24h)
        total_24h = last_24h_syncs.count()
        completed_24h = last_24h_syncs.filter(status='completed').count()
        success_rate = round((completed_24h / total_24h * 100), 1) if total_24h > 0 else 100.0

        # Total records synced today
        records_today = SyncLog.objects.filter(
            started_at__gte=today_start,
            started_at__lte=today_end
        ).aggregate(total=Sum('total_records_synced'))['total'] or 0

        # Last sync info
        last_sync = SyncLog.objects.order_by('-started_at').first()
        last_sync_type = last_sync.get_sync_type_display() if last_sync else 'None'
        last_sync_time = timezone.localtime(last_sync.started_at).strftime('%Y-%m-%d %H:%M') if last_sync else 'Never'

        # Get recent sync logs (last 50)
        recent_syncs = SyncLog.objects.order_by('-started_at')[:50]

        syncs_data = []
        for sync in recent_syncs:
            syncs_data.append({
                'id': sync.id,
                'sync_type': sync.sync_type,
                'sync_type_display': sync.get_sync_type_display(),
                'status': sync.status,
                'status_display': sync.get_status_display(),
                'started_at': timezone.localtime(sync.started_at).strftime('%Y-%m-%d %H:%M:%S'),
                'completed_at': timezone.localtime(sync.completed_at).strftime('%Y-%m-%d %H:%M:%S') if sync.completed_at else None,
                'duration_display': sync.duration_display,
                'total_records_synced': sync.total_records_synced,
                'records_created': sync.records_created,
                'records_updated': sync.records_updated,
                'errors_count': sync.errors_count,
                'success_rate': sync.success_rate,
                'modules': sync.modules,
                'module_results': sync.module_results,
                'error_message': sync.error_message,
                'triggered_by': sync.triggered_by,
                'triggered_by_user': sync.triggered_by_user,
            })

        response_data = {
            'summary': {
                'syncs_today': syncs_today,
                'running_syncs': running_syncs,
                'success_rate': success_rate,
                'records_today': records_today,
                'last_sync_type': last_sync_type,
                'last_sync_time': last_sync_time,
            },
            'syncs': syncs_data,
        }

        return JsonResponse(response_data)

    except Exception as e:
        logger.exception("[API] Sync history fetch failed")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def stop_sync_api(request):
    """
    Stop a running sync gracefully.

    POST Parameters:
    - sync_id: ID of the running sync to stop

    Returns:
    - JSON with stop status
    """
    try:
        sync_id = request.POST.get('sync_id')

        if not sync_id:
            return JsonResponse({
                'error': 'sync_id is required'
            }, status=400)

        # Get the sync log
        try:
            sync_log = SyncLog.objects.get(id=sync_id)
        except SyncLog.DoesNotExist:
            return JsonResponse({
                'error': f'Sync with ID {sync_id} not found'
            }, status=404)

        # Check if sync is running
        if sync_log.status != 'running':
            return JsonResponse({
                'error': f'Sync is not running (current status: {sync_log.status})'
            }, status=400)

        # Set stop flag
        sync_log.stop_requested = True
        sync_log.save()

        logger.info(f"[API] Stop requested for sync {sync_id}")

        return JsonResponse({
            'status': 'success',
            'message': 'Stop request sent. Sync will stop gracefully after current operation.',
            'sync_id': sync_id,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.exception("[API] Stop sync failed")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def force_stop_sync_api(request):
    """
    Force-stop a stale sync that didn't respond to graceful stop.
    Immediately marks it as stopped in the database.

    POST Parameters:
    - sync_id: ID of the sync to force-stop

    Returns:
    - JSON with force-stop status
    """
    try:
        sync_id = request.POST.get('sync_id')

        if not sync_id:
            return JsonResponse({
                'error': 'sync_id is required'
            }, status=400)

        # Get the sync log
        try:
            sync_log = SyncLog.objects.get(id=sync_id)
        except SyncLog.DoesNotExist:
            return JsonResponse({
                'error': f'Sync with ID {sync_id} not found'
            }, status=404)

        # Check if sync is running or stopping
        if sync_log.status not in ['running', 'stopping']:
            return JsonResponse({
                'error': f'Sync is not running (current status: {sync_log.status})'
            }, status=400)

        # Calculate elapsed time since last update
        elapsed_since_update = (timezone.now() - sync_log.last_updated).total_seconds()

        # Force stop immediately
        sync_log.status = 'stopped'
        sync_log.stop_requested = True
        sync_log.completed_at = timezone.now()
        duration = (timezone.now() - sync_log.started_at).total_seconds()
        sync_log.duration_seconds = int(duration)
        sync_log.error_message = f'Force-stopped after {int(duration)}s (stale for {int(elapsed_since_update)}s)'
        sync_log.save()

        logger.warning(f"[API] Force-stopped sync {sync_id} (was stale for {elapsed_since_update}s)")

        return JsonResponse({
            'status': 'success',
            'message': f'Sync force-stopped successfully. It was stale for {int(elapsed_since_update)} seconds.',
            'sync_id': sync_id,
            'elapsed_since_update': int(elapsed_since_update),
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.exception("[API] Force-stop sync failed")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def sync_progress_api(request):
    """
    Get real-time progress of the most recent Bigin sync.
    Returns flat format compatible with integrations hub frontend.
    """
    LEVEL_ICON = {
        'DEBUG': '🔍', 'INFO': 'ℹ️', 'SUCCESS': '✅',
        'WARNING': '⚠️', 'ERROR': '❌', 'CRITICAL': '🔥'
    }

    try:
        # Always fetch the most recent Bigin batch log (running OR completed/failed)
        batch_log = SyncLog.objects.filter(
            integration='bigin',
            log_kind='batch',
        ).order_by('-started_at').first()

        if not batch_log:
            return JsonResponse({
                'status': 'idle',
                'progress_percentage': 0,
                'message': 'No sync runs yet',
                'server_logs': [],
                'can_start': True,
                'can_stop': False,
            })

        # Build server_logs from operation logs
        server_logs = []
        try:
            op_logs = SyncLog.objects.filter(
                batch=batch_log,
                log_kind='operation',
            ).order_by('started_at')

            for op in op_logs:
                ts = timezone.localtime(op.started_at).strftime('%H:%M:%S')
                icon = LEVEL_ICON.get(op.level, '')
                line = f"[{ts}] {icon} {op.operation}"
                if op.message:
                    line += f": {op.message}"
                if op.duration_ms:
                    line += f" ({op.duration_ms}ms)"
                server_logs.append(line)
        except Exception as e:
            logger.error(f"[Bigin Progress] Failed to fetch operation logs: {e}")

        status = batch_log.status

        # Build human-readable message
        if status == 'running':
            current = batch_log.current_module or 'Syncing...'
            message = f"Syncing {current}..." if batch_log.current_module else 'Syncing...'
        elif status == 'completed':
            records = batch_log.records_created or 0
            message = f'✅ Sync complete — {records} records synced'
        elif status == 'failed':
            message = f'❌ Sync failed: {batch_log.error_message or "unknown error"}'
        elif status in ('stopped', 'stopping'):
            message = f'⏹️ Sync stopped'
        else:
            message = status

        return JsonResponse({
            'status': status,
            'progress_percentage': batch_log.overall_progress_percent or (100 if status == 'completed' else 0),
            'message': message,
            'current_status': message,
            'server_logs': server_logs,
            'can_start': status not in ['running', 'stopping'],
            'can_stop': status == 'running',
            'stop_requested': batch_log.stop_requested,
            'sync_id': batch_log.id,
            'current_module': batch_log.current_module,
            'records_created': batch_log.records_created or 0,
        })

    except Exception as e:
        logger.exception("[API] Bigin sync progress fetch failed")
        return JsonResponse({
            'error': str(e)
        }, status=500)

# =============================================================================
# BIGIN CRUD OPERATIONS API ENDPOINTS
# =============================================================================

@login_required
@require_http_methods(["POST"])
def create_bigin_contact(request):
    """
    Create a new contact in Bigin.
    
    POST body (JSON):
    {
        "First_Name": "John",
        "Last_Name": "Doe",
        "Email": "john@example.com",
        "Mobile": "+919876543210",
        "Type": "3pl",
        "Status": ["Hot"],
        "Area_Requirement": "5000"
    }
    
    Returns:
        JSON response with created record ID and details
    """
    import json
    from integrations.bigin.api_client import create_bigin_record
    from integrations.bigin.models import BiginContact
    
    try:
        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in create contact request: {str(e)}")
            return JsonResponse({
                'error': 'Invalid JSON format',
                'details': str(e)
            }, status=400)

        # Validate required fields
        required_fields = ['First_Name', 'Last_Name']
        for field in required_fields:
            if field not in data:
                return JsonResponse({
                    'error': f'Missing required field: {field}'
                }, status=400)
        
        # Create record in Bigin
        created_record = create_bigin_record('Contacts', data)
        
        # Sync back to local database
        bigin_id = created_record.get('id')
        if bigin_id:
            # Fetch full record details and save to DB
            from integrations.bigin.api_client import fetch_single_record
            full_record = fetch_single_record('Contacts', bigin_id)
            
            # Save to database
            BiginContact.objects.update_or_create(
                bigin_id=bigin_id,
                defaults={
                    'module': 'Contacts',
                    'full_name': full_record.get('data', [{}])[0].get('Full_Name', ''),
                    'email': full_record.get('data', [{}])[0].get('Email', ''),
                    'mobile': full_record.get('data', [{}])[0].get('Mobile', ''),
                    'owner': full_record.get('data', [{}])[0].get('Owner', {}).get('name', ''),
                    'contact_type': full_record.get('data', [{}])[0].get('Type', ''),
                    'status': ','.join(full_record.get('data', [{}])[0].get('Status', [])) if isinstance(full_record.get('data', [{}])[0].get('Status'), list) else full_record.get('data', [{}])[0].get('Status', ''),
                    'area_requirement': full_record.get('data', [{}])[0].get('Area_Requirement', ''),
                    'created_time': timezone.now(),
                    'modified_time': timezone.now(),
                }
            )
        
        logger.info(f"Successfully created Bigin contact: {bigin_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Contact created successfully in Bigin',
            'bigin_id': bigin_id,
            'record': created_record
        }, status=201)
        
    except ValueError as e:
        logger.error(f"Validation error creating contact: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Validation error',
            'details': str(e)
        }, status=400)
    except Exception as e:
        logger.error(f"Unexpected error creating contact: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': 'Internal server error',
            'details': str(e)
        }, status=500)
    except Exception as e:
        logger.exception("Error creating Bigin contact")
        return JsonResponse({
            'error': f'Failed to create contact: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["PUT", "PATCH"])
def update_bigin_contact(request, bigin_id):
    """
    Update an existing contact in Bigin.
    
    PUT /api/bigin/contacts/<bigin_id>/
    
    Body (JSON):
    {
        "Mobile": "+919876543211",
        "Status": ["Warm"],
        "Area_Requirement": "6000"
    }
    
    Returns:
        JSON response with update status
    """
    import json
    from integrations.bigin.api_client import update_bigin_record
    from integrations.bigin.models import BiginContact
    
    try:
        # Parse request body
        data = json.loads(request.body)
        
        if not data:
            return JsonResponse({
                'error': 'No update data provided'
            }, status=400)
        
        # Update record in Bigin
        updated_record = update_bigin_record('Contacts', bigin_id, data)
        
        # Update local database
        try:
            contact = BiginContact.objects.get(bigin_id=bigin_id)
            
            # Update fields that were changed
            if 'Mobile' in data:
                contact.mobile = data['Mobile']
            if 'Email' in data:
                contact.email = data['Email']
            if 'Status' in data:
                contact.status = ','.join(data['Status']) if isinstance(data['Status'], list) else data['Status']
            if 'Area_Requirement' in data:
                contact.area_requirement = data['Area_Requirement']
            if 'Type' in data:
                contact.contact_type = data['Type']
            
            contact.modified_time = timezone.now()
            contact.save()
            
        except BiginContact.DoesNotExist:
            logger.warning(f"Contact {bigin_id} not found in local DB, skipping local update")
        
        logger.info(f"Successfully updated Bigin contact: {bigin_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Contact updated successfully in Bigin',
            'bigin_id': bigin_id,
            'record': updated_record
        })
        
    except ValueError as e:
        logger.error(f"Validation error updating contact: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=400)
    except Exception as e:
        logger.exception(f"Error updating Bigin contact {bigin_id}")
        return JsonResponse({
            'error': f'Failed to update contact: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["DELETE"])
def delete_bigin_contact(request, bigin_id):
    """
    Delete a contact from Bigin.
    
    DELETE /api/bigin/contacts/<bigin_id>/
    
    Returns:
        JSON response with deletion status
    """
    from integrations.bigin.api_client import delete_bigin_record
    from integrations.bigin.models import BiginContact
    
    try:
        # Delete from Bigin
        delete_bigin_record('Contacts', bigin_id)
        
        # Delete from local database
        try:
            contact = BiginContact.objects.get(bigin_id=bigin_id)
            contact.delete()
            logger.info(f"Deleted contact {bigin_id} from local DB")
        except BiginContact.DoesNotExist:
            logger.warning(f"Contact {bigin_id} not found in local DB")
        
        logger.info(f"Successfully deleted Bigin contact: {bigin_id}")
        
        return JsonResponse({
            'success': True,
            'message': 'Contact deleted successfully from Bigin',
            'bigin_id': bigin_id
        })
        
    except ValueError as e:
        logger.error(f"Error deleting contact: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=400)
    except Exception as e:
        logger.exception(f"Error deleting Bigin contact {bigin_id}")
        return JsonResponse({
            'error': f'Failed to delete contact: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def bulk_create_bigin_contacts(request):
    """
    Create multiple contacts in Bigin (up to 100).
    
    POST body (JSON):
    {
        "contacts": [
            {
                "First_Name": "John",
                "Last_Name": "Doe",
                "Email": "john@example.com"
            },
            {
                "First_Name": "Jane",
                "Last_Name": "Smith",
                "Email": "jane@example.com"
            }
        ]
    }
    
    Returns:
        JSON response with created records
    """
    import json
    from integrations.bigin.api_client import bulk_create_bigin_records
    
    try:
        data = json.loads(request.body)
        contacts = data.get('contacts', [])
        
        if not contacts:
            return JsonResponse({
                'error': 'No contacts provided'
            }, status=400)
        
        if len(contacts) > 100:
            return JsonResponse({
                'error': 'Cannot create more than 100 contacts at once'
            }, status=400)
        
        # Bulk create in Bigin
        created_records = bulk_create_bigin_records('Contacts', contacts)
        
        logger.info(f"Bulk created {len(created_records)} contacts in Bigin")
        
        return JsonResponse({
            'success': True,
            'message': f'Successfully created {len(created_records)} contacts',
            'created_count': len(created_records),
            'records': created_records
        }, status=201)
        
    except ValueError as e:
        logger.error(f"Validation error in bulk create: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=400)
    except Exception as e:
        logger.exception("Error in bulk create contacts")
        return JsonResponse({
            'error': f'Failed to bulk create contacts: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["PUT"])
def bulk_update_bigin_contacts(request):
    """
    Update multiple contacts in Bigin (up to 100).
    Each contact must include 'id' field.
    
    PUT body (JSON):
    {
        "contacts": [
            {
                "id": "4876876000000123456",
                "Status": ["Hot"]
            },
            {
                "id": "4876876000000789012",
                "Status": ["Warm"]
            }
        ]
    }
    
    Returns:
        JSON response with update status
    """
    import json
    from integrations.bigin.api_client import bulk_update_bigin_records
    
    try:
        data = json.loads(request.body)
        contacts = data.get('contacts', [])
        
        if not contacts:
            return JsonResponse({
                'error': 'No contacts provided'
            }, status=400)
        
        if len(contacts) > 100:
            return JsonResponse({
                'error': 'Cannot update more than 100 contacts at once'
            }, status=400)
        
        # Validate all have ID
        for contact in contacts:
            if 'id' not in contact:
                return JsonResponse({
                    'error': 'All contacts must have "id" field for bulk update'
                }, status=400)
        
        # Bulk update in Bigin
        updated_records = bulk_update_bigin_records('Contacts', contacts)

        logger.info(f"Bulk updated {len(updated_records)} contacts in Bigin")

        return JsonResponse({
            'status': 'success',
            'count': len(updated_records),
            'records': updated_records
        })

    except Exception as e:
        logger.error(f"Bulk update failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_bigin_contact(request, bigin_id):
    """
    Get a single contact from local database by Bigin ID.

    GET /api/bigin/contacts/<bigin_id>/

    Returns:
    - JSON with contact details including notes
    """
    try:
        contact = BiginContact.objects.get(bigin_id=bigin_id, module='Contacts')

        # Fetch notes if not cached
        if not contact.notes or not contact.notes_fetched_at or \
           (timezone.now() - contact.notes_fetched_at).total_seconds() > 86400:  # 24 hours
            notes_data = fetch_contact_notes(bigin_id)
            contact.notes = notes_data
            contact.notes_fetched_at = timezone.now()
            contact.save(update_fields=['notes', 'notes_fetched_at'])

        return JsonResponse({
            'status': 'success',
            'contact': {
                'bigin_id': contact.bigin_id,
                'full_name': contact.full_name,
                'first_name': contact.first_name,
                'last_name': contact.last_name,
                'email': contact.email,
                'mobile': contact.mobile,
                'owner': contact.owner,
                'account_name': contact.account_name,
                'contact_type': contact.contact_type,
                'lead_source': contact.lead_source,
                'lead_stage': contact.lead_stage,
                'status': contact.status,
                'area_requirement': contact.area_requirement,
                'industry_type': contact.industry_type,
                'business_type': contact.business_type,
                'business_model': contact.business_model,
                'location': contact.location,
                'locations': contact.locations,
                'description': contact.description,
                'reason': contact.reason,
                'created_time': contact.created_time.isoformat() if contact.created_time else None,
                'modified_time': contact.modified_time.isoformat() if contact.modified_time else None,
                'last_activity_time': contact.last_activity_time.isoformat() if contact.last_activity_time else None,
                'notes': contact.notes,
                'raw': contact.raw,
            }
        })

    except BiginContact.DoesNotExist:
        return JsonResponse({
            'error': 'Contact not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Get contact failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': str(e)
        }, status=500)


# Existing code continues below...
@login_required
@require_http_methods(["POST"])
def bulk_delete_bigin_contacts(request):
    """
    Delete multiple contacts from Bigin (up to 100).

    POST body (JSON):
    {
        "ids": ["bigin_id_1", "bigin_id_2", ...]
    }

    Returns:
    - JSON with deletion summary
    """
    from integrations.bigin.api_client import delete_bigin_record

    try:
        data = json.loads(request.body)
        ids = data.get('ids', [])

        if not ids:
            return JsonResponse({
                'error': 'No contact IDs provided'
            }, status=400)

        if len(ids) > 100:
            return JsonResponse({
                'error': 'Cannot delete more than 100 contacts at once'
            }, status=400)

        success_count = 0
        failed_ids = []

        # Delete each contact
        for bigin_id in ids:
            try:
                # Delete from Bigin API
                delete_bigin_record('Contacts', bigin_id)

                # Delete from local database
                try:
                    contact = BiginContact.objects.get(bigin_id=bigin_id, module='Contacts')
                    contact.delete()
                except BiginContact.DoesNotExist:
                    pass  # Already deleted locally

                success_count += 1

            except Exception as e:
                logger.error(f"Failed to delete contact {bigin_id}: {str(e)}")
                failed_ids.append({
                    'id': bigin_id,
                    'error': str(e)
                })

        logger.info(f"Bulk deleted {success_count}/{len(ids)} contacts")

        return JsonResponse({
            'status': 'success',
            'deleted_count': success_count,
            'total_requested': len(ids),
            'failed': failed_ids
        })

    except Exception as e:
        logger.error(f"Bulk delete failed: {str(e)}", exc_info=True)
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_field_options(request):
    """
    Get dropdown options for contact form fields.
    Fetches data from Bigin API settings and local database.

    Returns:
        JSON with field options for all dropdowns
    """
    import requests
    from integrations.bigin.token_manager import get_valid_token
    from django.conf import settings

    try:
        # Get access token
        token = get_valid_token()
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json"
        }

        bigin_base = getattr(settings, "BIGIN_API_BASE", "https://bigin.zoho.com/api/v1/")

        # Fetch field metadata from Bigin
        url = f"{bigin_base}settings/fields?module=Contacts"
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()

        fields_data = resp.json().get('fields', [])

        # Extract picklist options
        options = {}

        for field in fields_data:
            api_name = field.get('api_name')
            if field.get('data_type') == 'picklist' and field.get('pick_list_values'):
                options[api_name] = [
                    {'value': v.get('actual_value'), 'label': v.get('display_value')}
                    for v in field.get('pick_list_values', [])
                    if not v.get('deleted', False)
                ]
            elif field.get('data_type') == 'multiselectpicklist' and field.get('pick_list_values'):
                options[api_name] = [
                    {'value': v.get('actual_value'), 'label': v.get('display_value')}
                    for v in field.get('pick_list_values', [])
                    if not v.get('deleted', False)
                ]

        # Get distinct values from database for additional fields
        from integrations.bigin.models import BiginContact

        # Get distinct owners
        owners = list(BiginContact.objects.filter(
            module='Contacts', owner__isnull=False
        ).values_list('owner', flat=True).distinct().order_by('owner'))

        # Get distinct locations (parse JSON arrays and comma-separated)
        locations_raw = BiginContact.objects.filter(
            module='Contacts', locations__isnull=False
        ).exclude(locations='').values_list('locations', flat=True).distinct()

        locations_set = set()
        for loc_str in locations_raw:
            if loc_str:
                try:
                    import json
                    if loc_str.startswith('['):
                        loc_list = json.loads(loc_str)
                        locations_set.update([l.strip() for l in loc_list if l and l.strip()])
                    else:
                        locations_set.update([l.strip() for l in loc_str.split(',') if l.strip()])
                except:
                    locations_set.update([l.strip() for l in loc_str.split(',') if l.strip()])

        locations = sorted(list(locations_set))

        # Get distinct reasons
        reasons = list(BiginContact.objects.filter(
            module='Contacts', reason__isnull=False
        ).exclude(reason='').values_list('reason', flat=True).distinct().order_by('reason'))

        # Combine with Bigin field options
        field_options = {
            'owners': [{'value': o, 'label': o} for o in owners],
            'contact_types': options.get('Type', [
                {'value': '3pl', 'label': '3PL'},
                {'value': 'warehouse', 'label': 'Warehouse'},
                {'value': 'logistic', 'label': 'Logistic'}
            ]),
            'lead_sources': options.get('Lead_Source', [
                {'value': 'Website', 'label': 'Website'},
                {'value': 'Referral', 'label': 'Referral'},
                {'value': 'LinkedIn', 'label': 'LinkedIn'},
                {'value': 'Cold Call', 'label': 'Cold Call'},
                {'value': 'Email Campaign', 'label': 'Email Campaign'},
                {'value': 'Other', 'label': 'Other'}
            ]),
            'statuses': options.get('Status', [
                {'value': 'Hot', 'label': 'Hot'},
                {'value': 'Warm', 'label': 'Warm'},
                {'value': 'Cold', 'label': 'Cold'},
                {'value': 'Converted', 'label': 'Converted'},
                {'value': 'Closed', 'label': 'Closed'},
                {'value': 'Junk', 'label': 'Junk'}
            ]),
            'lead_stages': options.get('Status_of_Action', []),
            'industry_types': options.get('Industry_Type', []),
            'business_types': options.get('Bussiness_Type', []),
            'business_models': options.get('Business_Model', []),
            'locations': [{'value': l, 'label': l} for l in locations],
            'reasons': [{'value': r, 'label': r} for r in reasons]
        }

        # Cache for 1 hour
        cache.set('bigin_field_options', field_options, 3600)

        return JsonResponse({
            'status': 'success',
            'options': field_options
        })

    except Exception as e:
        logger.error(f"Failed to fetch field options: {str(e)}", exc_info=True)

        # Return cached options if available
        cached = cache.get('bigin_field_options')
        if cached:
            return JsonResponse({
                'status': 'success',
                'options': cached,
                'cached': True
            })

        # Fallback to minimal defaults
        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'options': {
                'owners': [],
                'contact_types': [
                    {'value': '3pl', 'label': '3PL'},
                    {'value': 'warehouse', 'label': 'Warehouse'},
                    {'value': 'logistic', 'label': 'Logistic'}
                ],
                'lead_sources': [
                    {'value': 'Website', 'label': 'Website'},
                    {'value': 'Referral', 'label': 'Referral'},
                    {'value': 'LinkedIn', 'label': 'LinkedIn'},
                    {'value': 'Cold Call', 'label': 'Cold Call'},
                    {'value': 'Email Campaign', 'label': 'Email Campaign'},
                    {'value': 'Other', 'label': 'Other'}
                ],
                'statuses': [
                    {'value': 'Hot', 'label': 'Hot'},
                    {'value': 'Warm', 'label': 'Warm'},
                    {'value': 'Cold', 'label': 'Cold'},
                    {'value': 'Converted', 'label': 'Converted'},
                    {'value': 'Closed', 'label': 'Closed'},
                    {'value': 'Junk', 'label': 'Junk'}
                ],
                'lead_stages': [],
                'industry_types': [],
                'business_types': [],
                'business_models': [],
                'locations': [],
                'reasons': []
            }
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_contact_timeline(request, bigin_id):
    """
    Get timeline/audit trail for a contact.
    Fetches edit history from Bigin API.

    Returns:
        JSON with timeline events
    """
    import requests
    from integrations.bigin.token_manager import get_valid_token
    from django.conf import settings

    try:
        # Get access token
        token = get_valid_token()
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json"
        }

        bigin_base = getattr(settings, "BIGIN_API_BASE", "https://bigin.zoho.com/api/v1/")

        # Fetch timeline from Bigin (audit log)
        url = f"{bigin_base}Contacts/{bigin_id}/actions/timeline"
        resp = requests.get(url, headers=headers, timeout=20)

        if resp.status_code == 404:
            # Timeline API might not be available, fallback to basic info
            from integrations.bigin.models import BiginContact
            contact = BiginContact.objects.get(bigin_id=bigin_id, module='Contacts')

            timeline = []
            if contact.created_time:
                timeline.append({
                    'type': 'created',
                    'timestamp': contact.created_time.isoformat(),
                    'user': contact.raw.get('Created_By', {}).get('name', 'Unknown'),
                    'details': 'Contact created'
                })
            if contact.modified_time:
                timeline.append({
                    'type': 'modified',
                    'timestamp': contact.modified_time.isoformat(),
                    'user': contact.raw.get('Modified_By', {}).get('name', 'Unknown'),
                    'details': 'Contact modified'
                })

            return JsonResponse({
                'status': 'success',
                'timeline': timeline,
                'limited': True
            })

        resp.raise_for_status()
        timeline_data = resp.json().get('timeline', [])

        # Format timeline
        timeline = []
        for event in timeline_data:
            timeline.append({
                'type': event.get('action', 'update'),
                'timestamp': event.get('time', ''),
                'user': event.get('done_by', {}).get('name', 'Unknown'),
                'details': event.get('details', ''),
                'field': event.get('field_name', ''),
                'old_value': event.get('previous_value', ''),
                'new_value': event.get('current_value', '')
            })

        # Cache timeline for 5 minutes
        cache.set(f'contact_timeline_{bigin_id}', timeline, 300)

        return JsonResponse({
            'status': 'success',
            'timeline': timeline
        })

    except Exception as e:
        logger.error(f"Failed to fetch timeline for {bigin_id}: {str(e)}", exc_info=True)

        # Try to get from cache
        cached = cache.get(f'contact_timeline_{bigin_id}')
        if cached:
            return JsonResponse({
                'status': 'success',
                'timeline': cached,
                'cached': True
            })

        return JsonResponse({
            'status': 'error',
            'error': str(e),
            'timeline': []
        }, status=500)
