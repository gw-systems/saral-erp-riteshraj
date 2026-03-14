from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count, Avg, Min, Max
from django.http import JsonResponse
from datetime import datetime, timedelta
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import calendar
import logging
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

from accounts.notifications import (
    notify_dispute_raised,
    notify_dispute_assigned,
    notify_dispute_resolved,
)

from .models import (
    DailySpaceUtilization,
    DailyEntryAuditLog,
    WarehouseHoliday,
    DailyMISLog,
    DisputeLog,
    DisputeComment,
    DisputeActivity,
)
from projects.models import ProjectCode
from .models_adhoc import AdhocBillingEntry
from dropdown_master_data.models import StorageUnit, ActivityType



User = get_user_model()

def get_coordinator_workload():
    """Get coordinator workload statistics (2 batch queries instead of N+1)"""
    from django.contrib.auth import get_user_model
    from projects.models import ProjectCode
    from django.db.models import Q
    from collections import defaultdict

    User = get_user_model()
    coordinators = User.objects.filter(
        role='operation_coordinator',
        is_active=True
    )
    coord_names = {c.get_full_name(): c for c in coordinators}

    if not coord_names:
        return []

    # Single batch query for all coordinator project counts
    _proj_rows = ProjectCode.objects.filter(
        Q(operation_coordinator__in=coord_names.keys()) | Q(backup_coordinator__in=coord_names.keys()),
        project_status__in=['Active', 'Operation Not Started', 'Notice Period']
    ).values_list('operation_coordinator', 'backup_coordinator')

    _counts = defaultdict(int)
    for op_c, bk_c in _proj_rows:
        if op_c in coord_names:
            _counts[op_c] += 1
        if bk_c in coord_names:
            _counts[bk_c] += 1

    workload_data = [
        {
            'coordinator': coord_names[name],
            'coordinator_id': coord_names[name].id,
            'project_count': _counts.get(name, 0),
        }
        for name in coord_names
    ]

    workload_data.sort(key=lambda x: x['project_count'], reverse=True)
    return workload_data


def get_coordinator_projects(coordinator):
    """Get projects assigned to a coordinator"""
    from projects.models import ProjectCode
    from django.db.models import Q
    
    coord_name = coordinator.get_full_name()
    return ProjectCode.objects.filter(
        Q(operation_coordinator=coord_name) | Q(backup_coordinator=coord_name),
        project_status__in=['Active', 'Operation Not Started', 'Notice Period']
    )


def get_problem_coordinators(threshold=100):
    """
    Identify coordinators who are behind schedule based on their daily entry completion.

    Uses batch queries instead of per-coordinator loops (was O(2N) queries, now O(3)).

    Args:
        threshold: Percentage threshold (0-100). Coordinators below this are flagged.

    Returns:
        List of dicts with coordinator info and their status
    """
    from django.db.models import Q, Count
    from datetime import timedelta, date
    from collections import defaultdict
    from accounts.models import User
    from operations.models import DailySpaceUtilization
    from projects.models import ProjectCode
    from operations.performance import calculate_working_days

    today = date.today()
    days_to_check = 10
    start_date = today - timedelta(days=days_to_check)
    working_days = calculate_working_days(start_date, today)

    if working_days == 0:
        return []

    # Query 1: All active coordinators
    coordinators = User.objects.filter(
        role__in=['Operations Coordinator', 'Operations Coordinator (Backup)'],
        is_active=True
    )
    coord_by_name = {c.get_full_name(): c for c in coordinators}

    if not coord_by_name:
        return []

    # Query 2: All active projects with coordinator names — single query
    active_projects = ProjectCode.objects.filter(
        project_status__in=['Active', 'Operation Not Started', 'Notice Period']
    ).filter(
        Q(operation_coordinator__in=coord_by_name.keys()) |
        Q(backup_coordinator__in=coord_by_name.keys())
    ).values_list('id', 'operation_coordinator', 'backup_coordinator')

    # Build coordinator_name → set of project_ids mapping
    coord_projects = defaultdict(set)
    all_project_ids = set()
    for pid, op_coord, bk_coord in active_projects:
        all_project_ids.add(pid)
        if op_coord in coord_by_name:
            coord_projects[op_coord].add(pid)
        if bk_coord in coord_by_name:
            coord_projects[bk_coord].add(pid)

    if not all_project_ids:
        return []

    # Query 3: Entry counts grouped by project — single query
    entry_counts = dict(
        DailySpaceUtilization.objects.filter(
            project_id__in=all_project_ids,
            entry_date__gte=start_date,
            entry_date__lte=today,
        ).values('project_id').annotate(cnt=Count('id')).values_list('project_id', 'cnt')
    )

    # Compute compliance per coordinator in Python (no more DB queries)
    problem_coordinators = []
    for coord_name, user in coord_by_name.items():
        pids = coord_projects.get(coord_name)
        if not pids:
            continue

        expected = working_days * len(pids)
        actual = sum(entry_counts.get(pid, 0) for pid in pids)
        completion_rate = (actual / expected) * 100 if expected > 0 else 0

        if completion_rate < threshold:
            if completion_rate < 50:
                status = 'critical'
            elif completion_rate < 75:
                status = 'warning'
            else:
                status = 'attention'

            problem_coordinators.append({
                'coordinator': user,
                'compliance': completion_rate,
                'total_projects': len(pids),
                'missing_count': expected - actual,
                'status': status,
            })

    problem_coordinators.sort(key=lambda x: x['compliance'])
    return problem_coordinators


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_user_projects(user):
    """Get projects visible to user based on role - MAIN PROJECTS ONLY for coordinators"""
    if user.role in ['operation_coordinator', 'warehouse_manager']:
        # Coordinators see only their MAIN assigned projects (no backup)
        user_full_name = user.get_full_name()
        return ProjectCode.objects.filter(
            operation_coordinator=user_full_name,
            project_status='Active'
        ).order_by('client_name', 'project_code')  # FIXED: Direct field
    
    elif user.role == 'operation_manager':
        # MANAGERS SEE ALL PROJECTS (system-wide oversight)
        return ProjectCode.objects.filter(
            project_status='Active'
        ).order_by('client_name', 'project_code')  # FIXED
    
    elif user.role in ['admin', 'super_user', 'operation_controller', 'backoffice']:
        # Controllers and admins see ALL projects
        return ProjectCode.objects.filter(
            project_status='Active'
        ).order_by('client_name', 'project_code')  # FIXED
    
    else:
        # Other roles see no projects
        return ProjectCode.objects.none()


def is_holiday(date, project=None):
    """Check if date is a holiday"""
    if date.weekday() == 6:  # Sunday
        return True
    
    # Check project-specific holidays
    if project:
        if WarehouseHoliday.objects.filter(
            project=project,
            holiday_date=date
        ).exists():
            return True
    
    # Check national/regional holidays
    return WarehouseHoliday.objects.filter(
        Q(holiday_type='national') | Q(project__isnull=True),
        holiday_date=date
    ).exists()

def get_user_role(user):
    """Safely get user role"""
    try:
        return user.profile.role.role_name
    except AttributeError:
        return 'unknown'


# ============================================================================
# DAILY ENTRY VIEWS
# ============================================================================

@login_required
def daily_entry_list(request):
    """Dashboard showing entries with search, filters, and date selection"""
    user = request.user
    projects = get_user_projects(user)
    
    # Get date from query params or default to today
    selected_date_str = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = timezone.now().date()
    
    # Single search parameter
    search_query = request.GET.get('search', '').strip()
    
    # Get entries for selected date
    entries = DailySpaceUtilization.objects.filter(
        project__in=projects,
        entry_date=selected_date
    ).select_related('project', 'entered_by')
    
    # Apply search filter (searches across client, vendor, location, project code)
    if search_query:
        entries = entries.filter(
            Q(project__client_name__icontains=search_query) |
            Q(project__vendor_name__icontains=search_query) |
            Q(project__location__icontains=search_query) |
            Q(project__project_code__icontains=search_query)
        )
    
    # Order by project for grouping
    entries = entries.order_by('project__client_name', 'project__project_code', '-entry_date')
    
    # Group entries by project for history view
    from itertools import groupby

    # Pre-fetch history for all projects in 1 query instead of N
    _entry_projects = list({e.project for e in entries})
    _history_cutoff = selected_date - timedelta(days=30)
    _all_history = DailySpaceUtilization.objects.filter(
        project__in=_entry_projects,
        entry_date__lte=selected_date,
        entry_date__gte=_history_cutoff,
    ).order_by('project_id', '-entry_date')

    # Group history by project_id in Python
    from collections import defaultdict
    _history_by_project = defaultdict(list)
    for h in _all_history:
        if len(_history_by_project[h.project_id]) < 10:  # Limit to 10 per project
            _history_by_project[h.project_id].append(h)

    grouped_entries = []
    for project, project_entries in groupby(entries, key=lambda x: x.project):
        entries_list = list(project_entries)
        history = _history_by_project.get(project.project_id, [])

        grouped_entries.append({
            'project': project,
            'latest_entry': entries_list[0] if entries_list else None,
            'history': history,
            'history_count': len(history)
        })
    
    today = timezone.now().date()
    is_sunday = selected_date.weekday() == 6
    
    context = {
        'projects': projects,
        'grouped_entries': grouped_entries,
        'selected_date': selected_date,
        'today': today,
        'is_sunday': is_sunday,
        'search_query': search_query,
    }
    return render(request, 'operations/daily_entry_list.html', context)


