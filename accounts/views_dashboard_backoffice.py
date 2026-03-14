"""
Backoffice Dashboard View
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q

from projects.models import ProjectCode
from projects.models_document import ProjectDocument
from supply.models import VendorCard, VendorWarehouse
from projects.models_client import ClientCard
from operations.models_projectcard import ProjectCard
from operations.models_agreements import AgreementRenewalTracker, EscalationTracker


@login_required
def backoffice_dashboard(request):
    """
    Enhanced dashboard for backoffice users
    Focus: Data entry, project cards, agreement management, master data
    """
    if request.user.role not in ['backoffice', 'admin', 'director']:
        messages.error(request, "Access denied. Backoffice users only.")
        return redirect('accounts:dashboard')

    today = timezone.now().date()

    # ==================== PROJECT STATISTICS ====================

    # All projects (backoffice has access to ALL series)
    all_projects = ProjectCode.objects.filter(
        Q(project_status='Active') |
        Q(project_status='Operation Not Started') |
        Q(project_status='Notice Period')
    )

    _proj_agg = all_projects.aggregate(
        total_projects=Count('project_id'),
        active_projects_count=Count('project_id', filter=Q(project_status='Active')),
        notice_period_projects=Count('project_id', filter=Q(project_status='Notice Period')),
        not_started_projects=Count('project_id', filter=Q(project_status='Operation Not Started')),
    )
    total_projects = _proj_agg['total_projects']
    active_projects_count = _proj_agg['active_projects_count']
    notice_period_projects = _proj_agg['notice_period_projects']
    not_started_projects = _proj_agg['not_started_projects']

    # ==================== MASTER DATA STATISTICS (NEW) ====================

    # Gracefully handle supply app tables that may not exist in production yet
    try:
        total_vendors = VendorCard.objects.filter(vendor_is_active=True).count()
    except Exception:
        total_vendors = 0  # Table not deployed yet

    total_clients = ClientCard.objects.filter(client_is_active=True).count()

    try:
        total_warehouses = VendorWarehouse.objects.filter(warehouse_is_active=True).count()
    except Exception:
        total_warehouses = 0  # Table not deployed yet

    # ==================== PROJECT CARDS ====================
    # Filter: WAAS only, not Inactive

    # Active WAAS projects without project cards
    active_projects = ProjectCode.objects.filter(
        series_type='WAAS'
    ).exclude(project_status='Inactive')

    # Projects with project cards (WAAS, not Inactive)
    projects_with_project_cards = ProjectCard.objects.filter(
        project__series_type='WAAS'
    ).exclude(
        project__project_status='Inactive'
    ).values_list('project_id', flat=True).distinct()

    # Projects WITHOUT project cards
    projects_without_rate_card_qs = active_projects.exclude(
        project_id__in=projects_with_project_cards
    )

    projects_without_rate_card = projects_without_rate_card_qs.count()

    # Get list of projects without project cards (top 10)
    pending_rate_card_projects = projects_without_rate_card_qs.order_by('client_name')[:10]

    # ==================== INCOMPLETE PROJECT CARDS ====================

    # Count project cards with missing critical fields (WAAS, not Inactive)
    incomplete_cards_count = ProjectCard.objects.filter(
        project__series_type='WAAS'
    ).exclude(
        project__project_status='Inactive'
    ).filter(
        Q(agreement_start_date__isnull=True) |
        Q(agreement_end_date__isnull=True)
    ).count()

    # ==================== AGREEMENT RENEWALS ====================

    # Agreement renewals due in next 60 days
    sixty_days_from_now = today + timedelta(days=60)

    # Agreements expiring soon — WAAS only, not Inactive
    _expiring_qs = ProjectCard.objects.filter(
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period'],
        agreement_end_date__lte=sixty_days_from_now,
        agreement_end_date__gte=today
    ).select_related('project').order_by('agreement_end_date')
    agreements_expiring = _expiring_qs[:10]
    agreements_expiring_soon = _expiring_qs.count()

    # Agreements that have EXPIRED — WAAS only, not Inactive
    _expired_qs = ProjectCard.objects.filter(
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period'],
        agreement_end_date__lt=today
    ).select_related('project').order_by('agreement_end_date')
    expired_agreements = _expired_qs[:10]
    expired_agreements_count = _expired_qs.count()

    # ==================== ESCALATIONS ====================

    # Escalations due this year (60 days window) — WAAS only, not Inactive
    escalations_due_this_year = ProjectCard.objects.filter(
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period'],
        yearly_escalation_date__lte=sixty_days_from_now,
        yearly_escalation_date__gte=today
    ).count()

    # Escalations that are OVERDUE — WAAS only, not Inactive
    _overdue_esc_qs = ProjectCard.objects.filter(
        project__series_type='WAAS',
        project__project_status__in=['Active', 'Notice Period'],
        yearly_escalation_date__lt=today
    ).select_related('project').order_by('yearly_escalation_date')
    overdue_escalations = _overdue_esc_qs[:10]
    overdue_escalations_count = _overdue_esc_qs.count()

    # ==================== RENEWAL & ESCALATION TRACKER COUNTS ====================

    # Renewal Trackers — WAAS only, not Inactive
    _renewal_trackers = list(AgreementRenewalTracker.objects.filter(
        project_card__project__series_type='WAAS'
    ).exclude(
        project_card__project__project_status='Inactive'
    ).exclude(
        status__in=['renewed', 'cancelled', 'not_renewed']
    ).select_related('project_card__project'))
    total_renewals = len(_renewal_trackers)
    renewals_overdue = 0
    renewals_upcoming = 0
    for tracker in _renewal_trackers:
        if tracker.is_overdue:
            renewals_overdue += 1
        elif tracker.days_until_due and tracker.days_until_due <= 60:
            renewals_upcoming += 1

    # Escalation Trackers — WAAS only, not Inactive
    _escalation_trackers = list(EscalationTracker.objects.filter(
        project_card__project__series_type='WAAS'
    ).exclude(
        project_card__project__project_status='Inactive'
    ).exclude(
        status__in=['escalation_applied', 'cancelled']
    ).select_related('project_card__project'))
    total_escalations = len(_escalation_trackers)
    escalations_overdue_tracker = 0
    escalations_upcoming_tracker = 0
    for tracker in _escalation_trackers:
        if tracker.is_overdue:
            escalations_overdue_tracker += 1
        elif tracker.days_until_due and tracker.days_until_due <= 60:
            escalations_upcoming_tracker += 1

    # ==================== SYSTEM HEALTH SCORE ====================

    health_score = 100

    if projects_without_rate_card > 0:
        health_score -= min(20, projects_without_rate_card * 2)

    if incomplete_cards_count > 0:
        health_score -= min(15, incomplete_cards_count * 3)

    if renewals_overdue > 0:
        health_score -= min(30, renewals_overdue * 5)

    if escalations_overdue_tracker > 0:
        health_score -= min(20, escalations_overdue_tracker * 4)

    health_score = max(0, health_score)

    if health_score >= 90:
        health_status = 'excellent'
        health_color = 'green'
    elif health_score >= 75:
        health_status = 'good'
        health_color = 'blue'
    elif health_score >= 60:
        health_status = 'fair'
        health_color = 'yellow'
    else:
        health_status = 'needs_attention'
        health_color = 'red'

    # ==================== ADOBE SIGN E-SIGNATURE ====================

    # Adobe Sign statistics for backoffice
    try:
        from integrations.adobe_sign.models import AdobeAgreement
        # Adobe Sign counts — single aggregate instead of 8 separate queries
        _adobe_agg = AdobeAgreement.objects.filter(
            created_by=request.user
        ).aggregate(
            adobe_total_count=Count('id'),
            adobe_draft_count=Count('id', filter=Q(approval_status='DRAFT')),
            adobe_pending_count=Count('id', filter=Q(approval_status='PENDING_APPROVAL')),
            adobe_rejected_count=Count('id', filter=Q(approval_status='REJECTED')),
            adobe_client_agreement_count=Count('id', filter=Q(agreement_type__code='client_agreement')),
            adobe_sla_agreement_count=Count('id', filter=Q(agreement_type__code='sla_agreement')),
            adobe_addendum_client_count=Count('id', filter=Q(agreement_type__code='addendum_client')),
            adobe_addendum_3pl_count=Count('id', filter=Q(agreement_type__code='addendum_3pl')),
        )
        adobe_total_count = _adobe_agg['adobe_total_count']
        adobe_draft_count = _adobe_agg['adobe_draft_count']
        adobe_pending_count = _adobe_agg['adobe_pending_count']
        adobe_rejected_count = _adobe_agg['adobe_rejected_count']
        adobe_client_agreement_count = _adobe_agg['adobe_client_agreement_count']
        adobe_sla_agreement_count = _adobe_agg['adobe_sla_agreement_count']
        adobe_addendum_client_count = _adobe_agg['adobe_addendum_client_count']
        adobe_addendum_3pl_count = _adobe_agg['adobe_addendum_3pl_count']
    except Exception:
        adobe_draft_count = 0
        adobe_pending_count = 0
        adobe_rejected_count = 0
        adobe_total_count = 0
        adobe_client_agreement_count = 0
        adobe_sla_agreement_count = 0
        adobe_addendum_client_count = 0
        adobe_addendum_3pl_count = 0

    # ==================== DOCUMENT COMPLETENESS (WAAS) ====================

    waas_active = ProjectCode.objects.filter(
        series_type='WAAS'
    ).exclude(project_status='Inactive')

    projects_with_agreement = ProjectDocument.objects.exclude(
        project_agreement=''
    ).exclude(
        project_agreement__isnull=True
    ).values_list('project_id', flat=True)

    projects_with_addendum = ProjectDocument.objects.exclude(
        project_addendum_vendor=''
    ).exclude(
        project_addendum_vendor__isnull=True
    ).values_list('project_id', flat=True)

    missing_agreement_count = waas_active.exclude(
        project_id__in=projects_with_agreement
    ).count()

    missing_addendum_count = waas_active.exclude(
        project_id__in=projects_with_addendum
    ).count()

    # ==================== RECENT ACTIVITY ====================

    # All projects for table (recent 15)
    assigned_projects = ProjectCode.objects.filter(
        Q(project_status='Active') | Q(project_status='Operation Not Started')
    ).order_by('-updated_at')[:15]

    # ==================== CONTEXT ====================

    context = {
        'today': today,

        # PROJECT STATISTICS
        'total_projects': total_projects,
        'active_projects_count': active_projects_count,
        'notice_period_projects': notice_period_projects,
        'not_started_projects': not_started_projects,

        # MASTER DATA STATISTICS (NEW)
        'total_vendors': total_vendors,
        'total_clients': total_clients,
        'total_warehouses': total_warehouses,

        # PROJECT CARDS
        'projects_without_rate_card': projects_without_rate_card,
        'pending_rate_card_projects': pending_rate_card_projects,
        'incomplete_cards_count': incomplete_cards_count,

        # AGREEMENTS
        'agreements_expiring_soon': agreements_expiring_soon,
        'agreements_expiring': agreements_expiring,
        'expired_agreements': expired_agreements,
        'expired_agreements_count': expired_agreements_count,

        # ESCALATIONS
        'escalations_due_this_year': escalations_due_this_year,
        'overdue_escalations': overdue_escalations,
        'overdue_escalations_count': overdue_escalations_count,

        # TRACKERS
        'total_renewals': total_renewals,
        'renewals_overdue': renewals_overdue,
        'renewals_upcoming': renewals_upcoming,
        'total_escalations': total_escalations,
        'escalations_overdue_tracker': escalations_overdue_tracker,
        'escalations_upcoming_tracker': escalations_upcoming_tracker,

        # SYSTEM HEALTH
        'health_score': health_score,
        'health_status': health_status,
        'health_color': health_color,

        # RECENT ACTIVITY
        'assigned_projects': assigned_projects,

        # DOCUMENT COMPLETENESS
        'missing_agreement_count': missing_agreement_count,
        'missing_addendum_count': missing_addendum_count,

        # ADOBE SIGN E-SIGNATURE
        'adobe_draft_count': adobe_draft_count,
        'adobe_pending_count': adobe_pending_count,
        'adobe_rejected_count': adobe_rejected_count,
        'adobe_total_count': adobe_total_count,
        'adobe_client_agreement_count': adobe_client_agreement_count,
        'adobe_sla_agreement_count': adobe_sla_agreement_count,
        'adobe_addendum_client_count': adobe_addendum_client_count,
        'adobe_addendum_3pl_count': adobe_addendum_3pl_count,
    }

    return render(request, 'dashboards/backoffice_dashboard.html', context)
