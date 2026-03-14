"""
CRM Executive Dashboard View
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth

from accounts.models import User
from projects.models import ProjectCode
from integrations.bigin.models import BiginRecord
from operations.models import MonthlyBilling


@login_required
def crm_executive_dashboard(request):
    """
    CRM Executive Dashboard - Lead Management & Conversion Focus
    Access: CRM Executive, Admin, Director
    Shows: All leads from Bigin + personal projects (if any) (WAAS/SAAS only, no GW)
    """
    if request.user.role not in ['crm_executive', 'admin', 'director']:
        messages.error(request, "Access denied. CRM Executive, Admin, or Director access required.")
        return redirect('accounts:dashboard')

    user_full_name = request.user.get_full_name()
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    thirty_days_ago = today - timedelta(days=30)

    # ==================== PERSONAL PROJECTS (IF SALES MANAGER) - WAAS/SAAS ONLY ====================

    my_projects = ProjectCode.objects.filter(
        sales_manager=user_full_name,
        series_type__in=['WAAS', 'SAAS']  # Exclude GW
    )

    my_projects_count = my_projects.count()
    my_active_projects = my_projects.filter(project_status='Active').count()

    # Personal MTD Revenue (if has projects)
    my_mtd_revenue = 0
    if my_projects_count > 0:
        my_billing = MonthlyBilling.objects.filter(
            project__in=my_projects,
            billing_month__gte=current_month_start,
            status='approved'
        ).aggregate(revenue=Sum('client_total'))
        my_mtd_revenue = float(my_billing['revenue'] or 0) / 100000

    # ==================== ALL LEADS (BIGIN) ====================

    all_contacts = BiginRecord.objects.filter(module='Contacts')
    all_leads = all_contacts.filter(contact_type='Lead')

    total_leads = all_leads.count()

    # Leads by Status
    open_leads = all_leads.filter(status__in=['New', 'Open', 'In Progress', 'Follow Up']).count()
    qualified_leads = all_leads.filter(lead_stage='Qualified').count()
    converted_leads = all_leads.filter(status='Converted').count()
    lost_leads = all_leads.filter(status__in=['Lost', 'Dead', 'Closed']).count()

    # ==================== LEAD CONVERSION STATS ====================

    # This month
    leads_created_this_month = all_contacts.filter(
        contact_type='Lead',
        created_time__gte=current_month_start
    ).count()

    leads_converted_this_month = all_contacts.filter(
        contact_type='Lead',
        status='Converted',
        modified_time__gte=current_month_start
    ).count()

    conversion_rate = (leads_converted_this_month / leads_created_this_month * 100) if leads_created_this_month > 0 else 0

    # Average deal size (placeholder - needs Deal data)
    avg_deal_size = 0

    # ==================== LEAD SOURCE BREAKDOWN ====================

    leads_by_source = all_contacts.filter(
        contact_type='Lead'
    ).values('lead_source').annotate(
        count=Count('id')
    ).order_by('-count')[:5]

    # ==================== LEAD AGING ====================

    aged_leads = []

    old_leads = all_contacts.filter(
        contact_type='Lead',
        status__in=['New', 'Open', 'In Progress', 'Follow Up'],
        created_time__lt=thirty_days_ago
    ).order_by('created_time')[:10]

    for lead in old_leads:
        days_old = (today - lead.created_time.date()).days if lead.created_time else 0

        aged_leads.append({
            'bigin_id': lead.bigin_id,
            'full_name': lead.full_name,
            'account_name': lead.account_name,
            'lead_source': lead.lead_source,
            'status': lead.status,
            'days_old': days_old,
            'owner': lead.owner,
            'location': lead.location or lead.locations
        })

    # ==================== RECENT LEADS ====================

    recent_leads = []

    latest_leads = all_contacts.filter(
        contact_type='Lead'
    ).order_by('-created_time')[:10]

    for lead in latest_leads:
        recent_leads.append({
            'bigin_id': lead.bigin_id,
            'full_name': lead.full_name,
            'account_name': lead.account_name,
            'email': lead.email,
            'mobile': lead.mobile,
            'lead_source': lead.lead_source,
            'status': lead.status,
            'lead_stage': lead.lead_stage,
            'owner': lead.owner,
            'created_time': lead.created_time,
            'location': lead.location or lead.locations,
            'area_requirement': lead.area_requirement
        })

    # ==================== HOT LEADS (FOLLOW UP TODAY) ====================

    # Placeholder - needs custom field or activity tracking
    hot_leads_count = 0

    # ==================== BIGIN LEAD SUMMARY ====================

    # Helper function to extract sqft from area_requirement string
    def extract_sqft(area_str):
        if not area_str:
            return 0
        import re
        # Try to extract numbers from strings like "5000 sqft", "5000-10000", etc.
        numbers = re.findall(r'\d+', str(area_str).replace(',', ''))
        if numbers:
            return int(numbers[0])
        return 0

    # All leads
    all_leads = BiginRecord.objects.filter(module='Contacts', contact_type='Lead')

    # Hot/Warm/Converted Leads — use values_list to avoid loading full model instances
    _lead_status_data = all_leads.filter(
        status__in=['Hot', 'Warm', 'Converted']
    ).values_list('status', 'area_requirement')

    _lead_status_counts = {'Hot': 0, 'Warm': 0, 'Converted': 0}
    _lead_status_sqft = {'Hot': 0, 'Warm': 0, 'Converted': 0}
    for status, area_req in _lead_status_data:
        _lead_status_counts[status] = _lead_status_counts.get(status, 0) + 1
        _lead_status_sqft[status] = _lead_status_sqft.get(status, 0) + extract_sqft(area_req)

    hot_leads_count = _lead_status_counts['Hot']
    hot_leads_sqft = _lead_status_sqft['Hot']
    warm_leads_count = _lead_status_counts['Warm']
    warm_leads_sqft = _lead_status_sqft['Warm']
    converted_leads_count = _lead_status_counts['Converted']
    converted_leads_sqft = _lead_status_sqft['Converted']

    # Lead Stage Breakdown — 1 batch query for sqft per stage instead of N
    lead_stages = all_leads.values('lead_stage').annotate(
        count=Count('id')
    ).order_by('-count')

    # Pre-fetch all area_requirements grouped by lead_stage in 1 query
    _stage_areas = {}
    for row in all_leads.values_list('lead_stage', 'area_requirement'):
        _stage_areas.setdefault(row[0], []).append(row[1])

    lead_stage_summary = []
    for stage in lead_stages:
        stage_sqft = sum(extract_sqft(a) for a in _stage_areas.get(stage['lead_stage'], []))
        lead_stage_summary.append({
            'stage': stage['lead_stage'] or 'Not Set',
            'count': stage['count'],
            'sqft': stage_sqft
        })

    # ==================== MONTHLY TREND (Last 6 Months) ====================

    # Monthly trend — 2 batch queries instead of 12
    _crm_six_months_ago = (current_month_start - timedelta(days=5*30)).replace(day=1)

    _crm_created_by_month = dict(
        all_contacts.filter(
            contact_type='Lead',
            created_time__gte=_crm_six_months_ago,
        ).annotate(
            month=TruncMonth('created_time')
        ).values('month').annotate(cnt=Count('id')).values_list('month', 'cnt')
    )

    _crm_converted_by_month = dict(
        all_contacts.filter(
            contact_type='Lead',
            status='Converted',
            modified_time__gte=_crm_six_months_ago,
        ).annotate(
            month=TruncMonth('modified_time')
        ).values('month').annotate(cnt=Count('id')).values_list('month', 'cnt')
    )

    lead_trend = []
    for i in range(5, -1, -1):
        month_date = (current_month_start - timedelta(days=i*30)).replace(day=1)
        # TruncMonth returns aware datetime — try both
        from datetime import datetime as _dt
        _month_key_naive = _dt(month_date.year, month_date.month, 1)
        _month_key_aware = timezone.make_aware(_month_key_naive) if timezone.is_naive(_month_key_naive) else _month_key_naive

        created = _crm_created_by_month.get(_month_key_aware, 0) or _crm_created_by_month.get(_month_key_naive, 0) or _crm_created_by_month.get(month_date, 0)
        converted = _crm_converted_by_month.get(_month_key_aware, 0) or _crm_converted_by_month.get(_month_key_naive, 0) or _crm_converted_by_month.get(month_date, 0)

        lead_trend.append({
            'month': month_date.strftime('%b'),
            'created': created,
            'converted': converted,
            'conversion_rate': (converted / created * 100) if created > 0 else 0
        })

    # ==================== LEADS BY LOCATION ====================

    leads_by_location = all_contacts.filter(
        contact_type='Lead',
        status__in=['New', 'Open', 'In Progress', 'Follow Up']
    ).exclude(
        Q(location__isnull=True) & Q(locations__isnull=True)
    ).values('location').annotate(
        count=Count('id')
    ).order_by('-count')[:5]

    # ==================== CONTEXT ====================

    context = {
        'today': today,
        'user_name': user_full_name,

        # Personal Projects
        'my_projects_count': my_projects_count,
        'my_active_projects': my_active_projects,
        'my_mtd_revenue': round(my_mtd_revenue, 2),

        # Lead Stats
        'total_leads': total_leads,
        'open_leads': open_leads,
        'qualified_leads': qualified_leads,
        'converted_leads': converted_leads,
        'lost_leads': lost_leads,

        # Conversion
        'leads_created_this_month': leads_created_this_month,
        'leads_converted_this_month': leads_converted_this_month,
        'conversion_rate': round(conversion_rate, 1),
        'avg_deal_size': avg_deal_size,

        # Lead Breakdown
        'leads_by_source': leads_by_source,
        'leads_by_location': leads_by_location,

        # Aged Leads
        'aged_leads': aged_leads,
        'aged_leads_count': len(aged_leads),

        # Recent Leads
        'recent_leads': recent_leads,

        # Hot Leads
        'hot_leads_count': hot_leads_count,

        # Bigin Lead Summary
        'hot_leads_count': hot_leads_count,
        'hot_leads_sqft': hot_leads_sqft,
        'warm_leads_count': warm_leads_count,
        'warm_leads_sqft': warm_leads_sqft,
        'converted_leads_count': converted_leads_count,
        'converted_leads_sqft': converted_leads_sqft,
        'lead_stage_summary': lead_stage_summary,

        # Trends
        'lead_trend': lead_trend,
    }

    return render(request, 'dashboards/crm_executive_dashboard.html', context)