@login_required
def daily_entry_single(request):
    """Single project entry form - INCLUDES BACKUP PROJECTS, sorted alphabetically"""
    user = request.user
    user_name = user.get_full_name()
    
    # Get projects - MAIN + BACKUP, sorted alphabetically by client name
    projects = ProjectCode.objects.filter(
        Q(operation_coordinator=user_name) | Q(backup_coordinator=user_name),
        project_status='Active'
    ).order_by('client_name', 'project_code')  # FIXED: Direct field
    
    if request.method == 'POST':
        project_id = request.POST.get('project_id')
        entry_date = request.POST.get('entry_date')
        space_utilized = request.POST.get('space_utilized')
        inventory_value = request.POST.get('inventory_value')
        remarks = request.POST.get('remarks', '')
        unit_code = request.POST.get('unit')  # Get unit code directly from form

        try:
            # Verify user has access to this project (main OR backup coordinator)
            project = ProjectCode.objects.get(
                Q(project_id=project_id) &
                (Q(operation_coordinator=user_name) | Q(backup_coordinator=user_name))
            )

            # Check if entry already exists
            existing = DailySpaceUtilization.objects.filter(
                project=project,
                entry_date=entry_date
            ).first()

            if existing:
                messages.error(request, f"Entry already exists for {project.project_code} on {entry_date}")
                return redirect('operations:daily_entry_single')

            # Get StorageUnit instance from code
            try:
                unit_instance = StorageUnit.objects.get(code=unit_code)
            except StorageUnit.DoesNotExist:
                unit_instance = StorageUnit.objects.get(code='sqft')  # Fallback to sqft

            # Create entry
            entry = DailySpaceUtilization.objects.create(
                project=project,
                entry_date=entry_date,
                space_utilized=space_utilized,
                unit=unit_instance,
                inventory_value=inventory_value,
                remarks=remarks,
                entered_by=user
            )
            
            # Create audit log
            DailyEntryAuditLog.objects.create(
                daily_entry=entry,
                action='CREATED',
                changed_by=user,
                new_values={
                    'space_utilized': str(space_utilized),
                    'unit': unit_code or 'sqft',
                    'inventory_value': str(inventory_value),
                    'remarks': remarks
                }
            )
            
            messages.success(request, f"✅ Entry created successfully for {project.project_code}")
            return redirect('operations:daily_entry_list')
            
        except ProjectCode.DoesNotExist:
            messages.error(request, "❌ You don't have access to this project")
            return redirect('operations:daily_entry_single')
        except Exception as e:
            messages.error(request, f"❌ Error creating entry: {str(e)}")
    
    context = {
        'projects': projects,
        'today': timezone.now().date(),
    }
    return render(request, 'operations/daily_entry_single.html', context)


@login_required
def daily_entry_bulk(request):
    """Bulk entry form - ONLY MAIN COORDINATOR PROJECTS (no backup)"""
    user = request.user
    user_name = user.get_full_name()
    
    # Get view preference
    view_mode = request.GET.get('view', 'my_projects')
    
    # Filter projects based on role and view mode
    if user.role == 'operation_coordinator':
        # CHANGE: Coordinators see ONLY their main projects (no backup)
        projects = ProjectCode.objects.filter(
            operation_coordinator=user_name,
            project_status__in=['Active', 'Operation Not Started', 'Notice Period']
        ).order_by('client_name', 'project_code')  # FIXED: Direct field, no relation
        view_mode = 'my_projects'
        show_toggle = False
        
    elif user.role == 'operation_manager':
        # Managers can toggle
        if view_mode == 'my_projects':
            projects = ProjectCode.objects.filter(
                Q(sales_manager=user_name) | Q(operation_coordinator=user_name),
                project_status__in=['Active', 'Operation Not Started', 'Notice Period']
            ).order_by('client_name', 'project_code')  # FIXED
        else:
            projects = ProjectCode.objects.filter(
                project_status__in=['Active', 'Operation Not Started', 'Notice Period']
            ).order_by('client_name', 'project_code')  # FIXED
        show_toggle = True
        
    else:
        # Controllers, admin see all with toggle
        projects = ProjectCode.objects.filter(
            project_status__in=['Active', 'Operation Not Started', 'Notice Period']
        ).order_by('client_name', 'project_code')  # FIXED
        show_toggle = True
    
    if request.method == 'POST':
        entry_date = request.POST.get('entry_date')
        success_count = 0
        error_count = 0
        errors = []

        for project in projects:
            space_key = f'space_{project.project_id}'
            unit_key = f'unit_{project.project_id}'
            inventory_key = f'inventory_{project.project_id}'
            remarks_key = f'remarks_{project.project_id}'

            space_utilized = request.POST.get(space_key)
            unit_code = request.POST.get(unit_key)  # Get unit code directly from form
            inventory_value = request.POST.get(inventory_key)
            remarks = request.POST.get(remarks_key, '')

            if not space_utilized and not inventory_value:
                continue

            try:
                existing = DailySpaceUtilization.objects.filter(
                    project=project,
                    entry_date=entry_date
                ).first()

                if existing:
                    error_count += 1
                    errors.append(f"{project.project_code} - already exists")
                    continue

                # Fetch the StorageUnit instance
                try:
                    unit_instance = StorageUnit.objects.get(code=unit_code)
                except StorageUnit.DoesNotExist:
                    unit_instance = StorageUnit.objects.get(code='sqft')  # Fallback to sqft

                entry = DailySpaceUtilization.objects.create(
                    project=project,
                    entry_date=entry_date,
                    space_utilized=space_utilized or 0,
                    unit=unit_instance,
                    inventory_value=inventory_value or 0,
                    remarks=remarks,
                    entered_by=user
                )

                DailyEntryAuditLog.objects.create(
                    daily_entry=entry,
                    action='CREATED',
                    changed_by=user,
                    new_values={
                        'space_utilized': str(space_utilized or 0),
                        'unit': unit_code,
                        'inventory_value': str(inventory_value or 0),
                        'remarks': remarks
                    }
                )

                success_count += 1

            except Exception as e:
                error_count += 1
                errors.append(f"{project.project_code} - {str(e)}")
        
        if success_count > 0:
            messages.success(request, f"✅ Successfully created {success_count} entries")
        if error_count > 0:
            messages.warning(request, f"⚠️ {error_count} entries skipped: {', '.join(errors[:3])}")
        
        return redirect('operations:daily_entry_list')
    
    context = {
        'projects': projects,
        'today': timezone.now().date(),
        'view_mode': view_mode,
        'show_toggle': show_toggle,
    }
    return render(request, 'operations/daily_entry_bulk.html', context)


@login_required
def daily_entry_edit(request, entry_id):
    """Edit existing daily entry (within 5 days only)"""
    entry = get_object_or_404(DailySpaceUtilization, id=entry_id)
    user = request.user

    # Check if editable (within 5 days)
    days_old = (timezone.now().date() - entry.entry_date).days
    if days_old > 5:
        messages.error(request, "Entry is older than 5 days and cannot be edited")
        return redirect('operations:daily_entry_list')

    # Check permissions
    if user.role == 'operation_coordinator':
        user_projects = get_user_projects(user)
        if entry.project not in user_projects:
            messages.error(request, "You don't have permission to edit this entry")
            return redirect('operations:daily_entry_list')
    
    if request.method == 'POST':
        old_values = {
            'space_utilized': str(entry.space_utilized),
            'unit': entry.unit.code if entry.unit else 'sqft',
            'inventory_value': str(entry.inventory_value),
            'remarks': entry.remarks
        }

        unit_code = request.POST.get('unit')  # Get unit code directly from form

        # Get StorageUnit instance
        try:
            unit_instance = StorageUnit.objects.get(code=unit_code)
        except StorageUnit.DoesNotExist:
            unit_instance = StorageUnit.objects.get(code='sqft')  # Fallback

        entry.space_utilized = request.POST.get('space_utilized')
        entry.unit = unit_instance
        entry.inventory_value = request.POST.get('inventory_value')
        entry.remarks = request.POST.get('remarks', '')
        entry.last_modified_by = user
        entry.save()

        # Audit log
        DailyEntryAuditLog.objects.create(
            daily_entry=entry,
            action='UPDATED',
            changed_by=user,
            old_values=old_values,
            new_values={
                'space_utilized': str(entry.space_utilized),
                'unit': unit_instance.code,
                'inventory_value': str(entry.inventory_value),
                'remarks': entry.remarks
            }
        )
        
        messages.success(request, "Entry updated successfully")
        return redirect('operations:daily_entry_list')
    
    context = {
        'entry': entry,
    }
    return render(request, 'operations/daily_entry_edit.html', context)


