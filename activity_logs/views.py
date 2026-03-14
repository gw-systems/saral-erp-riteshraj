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
