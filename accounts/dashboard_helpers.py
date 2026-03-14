"""
Dashboard Helper Functions
Shared utility functions for dashboard views
"""

from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta

from projects.models import ProjectCode
from operations.models import DailySpaceUtilization
from operations.models_adhoc import AdhocBillingEntry
from operations.models_projectcard import ProjectCard


def get_coordinator_workload():
    """Get coordinator workload statistics"""
    from accounts.models import User

    coordinators = User.objects.filter(
        role='operation_coordinator',
        is_active=True
    )

    workload_data = []
    for coordinator in coordinators:
        coord_name = coordinator.get_full_name()
        project_count = ProjectCode.objects.filter(
            Q(operation_coordinator=coord_name) | Q(backup_coordinator=coord_name),
            project_status='Active'
        ).count()

        workload_data.append({
            'coordinator': coordinator,
            'project_count': project_count,
        })

    # Sort by project count descending
    workload_data.sort(key=lambda x: x['project_count'], reverse=True)

    return workload_data


def get_incomplete_project_cards_count():
    """
    Get count of active projects without project cards
    """
    active_project_ids = ProjectCode.objects.filter(
        project_status='Active'
    ).values_list('project_id', flat=True)
    
    projects_with_cards = ProjectCard.objects.filter(
        project_id__in=active_project_ids
    ).values_list('project_id', flat=True).distinct()
    
    return len(set(active_project_ids) - set(projects_with_cards))


def get_disputes_open_7days_count():
    """
    Get count of disputes open for more than 7 days
    """
    try:
        from operations.models import DisputeLog
        return DisputeLog.objects.filter(
            status__in=['open', 'in_progress'],
            opened_at__lt=timezone.now() - timedelta(days=7)
        ).count()
    except:
        return 0


def get_adhoc_pending_30days_count():
    """
    Get count of adhoc billing entries pending for more than 30 days
    """
    today = timezone.now().date()
    return AdhocBillingEntry.objects.filter(
        status='pending',
        event_date__lt=today - timedelta(days=30)
    ).count()


def get_missing_daily_entries_count():
    """
    Get count of active projects missing today's daily entry
    """
    today = timezone.now().date()
    try:
        active_projects_count = ProjectCode.objects.filter(project_status='Active').count()
        entries_today_count = DailySpaceUtilization.objects.filter(
            entry_date=today
        ).values('project_id').distinct().count()
        return max(0, active_projects_count - entries_today_count)
    except:
        return 0


def get_top_states_by_projects(limit=10):
    """
    Get top states by active project count
    """
    return ProjectCode.objects.filter(
        project_status='Active'
    ).values('state').annotate(
        count=Count('project_id')
    ).order_by('-count')[:limit]


def get_top_clients_by_projects(limit=10):
    """
    Get top clients by project count
    """
    return ProjectCode.objects.filter(
        project_status__in=['Active', 'Operation Not Started']
    ).values('client_name').annotate(
        project_count=Count('project_id')
    ).order_by('-project_count')[:limit]


def get_daily_entries_status(date):
    """
    Get daily entries status for a specific date
    """
    active_projects = ProjectCode.objects.filter(project_status='Active').count()
    entries_count = DailySpaceUtilization.objects.filter(
        entry_date=date
    ).values('project_id').distinct().count()
    
    return {
        'total': entries_count,
        'pending': active_projects - entries_count,
        'completion_rate': round((entries_count / active_projects * 100), 1) if active_projects > 0 else 0
    }


def get_monthly_billing_status():
    """
    Get monthly billing status
    """
    from operations.models import MonthlyBilling
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    
    return {
        'generated': MonthlyBilling.objects.filter(
            billing_month__gte=current_month_start,
            status='generated'
        ).count(),
        'sent': MonthlyBilling.objects.filter(
            billing_month__gte=current_month_start,
            status='sent'
        ).count(),
        'paid': MonthlyBilling.objects.filter(
            billing_month__gte=current_month_start,
            status='paid'
        ).count(),
    }


def get_disputes_summary():
    """
    Get disputes summary
    """
    try:
        from operations.models import DisputeLog
        return {
            'open': DisputeLog.objects.filter(status__in=['open', 'in_progress']).count(),
            'resolved_this_month': DisputeLog.objects.filter(
                status='resolved',
                resolved_at__gte=timezone.now().replace(day=1)
            ).count(),
        }
    except:
        return {'open': 0, 'resolved_this_month': 0}


def get_adhoc_billing_summary():
    """
    Get adhoc billing summary
    """
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    
    pending_count = AdhocBillingEntry.objects.filter(status='pending').count()
    approved_count = AdhocBillingEntry.objects.filter(
        status='approved',
        event_date__gte=current_month_start
    ).count()
    
    pending_amount = AdhocBillingEntry.objects.filter(
        status='pending'
    ).aggregate(total=Sum('total_client_amount'))['total'] or 0
    pending_amount = float(pending_amount) / 100000
    
    return {
        'pending': pending_count,
        'approved_this_month': approved_count,
        'pending_amount': pending_amount,
    }