@login_required
def daily_entry_bulk_edit(request):
    """Bulk edit existing entries for a specific date"""
    user = request.user
    projects = get_user_projects(user)
    
    # Get date from query params or default to today
    date_str = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        target_date = timezone.now().date()
    
    if request.method == 'POST':
        updated_count = 0
        created_count = 0

        for project in projects:
            space_key = f'space_{project.project_id}'
            unit_key = f'unit_{project.project_id}'
            inventory_key = f'inventory_{project.project_id}'
            remarks_key = f'remarks_{project.project_id}'

            space_value = request.POST.get(space_key)
            unit_value = request.POST.get(unit_key)
            inventory_value = request.POST.get(inventory_key)
            remarks = request.POST.get(remarks_key, '')

            # Skip if both are empty
            if not space_value and not inventory_value:
                continue

            # Mapping from display labels to StorageUnit codes
            # Get unit code directly (dropdown now sends codes, not labels)
            unit_code = unit_value if unit_value else 'sqft'

            # Get StorageUnit instance
            try:
                unit_instance = StorageUnit.objects.get(code=unit_code)
            except StorageUnit.DoesNotExist:
                unit_instance = StorageUnit.objects.get(code='sqft')  # Fallback

            # Get or create entry
            entry, created = DailySpaceUtilization.objects.get_or_create(
                project=project,
                entry_date=target_date,
                defaults={
                    'space_utilized': space_value or 0,
                    'unit': unit_instance,
                    'inventory_value': inventory_value or 0,
                    'remarks': remarks,
                    'entered_by': user
                }
            )

            if not created:
                # Update existing entry
                entry.space_utilized = space_value or 0
                entry.unit = unit_instance
                entry.inventory_value = inventory_value or 0
                entry.remarks = remarks
                entry.entered_by = user
                entry.updated_at = timezone.now()
                entry.save()
                updated_count += 1
            else:
                created_count += 1
        
        if created_count > 0 or updated_count > 0:
            messages.success(
                request, 
                f'✅ Successfully updated {updated_count} and created {created_count} entries for {target_date.strftime("%B %d, %Y")}'
            )
        else:
            messages.warning(request, 'No changes were made.')
        
        return redirect('operations:daily_entry_list')
    
    # GET request - load existing entries
    existing_entries = {}
    entries = DailySpaceUtilization.objects.filter(
        project__in=projects,
        entry_date=target_date
    ).select_related('project')

    for entry in entries:
        unit_code = entry.unit.code if entry.unit else 'sqft'
        existing_entries[entry.project.project_id] = {
            'space_utilized': entry.space_utilized,
            'inventory_value': entry.inventory_value,
            'remarks': entry.remarks,
            'unit': unit_code,  # Send code directly since dropdown uses codes
        }
    
    context = {
        'projects': projects,
        'target_date': target_date,
        'today': timezone.now().date(),
        'existing_entries': existing_entries,
    }
    
    return render(request, 'operations/daily_entry_bulk_edit.html', context)


@login_required
def daily_entry_history(request, project_id):
    """
    Complete history of daily space utilization entries for a specific project.
    Shows ALL entries with pagination, date filter, search, and statistics.
    """
    user = request.user

    # Get project and verify access
    project = get_object_or_404(ProjectCode, project_id=project_id)

    # Permission check - user must have access to this project
    user_projects = get_user_projects(user)
    if project not in user_projects:
        messages.error(request, "You don't have permission to view this project's history.")
        return redirect('operations:daily_entry_list')

    # Get date filters from query params
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    search_query = request.GET.get('search', '').strip()

    # Base queryset - all entries for this project
    entries = DailySpaceUtilization.objects.filter(
        project=project
    ).select_related('entered_by', 'last_modified_by', 'unit').order_by('-entry_date')

    # Apply date filters
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            entries = entries.filter(entry_date__gte=start_date)
        except ValueError:
            messages.warning(request, "Invalid start date format.")

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            entries = entries.filter(entry_date__lte=end_date)
        except ValueError:
            messages.warning(request, "Invalid end date format.")

    # Apply search filter (search in remarks)
    if search_query:
        entries = entries.filter(remarks__icontains=search_query)

    # Calculate statistics
    stats = entries.aggregate(
        total_entries=Count('id'),
        avg_space=Avg('space_utilized'),
        min_space=Min('space_utilized'),
        max_space=Max('space_utilized'),
        avg_inventory=Avg('inventory_value'),
        min_inventory=Min('inventory_value'),
        max_inventory=Max('inventory_value')
    )

    # Pagination
    paginator = Paginator(entries, 50)  # 50 entries per page
    page = request.GET.get('page')

    try:
        paginated_entries = paginator.page(page)
    except PageNotAnInteger:
        paginated_entries = paginator.page(1)
    except EmptyPage:
        paginated_entries = paginator.page(paginator.num_pages)

    context = {
        'project': project,
        'entries': paginated_entries,
        'stats': stats,
        'total_count': entries.count(),
        'start_date': start_date_str,
        'end_date': end_date_str,
        'search_query': search_query,
        'today': timezone.now().date(),
    }

    return render(request, 'operations/daily_entry_history.html', context)


@login_required
def daily_entry_all_history(request):
    """
    View all daily space utilization history with project dropdown selector.
    Shows history for selected project with role-based access control.
    """
    user = request.user

    # Get all projects user has access to
    user_projects = get_user_projects(user)

    # Get selected project from query params
    selected_project_id = request.GET.get('project_id')
    selected_project = None
    entries = DailySpaceUtilization.objects.none()
    stats = {}

    if selected_project_id:
        # Verify user has access to selected project
        try:
            selected_project = ProjectCode.objects.get(project_id=selected_project_id)
            if selected_project not in user_projects:
                messages.error(request, "You don't have permission to view this project's history.")
                selected_project = None
        except ProjectCode.DoesNotExist:
            messages.error(request, "Project not found.")
            selected_project = None

    # If project is selected and accessible, fetch entries
    if selected_project:
        # Get date filters from query params
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        search_query = request.GET.get('search', '').strip()

        # Base queryset
        entries = DailySpaceUtilization.objects.filter(
            project=selected_project
        ).select_related('entered_by', 'last_modified_by', 'unit').order_by('-entry_date')

        # Apply date filters
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                entries = entries.filter(entry_date__gte=start_date)
            except ValueError:
                messages.warning(request, "Invalid start date format.")

        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                entries = entries.filter(entry_date__lte=end_date)
            except ValueError:
                messages.warning(request, "Invalid end date format.")

        # Apply search filter
        if search_query:
            entries = entries.filter(remarks__icontains=search_query)

        # Calculate statistics
        stats = entries.aggregate(
            total_entries=Count('id'),
            avg_space=Avg('space_utilized'),
            min_space=Min('space_utilized'),
            max_space=Max('space_utilized'),
        )

        # Pagination
        paginator = Paginator(entries, 50)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
    else:
        page_obj = None
        start_date_str = None
        end_date_str = None
        search_query = None

    context = {
        'user_projects': user_projects.order_by('client_name', 'project_code'),
        'selected_project': selected_project,
        'page_obj': page_obj,
        'stats': stats,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'search_query': search_query,
        'today': timezone.now().date(),
    }

    return render(request, 'operations/daily_entry_all_history.html', context)


# ============================================================================
# MIS TRACKING VIEWS
# ============================================================================

@login_required
def mis_dashboard(request):
    """
    MIS Tracking Dashboard with date filter and search
    Shows: MIS Daily (Mon-Sat), MIS Weekly (Saturdays), MIS Monthly (last 2 days of month)
    Excludes: Inciflo, MIS Automode, MIS Not Required, Backup Projects
    """
    from django.utils import timezone
    from projects.models import ProjectCode
    from operations.models import DailyMISLog
    from django.db.models import Q
    from datetime import timedelta, datetime
    from calendar import monthrange
    from itertools import groupby
    
    user = request.user
    
    # Get date from query params or default to today
    selected_date_str = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = timezone.now().date()
    
    today = timezone.now().date()
    
    # Search parameter
    search_query = request.GET.get('search', '').strip()

    # Frequency filter parameter
    frequency_filter = request.GET.get('frequency', '').strip()

    # Base queryset - Active + Notice Period projects with valid MIS status
    base_projects = ProjectCode.objects.filter(
        project_status__in=['Active', 'Notice Period']
    ).exclude(
        Q(mis_status__isnull=True) |
        Q(mis_status='') |
        Q(mis_status__iexact='inciflo') |
        Q(mis_status__iexact='MIS Automode') |
        Q(mis_status__iexact='MIS Not Required')
    )
    
    # Filter by role - ONLY MAIN COORDINATOR (NO BACKUP)
    if user.role == 'operation_coordinator':
        user_name = user.get_full_name()
        projects = base_projects.filter(
            operation_coordinator=user_name  # ONLY main coordinator
        )
    elif user.role in ['operation_manager', 'operation_controller', 'admin', 'backoffice']:
        projects = base_projects
    else:
        messages.error(request, 'Access denied.')
        return redirect('accounts:dashboard')
    
    # Apply search filter
    if search_query:
        projects = projects.filter(
            Q(client_name__icontains=search_query) |
            Q(vendor_name__icontains=search_query) |
            Q(location__icontains=search_query) |
            Q(project_code__icontains=search_query)
        )

    # Apply frequency filter
    if frequency_filter:
        projects = projects.filter(mis_status__iexact=frequency_filter)

    # Sort by client name
    projects = projects.order_by('client_name', 'project_code')
    
    # Determine what should be sent on selected date
    is_sunday = selected_date.weekday() == 6
    is_saturday = selected_date.weekday() == 5
    
    # Calculate if it's month-end period (last 2 days)
    last_day = monthrange(selected_date.year, selected_date.month)[1]
    is_month_end_period = selected_date.day >= (last_day - 1)

    # Build MIS data with grouping
    grouped_mis_data = []
    
    for project in projects:
        # Determine if MIS is due on selected date
        should_send_today = False

        # Get MIS status code from dropdown
        mis_status_raw = project.mis_status or 'MIS Daily'
        mis_status_code = mis_status_raw.lower().replace(' ', '_')

        if mis_status_code == 'mis_daily' and not is_sunday:
            should_send_today = True
        elif mis_status_code == 'mis_weekly' and is_saturday:
            should_send_today = True
        elif mis_status_code == 'mis_monthly' and is_month_end_period:
            should_send_today = True

        # Get selected date's MIS log
        selected_date_log = DailyMISLog.objects.filter(
            project=project,
            log_date=selected_date
        ).first()
        
        # Get last 30 days history for this project
        history = DailyMISLog.objects.filter(
            project=project,
            log_date__lte=selected_date,
            log_date__gte=selected_date - timedelta(days=30)
        ).select_related('sent_by').order_by('-log_date')[:10]
        
        
        grouped_mis_data.append({
            'project': project,
            'frequency': project.mis_status if project.mis_status else 'MIS Daily',
            'should_send_today': should_send_today,
            'sent_today': selected_date_log.mis_sent if selected_date_log else False,
            'sent_by': selected_date_log.sent_by if selected_date_log else None,
            'selected_date_log': selected_date_log,
            'coordinator': project.operation_coordinator,
            'history': history,
            'history_count': history.count()
        })
    
    # Filter by status (for backward compatibility with existing filters)
    filter_status = request.GET.get('status', '')
    if filter_status == 'sent':
        grouped_mis_data = [m for m in grouped_mis_data if m['sent_today']]
    elif filter_status == 'pending':
        grouped_mis_data = [m for m in grouped_mis_data if m['should_send_today'] and not m['sent_today']]

    sent_count = sum(1 for item in grouped_mis_data if item['sent_today'])
    pending_count = sum(1 for item in grouped_mis_data if item['should_send_today'] and not item['sent_today'])
    
    context = {
        'grouped_mis_data': grouped_mis_data,
        'selected_date': selected_date,
        'today': today,
        'is_sunday': is_sunday,
        'is_saturday': is_saturday,
        'is_month_end_period': is_month_end_period,
        'search_query': search_query,
        'frequency_filter': frequency_filter,
        'filter_status': filter_status,
        'sent_count': sent_count,
        'pending_count': pending_count,
    }

    return render(request, 'operations/mis_dashboard.html', context)

