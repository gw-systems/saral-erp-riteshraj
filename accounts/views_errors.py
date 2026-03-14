import logging
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from datetime import timedelta
from .models import ErrorLog

logger = logging.getLogger(__name__)


@login_required
def error_list(request):
    """Browse all errors — Admin/Super User only"""
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, 'Access denied. Admin only.')
        return HttpResponse(status=403)

    # Filters
    show_resolved = request.GET.get('resolved', 'false')
    environment = request.GET.get('env', '')
    severity = request.GET.get('severity', '')
    source = request.GET.get('source', '')
    search = request.GET.get('search', '').strip()

    errors = ErrorLog.objects.select_related('request_user', 'resolved_by').all()

    if show_resolved == 'false':
        errors = errors.filter(resolved=False)
    elif show_resolved == 'true':
        errors = errors.filter(resolved=True)
    # 'all' shows everything

    if environment:
        errors = errors.filter(environment=environment)
    if severity:
        errors = errors.filter(severity=severity)
    if source:
        errors = errors.filter(source=source)
    if search:
        errors = errors.filter(
            Q(exception_type__icontains=search)
            | Q(request_path__icontains=search)
            | Q(exception_message__icontains=search)
        )

    # Stats — single aggregate query over full (unfiltered) set
    today = timezone.now().date()
    week_ago = timezone.now() - timedelta(days=7)
    _stats = ErrorLog.objects.aggregate(
        total_count=Count('id'),
        unresolved_count=Count('id', filter=Q(resolved=False)),
        today_count=Count('id', filter=Q(timestamp__date=today)),
        week_count=Count('id', filter=Q(timestamp__gte=week_ago)),
        error_count=Count('id', filter=Q(severity='error', resolved=False)),
        warning_count=Count('id', filter=Q(severity='warning', resolved=False)),
        caught_count=Count('id', filter=Q(source='caught', resolved=False)),
        unhandled_count=Count('id', filter=Q(source='unhandled', resolved=False)),
    )

    # Pagination
    paginator = Paginator(errors, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'total_count': _stats['total_count'],
        'unresolved_count': _stats['unresolved_count'],
        'today_count': _stats['today_count'],
        'week_count': _stats['week_count'],
        'error_count': _stats['error_count'],
        'warning_count': _stats['warning_count'],
        'caught_count': _stats['caught_count'],
        'unhandled_count': _stats['unhandled_count'],
        'show_resolved': show_resolved,
        'selected_env': environment,
        'selected_severity': severity,
        'selected_source': source,
        'search': search,
    }

    return render(request, 'accounts/error_list.html', context)


@login_required
def error_detail(request, error_id):
    """View single error details — Admin/Super User only"""
    if request.user.role not in ['admin', 'super_user']:
        messages.error(request, 'Access denied. Admin only.')
        return HttpResponse(status=403)

    error = get_object_or_404(ErrorLog, error_id=error_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'resolve':
            error.resolved = True
            error.resolved_at = timezone.now()
            error.resolved_by = request.user
            error.notes = request.POST.get('notes', '')
            error.save()
            messages.success(request, f'Error {error_id} marked as resolved.')
        elif action == 'unresolve':
            error.resolved = False
            error.resolved_at = None
            error.resolved_by = None
            error.save()
            messages.success(request, f'Error {error_id} reopened.')

    context = {'error': error}
    return render(request, 'accounts/error_detail.html', context)


@login_required
def resolve_all_errors(request):
    """AJAX: mark ALL unresolved errors as resolved"""
    if request.user.role not in ['admin', 'super_user']:
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    updated = ErrorLog.objects.filter(resolved=False).update(
        resolved=True,
        resolved_at=timezone.now(),
        resolved_by=request.user,
    )
    return JsonResponse({'success': True, 'count': updated})


@login_required
def resolve_error(request, error_id):
    """AJAX: toggle resolved/unresolved inline"""
    if request.user.role not in ['admin', 'super_user']:
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    error = get_object_or_404(ErrorLog, error_id=error_id)
    action = request.POST.get('action', 'resolve')

    if action == 'unresolve':
        error.resolved = False
        error.resolved_at = None
        error.resolved_by = None
        error.save(update_fields=['resolved', 'resolved_at', 'resolved_by'])
        return JsonResponse({'success': True, 'resolved': False})
    else:
        error.resolved = True
        error.resolved_at = timezone.now()
        error.resolved_by = request.user
        error.notes = request.POST.get('notes', '')
        error.save(update_fields=['resolved', 'resolved_at', 'resolved_by', 'notes'])
        return JsonResponse({
            'success': True,
            'resolved': True,
            'resolved_at': error.resolved_at.strftime('%d %b %Y, %H:%M'),
            'resolved_by': request.user.get_full_name() or request.user.username,
        })