def get_recent_escalations(limit=10):
    """
    Get recent escalations
    """
    try:
        from operations.models import Escalation
        return Escalation.objects.order_by('-created_at')[:limit]
    except:
        return []


def get_coordinator_performance():
    """
    Get coordinator performance metrics
    """
    from accounts.models import User
    
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    
    # Calculate working days
    working_days = 0
    current_date = current_month_start
    while current_date <= today:
        if current_date.weekday() != 6:  # Not Sunday
            working_days += 1
        current_date += timedelta(days=1)
    
    coordinators = User.objects.filter(role='operation_coordinator', is_active=True)
    performance = []
    
    for coord in coordinators[:10]:
        coord_name = coord.get_full_name()
        coord_projects = ProjectCode.objects.filter(
            Q(operation_coordinator=coord_name) | Q(backup_coordinator=coord_name),
            project_status='Active'
        )
        
        coord_entries = DailySpaceUtilization.objects.filter(
            project__in=coord_projects,
            entry_date__gte=current_month_start
        ).count()
        
        expected = coord_projects.count() * working_days
        completion_rate = round((coord_entries / expected * 100), 1) if expected > 0 else 0
        
        performance.append({
            'name': coord_name,
            'projects': coord_projects.count(),
            'entries': coord_entries,
            'completion_rate': completion_rate
        })
    
    return performance


def get_bigin_health_status():
    """
    Get Bigin CRM health status
    """
    # Placeholder - implement actual Bigin health check
    return {
        'status': 'healthy',
        'last_sync': timezone.now() - timedelta(hours=2)
    }


def get_tallysync_health_status():
    """
    Get TallySync health status
    """
    # Placeholder - implement actual TallySync health check
    return {
        'status': 'healthy',
        'last_sync': timezone.now() - timedelta(hours=1)
    }


def get_adobe_sign_health_status():
    """
    Get Adobe Sign health status
    """
    # Placeholder - implement actual Adobe Sign health check
    return {
        'status': 'healthy',
        'last_check': timezone.now() - timedelta(minutes=30)
    }


def get_bigin_last_sync():
    """
    Get Bigin last sync time
    """
    # Placeholder - implement actual sync time retrieval
    return timezone.now() - timedelta(hours=2)


def get_bigin_sync_status():
    """
    Get Bigin sync status
    """
    # Placeholder
    return 'success'


def get_bigin_leads_count():
    """
    Get Bigin leads count
    """
    # Placeholder
    return 0


def get_tallysync_last_sync():
    """
    Get TallySync last sync time
    """
    # Placeholder
    return timezone.now() - timedelta(hours=1)


def get_tallysync_vouchers_count():
    """
    Get TallySync vouchers count
    """
    # Placeholder
    return 0


def get_database_size():
    """
    Get database size in MB
    """
    # Placeholder - implement actual database size query
    return 450


def get_background_jobs_count():
    """
    Get background jobs count
    """
    # Placeholder - implement actual job count
    return {'running': 2, 'queued': 5}


def get_total_dropdown_count():
    """
    Get total dropdown count
    """
    try:
        from dropdown_master_data.models import DropdownMaster
        return DropdownMaster.objects.count()
    except:
        return 0


def get_recent_dropdown_updates(limit=5):
    """
    Get recent dropdown updates
    """
    try:
        from dropdown_master_data.models import DropdownMaster
        return DropdownMaster.objects.order_by('-updated_at')[:limit]
    except:
        return []


def get_total_files_count():
    """
    Get total files count in storage
    """
    # Placeholder - implement actual file count
    return 0


def get_storage_usage():
    """
    Get storage usage in MB
    """
    # Placeholder - implement actual storage usage
    return 0


def get_recent_uploads(limit=5):
    """
    Get recent file uploads
    """
    # Placeholder - implement actual recent uploads
    return []


def get_backup_status():
    """
    Get backup status
    """
    # Placeholder
    return {
        'last_backup': timezone.now() - timedelta(hours=2),
        'status': 'success',
        'size_mb': 125
    }


def get_recent_system_errors(limit=10):
    """
    Get recent system errors
    """
    # Placeholder - implement actual error log retrieval
    return []


def get_orphaned_records_count():
    """
    Get count of orphaned records
    """
    # Placeholder - implement actual orphaned records check
    return 0


def get_duplicate_records_count():
    """
    Get count of duplicate records
    """
    # Placeholder - implement actual duplicate check
    return 0


def get_missing_required_fields_count():
    """
    Get count of records with missing required fields
    """
    return get_incomplete_project_cards_count()


def get_invalid_data_formats_count():
    """
    Get count of records with invalid data formats
    """
    # Placeholder - implement actual validation check
    return 0