@login_required
def mis_mark_sent(request, project_id):
    """Mark MIS as sent for selected date"""
    from projects.models import ProjectCode
    from operations.models import DailyMISLog
    from django.utils import timezone
    from django.shortcuts import get_object_or_404
    
    project = get_object_or_404(ProjectCode, project_id=project_id)
    
    # Get date from query params or use today
    date_str = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
    try:
        log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        log_date = timezone.now().date()
    
    # Permission check - ONLY MAIN COORDINATOR
    if request.user.role == 'operation_coordinator':
        user_name = request.user.get_full_name()
        if project.operation_coordinator != user_name:
            messages.error(request, 'Access denied.')
            return redirect('operations:mis_dashboard')
    
    # Create or update MIS log
    log, created = DailyMISLog.objects.get_or_create(
        project=project,
        log_date=log_date,
        defaults={
            'mis_sent': True,
            'sent_by': request.user,
            'sent_at': timezone.now()
        }
    )
    
    if not created:
        log.mis_sent = True
        log.sent_by = request.user
        log.sent_at = timezone.now()
        log.save()
    
    # At the end of mis_mark_sent function:
    messages.success(request, f'✅ MIS marked as sent for {project.project_code} on {log_date.strftime("%d %b %Y")}')
    return redirect('operations:mis_dashboard')  # Remove the ?date= part for now


@login_required
def mis_history(request, project_id):
    """
    Complete history of MIS logs for a specific project.
    Shows ALL MIS logs with pagination, date filter, and statistics.
    """
    from projects.models import ProjectCode
    from operations.models import DailyMISLog
    from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
    from django.db.models import Count
    from datetime import datetime

    user = request.user

    # Get project and verify access
    project = get_object_or_404(ProjectCode, project_id=project_id)

    # Permission check - user must have access to this project
    user_projects = get_user_projects(user)
    if project not in user_projects:
        messages.error(request, "You don't have permission to view this project's MIS history.")
        return redirect('operations:mis_dashboard')

    # Get date filters from query params
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    status_filter = request.GET.get('status', '')

    # Base queryset - all MIS logs for this project
    logs = DailyMISLog.objects.filter(
        project=project
    ).select_related('sent_by').order_by('-log_date')

    # Apply date filters
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            logs = logs.filter(log_date__gte=start_date)
        except ValueError:
            messages.warning(request, "Invalid start date format.")

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            logs = logs.filter(log_date__lte=end_date)
        except ValueError:
            messages.warning(request, "Invalid end date format.")

    # Apply status filter
    if status_filter == 'sent':
        logs = logs.filter(mis_sent=True)
    elif status_filter == 'pending':
        logs = logs.filter(mis_sent=False)

    # Calculate statistics
    total_logs = logs.count()
    sent_logs = logs.filter(mis_sent=True).count()
    pending_logs = logs.filter(mis_sent=False).count()

    stats = {
        'total_logs': total_logs,
        'sent_logs': sent_logs,
        'pending_logs': pending_logs,
        'compliance_rate': round((sent_logs / total_logs * 100), 1) if total_logs > 0 else 0
    }

    # Pagination
    paginator = Paginator(logs, 50)  # 50 logs per page
    page = request.GET.get('page')

    try:
        paginated_logs = paginator.page(page)
    except PageNotAnInteger:
        paginated_logs = paginator.page(1)
    except EmptyPage:
        paginated_logs = paginator.page(paginator.num_pages)

    context = {
        'project': project,
        'logs': paginated_logs,
        'stats': stats,
        'total_count': total_logs,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'status_filter': status_filter,
        'today': timezone.now().date(),
    }

    return render(request, 'operations/mis_history.html', context)


@login_required
def mis_all_history(request):
    """
    View all MIS history with project dropdown selector.
    Shows history for selected project with role-based access control.
    """
    from projects.models import ProjectCode
    from operations.models import DailyMISLog
    from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
    from datetime import datetime

    user = request.user

    # Get all projects user has access to
    user_projects = get_user_projects(user)

    # Get selected project from query params
    selected_project_id = request.GET.get('project')
    selected_project = None

    if selected_project_id:
        try:
            selected_project = ProjectCode.objects.get(project_id=selected_project_id)
            # Verify user has access
            if selected_project not in user_projects:
                messages.error(request, "You don't have permission to view this project's MIS history.")
                selected_project = None
        except ProjectCode.DoesNotExist:
            messages.warning(request, "Project not found.")
            selected_project = None

    # Get date filters from query params
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    status_filter = request.GET.get('status', '')

    # Base queryset
    if selected_project:
        logs = DailyMISLog.objects.filter(
            project=selected_project
        ).select_related('sent_by', 'project').order_by('-log_date')
    else:
        logs = DailyMISLog.objects.filter(
            project__in=user_projects
        ).select_related('sent_by', 'project').order_by('-log_date')

    # Apply date filters
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            logs = logs.filter(log_date__gte=start_date)
        except ValueError:
            messages.warning(request, "Invalid start date format.")

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            logs = logs.filter(log_date__lte=end_date)
        except ValueError:
            messages.warning(request, "Invalid end date format.")

    # Apply status filter
    if status_filter == 'sent':
        logs = logs.filter(mis_sent=True)
    elif status_filter == 'pending':
        logs = logs.filter(mis_sent=False)

    # Calculate statistics
    total_logs = logs.count()
    sent_logs = logs.filter(mis_sent=True).count()
    pending_logs = logs.filter(mis_sent=False).count()

    stats = {
        'total_logs': total_logs,
        'sent_logs': sent_logs,
        'pending_logs': pending_logs,
        'compliance_rate': round((sent_logs / total_logs * 100), 1) if total_logs > 0 else 0
    }

    # Pagination
    paginator = Paginator(logs, 50)  # 50 logs per page
    page = request.GET.get('page')

    try:
        paginated_logs = paginator.page(page)
    except PageNotAnInteger:
        paginated_logs = paginator.page(1)
    except EmptyPage:
        paginated_logs = paginator.page(paginator.num_pages)

    context = {
        'all_projects': user_projects.order_by('client_name', 'project_code'),
        'selected_project': selected_project,
        'logs': paginated_logs,
        'stats': stats,
        'total_count': total_logs,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'status_filter': status_filter,
        'today': timezone.now().date(),
    }

    return render(request, 'operations/mis_all_history.html', context)


# ============================================================================
# DISPUTE VIEWS
# ============================================================================

@login_required
def dispute_list(request):
    """List all disputes with filters"""
    user = request.user
    role = getattr(user, 'role', 'unknown') # Safer attribute access
    projects = get_user_projects(user)
    
    disputes = DisputeLog.objects.filter(
        project__in=projects
    ).select_related('project', 'raised_by', 'assigned_to').order_by('-raised_at')
    
    if role == 'operation_coordinator':
        disputes = disputes.filter(raised_by=user)
    
    # Filters
    status_filter = request.GET.get('status')
    priority_filter = request.GET.get('priority')
    title_filter = request.GET.get('title')
    search_filter = request.GET.get('search')

    if status_filter:
        disputes = disputes.filter(status=status_filter)
    if priority_filter:
        disputes = disputes.filter(priority=priority_filter)
    if title_filter:
        disputes = disputes.filter(title__icontains=title_filter)
    if search_filter:
        disputes = disputes.filter(
            Q(project__project_code__icontains=search_filter) |
            Q(project__client_name__icontains=search_filter) |
            Q(description__icontains=search_filter) |
            Q(raised_by__first_name__icontains=search_filter) |
            Q(raised_by__last_name__icontains=search_filter)
        )
    
    # Stats
    total_disputes = disputes.count()
    open_count = disputes.filter(status='open').count()
    in_progress_count = disputes.filter(status='in_progress').count()
    resolved_count = disputes.filter(status='resolved').count()
    
    context = {
        'disputes': disputes,
        'total_disputes': total_disputes,
        'open_count': open_count,
        'in_progress_count': in_progress_count,
        'resolved_count': resolved_count,
        'user_role': role,
    }
    return render(request, 'operations/dispute_list.html', context)


@login_required
def dispute_analysis(request):
    """Dispute analysis by project - shows dispute percentage per project"""
    user = request.user
    projects = get_user_projects(user)

    # Filter only WAAS Active projects
    projects = projects.filter(series_type='WAAS')

    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        projects = projects.filter(project_status=status_filter)
    else:
        # Default to Active and Notice Period projects
        projects = projects.filter(project_status__in=['Active', 'Notice Period'])

    # Search filter
    search_filter = request.GET.get('search')
    if search_filter:
        projects = projects.filter(
            Q(project_code__icontains=search_filter) |
            Q(client_name__icontains=search_filter)
        )

    # Calculate dispute metrics for each project
    project_data = []
    total_disputes_count = 0
    projects_with_disputes_count = 0

    for project in projects:
        # Get all disputes for this project
        all_disputes = DisputeLog.objects.filter(project=project)
        total_disputes = all_disputes.count()

        # Count by status
        open_disputes = all_disputes.filter(status__code='open').count()
        in_progress_disputes = all_disputes.filter(status__code='in_progress').count()
        resolved_disputes = all_disputes.filter(status__code='resolved').count()

        # Get most common dispute title/category for this project
        top_dispute = all_disputes.values('title').annotate(
            count=Count('dispute_id')
        ).order_by('-count').first()
        common_title = top_dispute['title'] if top_dispute else "N/A"

        # Calculate dispute percentage (disputes per project - simplified metric)
        # This shows what percentage of "expected events" resulted in disputes
        # For simplicity, we'll use: (total_disputes / max(1, months_active)) * 10
        # This gives a rough measure of dispute frequency

        # Alternative: Use a fixed baseline (e.g., disputes per 100 service months)
        # For now, let's use total disputes as the percentage directly (capped at 100)
        dispute_percentage = min(total_disputes * 10, 100) if total_disputes > 0 else 0

        if total_disputes > 0:
            projects_with_disputes_count += 1
            total_disputes_count += total_disputes

            # Only add projects with disputes to the list
            project_data.append({
                'project_code': project.project_code,
                'client_name': project.client_name,
                'project_status': project.project_status,
                'total_disputes': total_disputes,
                'open_disputes': open_disputes,
                'in_progress_disputes': in_progress_disputes,
                'resolved_disputes': resolved_disputes,
                'dispute_percentage': round(dispute_percentage, 1),
                'common_title': common_title,
            })

    # Sort projects
    sort_by = request.GET.get('sort', 'dispute_percentage')
    if sort_by == 'total_disputes':
        project_data.sort(key=lambda x: x['total_disputes'], reverse=True)
    elif sort_by == 'project_code':
        project_data.sort(key=lambda x: x['project_code'])
    else:  # dispute_percentage
        project_data.sort(key=lambda x: x['dispute_percentage'], reverse=True)

    # Calculate overall stats - Total WAAS Active + Notice Period projects
    total_waas_projects = projects.count()

    # Overall Dispute % = (Projects with disputes / Total WAAS projects) * 100
    overall_dispute_percentage = round(
        (projects_with_disputes_count / total_waas_projects * 100), 1
    ) if total_waas_projects > 0 else 0

    # ==================== ADDITIONAL ANALYTICS CALCULATIONS ====================
    from django.db.models import Sum, F, ExpressionWrapper, DurationField

    # Month boundaries
    today = timezone.now().date()
    current_month_start = today.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)

    # Filter only WAAS Active projects' disputes for consistency
    waas_project_ids = projects.values_list('project_id', flat=True)

    # Monthly Trends
    disputes_this_month = DisputeLog.objects.filter(
        project_id__in=waas_project_ids,
        raised_at__date__gte=current_month_start
    ).count()

    disputes_last_month = DisputeLog.objects.filter(
        project_id__in=waas_project_ids,
        raised_at__date__gte=previous_month_start,
        raised_at__date__lte=previous_month_end
    ).count()

    resolved_this_month = DisputeLog.objects.filter(
        project_id__in=waas_project_ids,
        resolved_at__date__gte=current_month_start,
        status__code='resolved'
    ).count()

    resolved_last_month = DisputeLog.objects.filter(
        project_id__in=waas_project_ids,
        resolved_at__date__gte=previous_month_start,
        resolved_at__date__lte=previous_month_end,
        status__code='resolved'
    ).count()

    # Calculate month-over-month trends
    month_over_month_raised = round(
        ((disputes_this_month - disputes_last_month) / disputes_last_month * 100), 1
    ) if disputes_last_month > 0 else 0

    month_over_month_resolved = round(
        ((resolved_this_month - resolved_last_month) / resolved_last_month * 100), 1
    ) if resolved_last_month > 0 else 0

    # Performance Metrics - Average TAT
    resolved_disputes = DisputeLog.objects.filter(
        project_id__in=waas_project_ids,
        status__code='resolved',
        opened_at__isnull=False,
        resolved_at__isnull=False
    )

    if resolved_disputes.exists():
        avg_tat_days = 0
        tat_count = 0
        for dispute in resolved_disputes:
            if dispute.calculated_tat_days:
                avg_tat_days += dispute.calculated_tat_days
                tat_count += 1
        avg_tat_days = round(avg_tat_days / tat_count, 1) if tat_count > 0 else 0
    else:
        avg_tat_days = 0

    # On-Time Resolution Rate
    total_resolved = resolved_disputes.count()
    on_time_resolved = 0

    for dispute in resolved_disputes:
        if dispute.calculated_tat_days and dispute.calculated_tat_days <= 7:
            on_time_resolved += 1

    on_time_resolution_rate = round(
        (on_time_resolved / total_resolved * 100), 1
    ) if total_resolved > 0 else 0

    # Overdue Disputes
    overdue_disputes = DisputeLog.objects.filter(
        Q(status__code='open') | Q(status__code='in_progress'),
        project_id__in=waas_project_ids,
        raised_at__date__lt=timezone.now().date() - timedelta(days=7)
    ).count()

    # Critical/High Priority
    critical_high_disputes = DisputeLog.objects.filter(
        (Q(status__code='open') | Q(status__code='in_progress')) &
        (Q(priority__code='critical') | Q(priority__code='high')),
        project_id__in=waas_project_ids
    ).count()

    # Optional Financial Metrics
    total_disputed_amount = DisputeLog.objects.filter(
        Q(status__code='open') | Q(status__code='in_progress'),
        project_id__in=waas_project_ids,
        disputed_amount__isnull=False
    ).aggregate(total=Sum('disputed_amount'))['total'] or 0

    # Convert to lakhs
    total_disputed_amount_lakhs = round(total_disputed_amount / 100000, 2)

    avg_disputed_amount = DisputeLog.objects.filter(
        project_id__in=waas_project_ids,
        disputed_amount__isnull=False
    ).aggregate(avg=Avg('disputed_amount'))['avg'] or 0

    avg_disputed_amount_lakhs = round(avg_disputed_amount / 100000, 2)

    # Top category
    top_category = DisputeLog.objects.filter(
        project_id__in=waas_project_ids
    ).values('category__label').annotate(
        count=Count('dispute_id')
    ).order_by('-count').first()

    top_category_name = top_category['category__label'] if top_category else "N/A"
    top_category_count = top_category['count'] if top_category else 0

    context = {
        'projects': project_data,
        'projects_with_disputes': projects_with_disputes_count,
        'total_disputes': total_disputes_count,
        'overall_dispute_percentage': overall_dispute_percentage,

        # Monthly Trends
        'disputes_this_month': disputes_this_month,
        'disputes_last_month': disputes_last_month,
        'resolved_this_month': resolved_this_month,
        'resolved_last_month': resolved_last_month,
        'month_over_month_raised': month_over_month_raised,
        'month_over_month_resolved': month_over_month_resolved,

        # Performance Metrics
        'avg_tat_days': avg_tat_days,
        'on_time_resolution_rate': on_time_resolution_rate,
        'overdue_disputes': overdue_disputes,
        'critical_high_disputes': critical_high_disputes,

        # Optional Financial Metrics
        'total_disputed_amount_lakhs': total_disputed_amount_lakhs,
        'avg_disputed_amount_lakhs': avg_disputed_amount_lakhs,
        'top_category_name': top_category_name,
        'top_category_count': top_category_count,
    }
    return render(request, 'operations/dispute_analysis.html', context)


@login_required
def dispute_create(request):
    """Create new dispute"""
    user = request.user
    projects = get_user_projects(user)
    
    if request.method == 'POST':
        from dropdown_master_data.models import Priority

        project_id = request.POST.get('project_id')
        title = request.POST.get('title')
        description = request.POST.get('description')
        priority_code = request.POST.get('priority', 'medium')
        disputed_amount = request.POST.get('disputed_amount')
        dispute_date = request.POST.get('dispute_date')
        assigned_to_id = request.POST.get('assigned_to')

        project = get_object_or_404(ProjectCode, project_id=project_id)

        # Get Priority object
        priority_obj = Priority.objects.get(code=priority_code)

        dispute = DisputeLog.objects.create(
            project=project,
            title=title,
            description=description,
            priority=priority_obj,
            disputed_amount=disputed_amount or None,
            dispute_date=dispute_date or None,
            raised_by=user,
            opened_at=timezone.now() # Track opening time
        )
        
        if assigned_to_id:
            assigned_user = User.objects.get(id=assigned_to_id)
            dispute.assigned_to = assigned_user
            dispute.save()
            notify_dispute_raised(dispute)
        
        # Log Creation Activity
        DisputeActivity.objects.create(
            dispute=dispute,
            user=user,
            activity_type=ActivityType.objects.get(code='created'),
            description='Dispute created'
        )
        
        messages.success(request, "Dispute created successfully")
        return redirect('operations:dispute_list')
    
    User = get_user_model()
    users = User.objects.filter(
        role__in=['operation_coordinator', 'operation_controller', 'admin']
    )
    
    context = {
        'projects': projects,
        'users': users,
        'today': timezone.now().date(),
    }
    return render(request, 'operations/dispute_create.html', context)


@login_required
def dispute_detail(request, pk):
    """Show dispute details - Fixed permissions for Reopening"""
    user = request.user
    role = getattr(user, 'role', 'unknown')
    
    dispute = get_object_or_404(DisputeLog, pk=pk)
    
    # 1. Access Control
    if role == 'operation_coordinator':
        if dispute.raised_by != user:
            messages.error(request, 'You do not have permission to view this dispute.')
            return redirect('operations:dispute_list')
    
    # 2. Define Management Roles
    management_roles = ['operation_manager', 'operation_controller', 'admin', 'super_user']
    is_management = role in management_roles
    
    # 3. Calculate Permissions
    # Check if dispute is currently active (editable)
    is_active_status = dispute.status.code not in ['resolved']
    
    # Can Edit: Only if active AND (is manager OR is owner)
    can_edit = (is_management or dispute.raised_by == user) and is_active_status
    
    # Can Assign: Only if active AND is manager
    can_assign = is_management and is_active_status
    
    # Can Delete: Only managers
    can_delete = is_management

    # NEW: Can Reopen: Only if NOT active AND (is manager OR is owner)
    can_reopen = (is_management or dispute.raised_by == user) and not is_active_status
    
    # Get related data
    comments = dispute.comments.all().order_by('-created_at')
    activities = dispute.activities.all().order_by('-created_at')
    
    # Get users for assignment dropdown
    User = get_user_model()
    users = User.objects.filter(
        role__in=['operation_manager', 'operation_controller', 'admin', 'operation_coordinator'],
        is_active=True
    ).exclude(id=user.id)
    
    context = {
        'dispute': dispute,
        'user_role': role,
        'comments': comments,
        'activities': activities,
        'users': users,
        'can_edit': can_edit,
        'can_assign': can_assign,
        'can_delete': can_delete,
        'can_reopen': can_reopen, # Pass this new flag
    }
    return render(request, 'operations/dispute_detail.html', context)


@login_required
def dispute_add_comment(request, pk):
    """Add comment to dispute"""
    dispute = get_object_or_404(DisputeLog, pk=pk)
    
    if request.method == 'POST':
        comment_text = request.POST.get('comment')
        attachment = request.FILES.get('attachment')
        
        if comment_text:
            DisputeComment.objects.create(
                dispute=dispute,
                user=request.user,
                comment=comment_text,
                attachment=attachment
            )
            
            DisputeActivity.objects.create(
                dispute=dispute,
                user=request.user,
                activity_type=ActivityType.objects.get(code='commented'),
                description=f"{request.user.get_full_name()} added a comment"
            )
            
            messages.success(request, '✅ Comment added successfully')
        else:
            messages.error(request, '❌ Comment cannot be empty')
    
    return redirect('operations:dispute_detail', pk=pk)


@login_required
def dispute_update_status(request, pk):
    """Update dispute status with Reopen logic"""
    user = request.user
    dispute = get_object_or_404(DisputeLog, pk=pk)
    
    # Permission logic
    allowed = (
        user.role in ['operation_manager', 'operation_controller', 'admin', 'super_user'] or 
        dispute.raised_by == user
    )
    
    if not allowed:
        messages.error(request, 'Permission denied.')
        return redirect('operations:dispute_detail', pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        from dropdown_master_data.models import DisputeStatus

        # Validate that the status exists
        try:
            new_status_obj = DisputeStatus.objects.get(code=new_status, is_active=True)
        except DisputeStatus.DoesNotExist:
            messages.error(request, f"Invalid status: '{new_status}'. Please contact support.")
            return redirect('operations:dispute_detail', pk=pk)

        old_status = dispute.status
        dispute.status = new_status_obj

        # 1. LOGIC FOR RESOLVING
        if new_status == 'resolved':
            dispute.resolved_at = timezone.now()
            dispute.resolved_by = user
            # We do NOT manually set tat_days integer field, we calculate it dynamically in template

        # 2. LOGIC FOR REOPENING (If moving from resolved back to open/in_progress)
        elif old_status.code in ['resolved'] and new_status in ['open', 'in_progress']:
            dispute.resolved_at = None
            dispute.resolved_by = None
            # opened_at remains the original start date to track total lifecycle

        dispute.save()

        # Log Activity
        activity_type_obj = ActivityType.objects.get(code='status_changed')
        DisputeActivity.objects.create(
            dispute=dispute,
            user=user,
            activity_type=activity_type_obj,
            old_value=old_status.code if old_status else 'unknown',
            new_value=new_status,
            description=f'Status changed from {old_status.label if old_status else "unknown"} to {new_status_obj.label}'
        )

        # Notifications
        if new_status == 'resolved':
            notify_dispute_resolved(dispute)

        messages.success(request, f'Status updated to {new_status_obj.label}.')

    return redirect('operations:dispute_detail', pk=pk)


@login_required
def dispute_update_priority(request, pk):
    """Update dispute priority"""
    user = request.user
    dispute = get_object_or_404(DisputeLog, pk=pk)
    
    allowed = (
        user.role in ['operation_manager', 'operation_controller', 'admin', 'super_user'] or 
        dispute.raised_by == user
    )
    
    if not allowed:
        messages.error(request, 'Permission denied.')
        return redirect('operations:dispute_detail', pk=pk)
    
    if request.method == 'POST':
        new_priority = request.POST.get('priority')
        if new_priority:
            from dropdown_master_data.models import Priority

            old_priority = dispute.priority
            # Get Priority object
            new_priority_obj = Priority.objects.get(code=new_priority)
            dispute.priority = new_priority_obj
            dispute.save()
            
            DisputeActivity.objects.create(
                dispute=dispute,
                user=user,
                activity_type=ActivityType.objects.get(code='priority_changed'),
                old_value=old_priority,
                new_value=new_priority,
                description=f'Priority changed from {old_priority} to {new_priority}'
            )
            
            messages.success(request, 'Priority updated.')
            
    return redirect('operations:dispute_detail', pk=pk)


@login_required
def dispute_assign(request, pk):
    """Assign dispute to user"""
    # Allow Managers and Controllers to assign
    if request.user.role not in ['operation_manager', 'operation_controller', 'admin', 'super_user']:
        messages.error(request, "Permission denied.")
        return redirect('operations:dispute_detail', pk=pk)
    
    dispute = get_object_or_404(DisputeLog, pk=pk)
    
    if request.method == 'POST':
        assigned_to_id = request.POST.get('assigned_to')
        old_assignee = dispute.assigned_to
        
        if assigned_to_id:
            User = get_user_model()
            assigned_user = User.objects.get(id=assigned_to_id)
            dispute.assigned_to = assigned_user
            
            DisputeActivity.objects.create(
                dispute=dispute,
                user=request.user,
                activity_type=ActivityType.objects.get(code='assigned'),
                description=f'Assigned to {assigned_user.get_full_name()}'
            )
            
            notify_dispute_assigned(dispute)
            messages.success(request, f"Assigned to {assigned_user.get_full_name()}")
        else:
            dispute.assigned_to = None
            DisputeActivity.objects.create(
                dispute=dispute,
                user=request.user,
                activity_type=ActivityType.objects.get(code='assigned'),
                description='Unassigned'
            )
            messages.success(request, "Dispute unassigned")
        
        dispute.save()
    
    return redirect('operations:dispute_detail', pk=pk)

@login_required
def dispute_edit(request, pk):
    """Edit dispute details"""
    user = request.user
    role = getattr(user, 'role', 'unknown')
    
    dispute = get_object_or_404(DisputeLog, pk=pk)
    
    # Permission Check
    allowed = (
        user.role in ['operation_manager', 'operation_controller', 'admin', 'super_user'] or 
        dispute.raised_by == user
    )
    
    if not allowed:
        messages.error(request, 'Access denied.')
        return redirect('operations:dispute_list')
    
    if request.method == 'POST':
        from dropdown_master_data.models import Priority

        dispute.title = request.POST.get('title')
        dispute.description = request.POST.get('description')

        # Get Priority object
        priority_code = request.POST.get('priority')
        if priority_code:
            priority_obj = Priority.objects.get(code=priority_code)
            dispute.priority = priority_obj

        dispute.disputed_amount = request.POST.get('disputed_amount') or None
        dispute.dispute_date = request.POST.get('dispute_date') or None
        dispute.save()
        
        messages.success(request, 'Dispute updated successfully.')
        return redirect('operations:dispute_detail', pk=pk)
    
    context = {
        'dispute': dispute,
        'user_role': role,
    }
    return render(request, 'operations/dispute_edit.html', context)


# ============================================================================
# HOLIDAY MANAGEMENT VIEWS
# ============================================================================

@login_required
def holiday_list(request):
    """List all holidays with filters"""
    holidays = WarehouseHoliday.objects.all().select_related('project', 'created_by').order_by('-holiday_date')
    
    # Filters
    year_filter = request.GET.get('year')
    month_filter = request.GET.get('month')
    project_filter = request.GET.get('project')
    
    if year_filter:
        holidays = holidays.filter(holiday_date__year=year_filter)
    if month_filter:
        holidays = holidays.filter(holiday_date__month=month_filter)
    if project_filter:
        holidays = holidays.filter(project__code__icontains=project_filter)
    
    # Stats
    today = timezone.now().date()
    total_holidays = holidays.count()
    this_month_count = holidays.filter(
        holiday_date__year=today.year,
        holiday_date__month=today.month
    ).count()
    upcoming_count = holidays.filter(holiday_date__gte=today).count()
    
    # Get affected projects
    affected_projects = holidays.values('project').distinct().count()
    
    # Get years for filter
    years = holidays.dates('holiday_date', 'year', order='DESC')
    
    context = {
        'holidays': holidays,
        'total_holidays': total_holidays,
        'this_month_count': this_month_count,
        'upcoming_count': upcoming_count,
        'affected_projects': affected_projects,
        'years': [d.year for d in years],
    }
    return render(request, 'operations/holiday_list.html', context)


@login_required
def holiday_create(request):
    """Create new holiday"""
    if request.method == 'POST':
        holiday_name = request.POST.get('holiday_name')
        holiday_date = request.POST.get('holiday_date')
        holiday_type = request.POST.get('holiday_type')
        description = request.POST.get('description', '')
        project_id = request.POST.get('project_id')
        
        holiday = WarehouseHoliday.objects.create(
            holiday_name=holiday_name,
            holiday_date=holiday_date,
            holiday_type=holiday_type,
            description=description,
            created_by=request.user
        )
        
        if holiday_type == 'project_specific' and project_id:
            holiday.project = ProjectCode.objects.get(project_id=project_id)
            holiday.save()
        
        messages.success(request, "Holiday added successfully")
        return redirect('operations:holiday_list')
    
    projects = ProjectCode.objects.filter(project_status='Active')
    
    context = {
        'projects': projects,
        'today': timezone.now().date(),
    }
    return render(request, 'operations/holiday_form.html', context)


@login_required
def holiday_edit(request, holiday_id):
    """Edit existing holiday"""
    holiday = get_object_or_404(WarehouseHoliday, id=holiday_id)
    
    if request.method == 'POST':
        holiday.holiday_name = request.POST.get('holiday_name')
        holiday.holiday_date = request.POST.get('holiday_date')
        holiday.holiday_type = request.POST.get('holiday_type')
        holiday.description = request.POST.get('description', '')
        
        project_id = request.POST.get('project_id')
        if holiday.holiday_type == 'project_specific' and project_id:
            holiday.project = ProjectCode.objects.get(project_id=project_id)
        else:
            holiday.project = None
        
        holiday.save()
        
        messages.success(request, "Holiday updated successfully")
        return redirect('operations:holiday_list')
    
    projects = ProjectCode.objects.filter(project_status='Active')
    
    context = {
        'holiday': holiday,
        'projects': projects,
        'today': timezone.now().date(),
    }
    return render(request, 'operations/holiday_form.html', context)


@login_required
def holiday_delete(request, holiday_id):
    """Delete holiday"""
    if request.method == 'POST':
        holiday = get_object_or_404(WarehouseHoliday, id=holiday_id)
        holiday.delete()
        messages.success(request, "Holiday deleted successfully")
    
    return redirect('operations:holiday_list')


# ============================================
# COORDINATOR PERFORMANCE VIEWS
# ============================================

@login_required
def coordinator_list_view(request):
    """
    Show list of all coordinators with project counts and performance stats.
    Accessible by managers, controllers, and admins.
    """
    # Check permissions
    if request.user.role not in ['operation_manager', 'operation_controller', 'admin', 'super_user']:
        messages.error(request, "You don't have permission to view coordinator performance.")
        return redirect('accounts:dashboard')
    
    from accounts.models import User
    
    # Get all coordinators
    coordinators = User.objects.filter(
        role='operation_coordinator',
        is_active=True
    ).order_by('first_name')
    
    today = timezone.now().date()
    coordinator_data = []
    
    for coord in coordinators:
        coord_name = f"{coord.first_name} {coord.last_name}".strip()
        
        # Count assigned projects
        project_count = ProjectCode.objects.filter(
            Q(operation_coordinator=coord_name) | Q(backup_coordinator=coord_name),
            project_status__in=['Active', 'Operation Not Started', 'Notice Period']
        ).count()
        
        # Calculate compliance (simplified)
        compliance_7d = 0
        compliance_30d = 0
        
        # Determine status based on compliance
        if compliance_30d >= 90:
            status = 'excellent'
        elif compliance_30d >= 70:
            status = 'good'
        elif compliance_30d >= 50:
            status = 'warning'
        else:
            status = 'critical'
        
        coordinator_data.append({
            'id': coord.id,
            'name': coord_name,
            'first_name': coord.first_name,
            'last_name': coord.last_name,
            'role': coord.get_role_display() if hasattr(coord, 'get_role_display') else 'Coordinator',
            'project_count': project_count,
            'compliance_7d': compliance_7d,
            'compliance_30d': compliance_30d,
            'status': status,
        })
    
    # Sort by project count descending
    coordinator_data.sort(key=lambda x: x['project_count'], reverse=True)
    
    context = {
        'coordinator_data': coordinator_data,
        'total_coordinators': len(coordinator_data),
    }
    
    return render(request, 'operations/coordinator_list.html', context)


def calculate_compliance(coordinator, start_date, end_date):
    """Calculate MIS compliance percentage for a coordinator in date range"""
    from operations.models import DailyMISLog
    
    coordinator_name = f"{coordinator.first_name} {coordinator.last_name}".strip()
    
    # Get projects assigned to this coordinator
    projects = ProjectCode.objects.filter(
        Q(operation_coordinator=coordinator_name) | Q(backup_coordinator=coordinator_name),
        project_status__in=['Active', 'Notice Period'],
        mis_status__in=['mis_daily', 'mis_weekly', 'mis_monthly']
    )
    
    if not projects.exists():
        return 0
    
    total_expected = 0
    total_submitted = 0
    
    for project in projects:
        # Calculate expected entries based on MIS status
        days_in_range = (end_date - start_date).days + 1
        
        if project.mis_status == 'mis_daily':
            expected = days_in_range
        elif project.mis_status == 'mis_weekly':
            expected = days_in_range // 7 + 1
        elif project.mis_status == 'mis_monthly':
            expected = 1
        else:
            expected = 0
        
        total_expected += expected
        
        # Count actual submissions - USE log_date NOT entry_date
        submitted = DailyMISLog.objects.filter(
            project=project,
            log_date__gte=start_date,
            log_date__lte=end_date
        ).count()
        
        total_submitted += submitted
    
    if total_expected == 0:
        return 100
    
    return round((total_submitted / total_expected) * 100, 1)


def get_coordinator_trend(coordinator, days):
    """Get MIS submission trend for coordinator over past N days"""
    from operations.models import DailyMISLog
    
    coordinator_name = f"{coordinator.first_name} {coordinator.last_name}".strip()
    today = timezone.now().date()
    
    trend_data = []
    
    for i in range(days - 1, -1, -1):
        date = today - timedelta(days=i)
        
        # Count submissions for this date
        count = DailyMISLog.objects.filter(
            Q(project__operation_coordinator=coordinator_name) | 
            Q(project__backup_coordinator=coordinator_name),
            log_date=date
        ).count()
        
        trend_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'count': count
        })
    
    return trend_data


def calculate_daily_compliance(coordinator, date):
    """Calculate compliance percentage for a coordinator on a specific date"""
    from operations.models import DailyMISLog
    
    coordinator_name = f"{coordinator.first_name} {coordinator.last_name}".strip()
    
    # Get projects assigned to this coordinator that need MIS on this date
    projects = ProjectCode.objects.filter(
        Q(operation_coordinator=coordinator_name) | Q(backup_coordinator=coordinator_name),
        project_status__in=['Active', 'Notice Period'],
        mis_status__in=['mis_daily', 'mis_weekly', 'mis_monthly']
    )
    
    if not projects.exists():
        return 100
    
    # For daily MIS, check if submitted
    daily_projects = projects.filter(mis_status='mis_daily')
    
    if not daily_projects.exists():
        return 100
    
    submitted = DailyMISLog.objects.filter(
        project__in=daily_projects,
        log_date=date
    ).count()
    
    total = daily_projects.count()
    
    if total == 0:
        return 100
    
    return round((submitted / total) * 100, 1)


@login_required
def coordinator_detail_view(request, coordinator_id):
    """
    Show detailed performance data for a specific coordinator.
    Includes: profile, current status, calendar, project list, charts.
    """
    # Check permissions
    if request.user.role not in ['operation_coordinator', 'operation_controller', 'admin', 'super_user']:
        messages.error(request, "You don't have permission to view coordinator details.")
        return redirect('accounts:dashboard')
    
    from operations.performance import (
        calculate_coordinator_performance,
        calculate_manager_performance,
        get_system_compliance,
        calculate_working_days,
        is_working_day
    )
    from datetime import timedelta
    
    # Get coordinator
    coordinator = get_object_or_404(User, id=coordinator_id)
    
    # Verify they are actually a coordinator
    if coordinator.role not in ['operation_coordinator', 'warehouse_manager']:
        messages.error(request, "This user is not a coordinator.")
        return redirect('operations:coordinator_list')
    
    today = timezone.now().date()
    
    # Get assigned projects
    projects = get_coordinator_projects(coordinator)
    
    # Calculate compliance for different periods
    from operations.performance import calculate_coordinator_performance
    perf = calculate_coordinator_performance(coordinator, today, days=1)
    compliance_today = perf['compliance_rate']

    from operations.performance import calculate_coordinator_performance
    perf_7d = calculate_coordinator_performance(coordinator, today, days=7)
    compliance_7d = perf_7d['compliance_rate']
    compliance_30d = calculate_compliance(coordinator, today - timedelta(days=29), today)
    
    # Get 30-day trend for chart
    trend_30d = get_coordinator_trend(coordinator, 30)
    
    # Get project-wise status (last entry date for each project)
    from operations.models import DailySpaceUtilization
    
    project_status = []
    for project in projects:
        last_entry = DailySpaceUtilization.objects.filter(
            project=project,
            entered_by=coordinator
        ).order_by('-entry_date').first()
        
        if last_entry:
            days_since = (today - last_entry.entry_date).days
        else:
            days_since = None
        
        project_status.append({
            'project': project,
            'last_entry_date': last_entry.entry_date if last_entry else None,
            'days_since': days_since,
            'status': 'good' if days_since == 0 else 'warning' if days_since and days_since <= 2 else 'critical'
        })
    
    # Sort by days_since (most critical first)
    project_status.sort(key=lambda x: x['days_since'] if x['days_since'] is not None else 999, reverse=True)
    
    # Build calendar data for current month
    import calendar
    from datetime import date
    
    year = today.year
    month = today.month
    
    cal = calendar.monthcalendar(year, month)
    calendar_data = []
    
    for week in cal:
        week_data = []
        for day in week:
            if day == 0:
                week_data.append(None)
            else:
                day_date = date(year, month, day)
                if day_date > today:
                    week_data.append({'day': day, 'compliance': None, 'future': True})
                else:
                    compliance = calculate_daily_compliance(coordinator, day_date)
                    week_data.append({
                        'day': day,
                        'date': day_date,
                        'compliance': compliance,
                        'color': 'green' if compliance >= 100 else 'yellow' if compliance >= 95 else 'red',
                        'future': False
                    })
        calendar_data.append(week_data)
    
    context = {
        'coordinator': coordinator,
        'total_projects': projects.count(),
        'compliance_today': compliance_today,
        'compliance_7d': compliance_7d,
        'compliance_30d': compliance_30d,
        'trend_30d': trend_30d,
        'project_status': project_status,
        'calendar_data': calendar_data,
        'current_month': today.strftime('%B %Y'),
    }
    
    return render(request, 'operations/coordinator_detail.html', context)

@login_required
def pending_entries_view(request):
    """
    Show pending entries breakdown by coordinator.
    Only accessible to managers and controllers.
    """
    user = request.user
    
    if user.role not in ['operation_coordinator', 'operation_controller', 'admin']:
        messages.error(request, "Access denied")
        return redirect('accounts:dashboard')
    
    today = timezone.now().date()
    
    # Get all coordinators
    coordinators = User.objects.filter(
        role__in=['operation_coordinator', 'warehouse_manager'],
        is_active=True
    ).order_by('first_name', 'last_name')
    
    pending_data = []
    
    for coord in coordinators:
        coord_full_name = coord.get_full_name()
        
        # Get assigned projects
        assigned = ProjectCode.objects.filter(
            Q(operation_coordinator=coord_full_name) | Q(backup_coordinator=coord_full_name)
        ).filter(
            project_status__in=['Active', 'Operation Not Started', 'Notice Period']
        )
        
        total_assigned = assigned.count()
        
        if total_assigned == 0:
            continue
        
        # Get today's entries
        entries_today = DailySpaceUtilization.objects.filter(
            project__in=assigned,
            entry_date=today
        ).count()
        
        pending_count = total_assigned - entries_today
        
        if pending_count > 0:
            pending_data.append({
                'coordinator': coord,
                'total_projects': total_assigned,
                'entries_today': entries_today,
                'pending_count': pending_count,
                'compliance': round((entries_today / total_assigned * 100), 1) if total_assigned > 0 else 0
            })
    
    # Sort by pending count (highest first)
    pending_data.sort(key=lambda x: x['pending_count'], reverse=True)
    
    context = {
        'pending_data': pending_data,
        'today': today,
    }
    
    return render(request, 'operations/pending_entries_detail.html', context)

# Calendar views removed — replaced by activity_logs app at /activity/

# API ENDPOINTS
# ============================================================================

from django.http import JsonResponse
from datetime import datetime, timedelta

@login_required
def get_previous_day_data(request):
    """API endpoint to get last filled entries for bulk copy"""
    user = request.user
    date_str = request.GET.get('date')

    if not date_str:
        return JsonResponse({'success': False, 'message': 'Date parameter required'})

    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Invalid date format'})

    # Get user's projects
    projects = get_user_projects(user)

    # For each project, find the most recent entry before the selected date
    entries_data = []
    last_entry_date = None

    for project in projects:
        # Get the most recent entry for this project before the selected date
        last_entry = DailySpaceUtilization.objects.filter(
            project=project,
            entry_date__lt=selected_date
        ).order_by('-entry_date').first()

        if last_entry:
            # Track the most recent date across all projects
            if last_entry_date is None or last_entry.entry_date > last_entry_date:
                last_entry_date = last_entry.entry_date

            entries_data.append({
                'project_id': project.project_id,
                'space_utilized': float(last_entry.space_utilized) if last_entry.space_utilized else None,
                'unit': last_entry.unit.code if hasattr(last_entry.unit, 'code') else str(last_entry.unit),
                'inventory_value': float(last_entry.inventory_value) if last_entry.inventory_value else None,
                'remarks': last_entry.remarks or '',
                'entry_date': last_entry.entry_date.strftime('%Y-%m-%d')
            })

    if not entries_data:
        return JsonResponse({
            'success': False,
            'message': 'No previous entries found for any projects'
        })

    return JsonResponse({
        'success': True,
        'last_entry_date': last_entry_date.strftime('%Y-%m-%d') if last_entry_date else None,
        'entries': entries_data,
        'count': len(entries_data)
    })


@login_required
def dispute_add_comment(request, pk):
    """Add comment to dispute"""
    dispute = get_object_or_404(DisputeLog, pk=pk)

    if request.method == 'POST':
        comment_text = request.POST.get('comment')
        attachment = request.FILES.get('attachment')

        if comment_text:
            # Create comment
            comment = DisputeComment.objects.create(
                dispute=dispute,
                user=request.user,
                comment=comment_text,
                attachment=attachment
            )

            # Create activity log
            DisputeActivity.objects.create(
                dispute=dispute,
                user=request.user,
                activity_type=ActivityType.objects.get(code='commented'),
                description=f"{request.user.get_full_name()} added a comment"
            )

            messages.success(request, '✅ Comment added successfully')
        else:
            messages.error(request, '❌ Comment cannot be empty')

    return redirect('operations:dispute_detail', pk=pk)


@login_required
def daily_entry_update_inline(request):
    """
    AJAX endpoint: Update daily entry inline from history view
    Allows editing space, unit, inventory, and remarks
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        import json
        data = json.loads(request.body)

        entry_id = data.get('entry_id')
        space_utilized = data.get('space_utilized')
        unit_value = data.get('unit')
        inventory_value = data.get('inventory_value')
        remarks = data.get('remarks', '')

        # Validate required fields
        if not entry_id or not space_utilized or not unit_value or not inventory_value:
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)

        # Get the entry
        try:
            entry = DailySpaceUtilization.objects.get(id=entry_id)
        except DailySpaceUtilization.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Entry not found'
            }, status=404)

        # Permission check: user can only edit their own entries or if admin/manager
        if request.user.role not in ['admin', 'operation_manager', 'operation_controller']:
            if entry.entered_by != request.user:
                return JsonResponse({
                    'success': False,
                    'error': 'You can only edit your own entries'
                }, status=403)

        # Get StorageUnit instance (dropdown now sends codes directly)
        try:
            from dropdown_master_data.models import StorageUnit
            unit_instance = StorageUnit.objects.get(code=unit_value)
        except StorageUnit.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Invalid unit: {unit_value}'
            }, status=400)

        # Update the entry
        entry.space_utilized = space_utilized
        entry.unit = unit_instance
        entry.inventory_value = inventory_value
        entry.remarks = remarks
        entry.last_modified_by = request.user
        entry.save()

        return JsonResponse({
            'success': True,
            'message': 'Entry updated successfully',
            'entry_id': entry_id
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Inline update failed: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
