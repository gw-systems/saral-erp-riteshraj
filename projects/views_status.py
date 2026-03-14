"""
Status transition logic for projects
Handles state changes with validation and prompts
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from supply.models import Location
from supply.models import CityCode
from .models import ProjectCode, GstState, UnusedProjectId, ProjectNameChangeLog, ProjectCodeChangeLog
from datetime import date, datetime, timedelta

def get_return_url(request):
    """
    Get the URL to return to after an action.
    Priority: 1) POST data, 2) GET param, 3) HTTP_REFERER, 4) None
    """
    # Check POST data first
    return_url = request.POST.get('return_url')

    # Check GET parameter
    if not return_url:
        return_url = request.GET.get('return_url')

    # Check HTTP referer
    if not return_url:
        return_url = request.META.get('HTTP_REFERER')

    # Ensure it's a safe internal URL (starts with /)
    if return_url and return_url.startswith('/'):
        return return_url

    return None


def log_status_change(project, field_name, old_value, new_value, user, request, change_reason=None):
    """
    Helper function to log status changes to audit trail
    """
    # Get IP address
    ip_address = request.META.get('REMOTE_ADDR')

    # Create change log entry
    ProjectCodeChangeLog.objects.create(
        project_id=project.project_id,
        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
        changed_by=user,
        ip_address=ip_address
    )

@login_required
def change_project_status(request, project_id):
    """
    Change project status with validation and required fields.
    Handles TEMP project conversion and merging.
    """
    project = get_object_or_404(ProjectCode, project_id=project_id)
    
    # Check permissions
    if request.user.role not in ['admin', 'super_user', 'operation_controller', 'operation_manager', 'backoffice']:
        messages.error(request, 'You do not have permission to change project status.')
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('projects:project_list_all')
    
    if request.method == 'POST':
        new_status = request.POST.get('new_status')
        current_status = project.project_status
        
        # Validate transition
        if current_status == new_status:
            messages.warning(request, f'Project is already in {new_status} status.')
            return_url = get_return_url(request)
            if return_url:
                return redirect(return_url)
            return redirect('projects:project_list_all')
        
        # TRANSITION 1: Operation Not Started → Active
        if current_status == 'Operation Not Started' and new_status == 'Active':
            # Check if this is a TEMP project
            is_temp = project.project_id.startswith('TEMP-')
            merge_with = request.POST.get('merge_with_project')
            
            if merge_with:
                # ============================================================
                # PATH A: USER CHOSE TO MERGE WITH EXISTING PROJECT
                # Works for both TEMP and non-TEMP projects
                # ============================================================
                try:
                    old_project = ProjectCode.objects.get(project_id=merge_with)
                    
                    # Validate merge
                    is_valid, errors, warnings = validate_project_merge(project, old_project)
                    
                    if not is_valid:
                        for error in errors:
                            messages.error(request, error)
                        return redirect('projects:change_status', project_id=project_id)
                    
                    # Show warnings
                    for warning in warnings:
                        messages.warning(request, warning)
                    
                    # Perform merge
                    merge_reason = request.POST.get('merge_reason', '')
                    success, message, updated_project = merge_temp_into_existing(
                        project, old_project, request.user, merge_reason
                    )
                    
                    if success:
                        messages.success(request, f"✅ {message}")
                        return_url = get_return_url(request)
                        if return_url:
                            return redirect(return_url)
                        return redirect('projects:project_detail', project_id=updated_project.project_id)
                    else:
                        messages.error(request, f"❌ {message}")
                        return redirect('projects:change_status', project_id=project_id)
                        
                except ProjectCode.DoesNotExist:
                    messages.error(request, "Selected project not found")
                    return redirect('projects:change_status', project_id=project_id)
            
            elif is_temp:
                # ============================================================
                # PATH B: USER CHOSE NEW INDEPENDENT PROJECT - Generate permanent ID
                # ============================================================
                operation_start_date = request.POST.get('operation_start_date')
                
                if not operation_start_date:
                    messages.error(request, 'Operation Start Date is required')
                    return redirect('projects:change_status', project_id=project_id)
                
                # Generate permanent project_id
                from .utils import get_next_sequence_number, get_next_state_code
                from .models import GstState
                
                series_type = project.series_type
                current_year = timezone.now().year
                sequence_num = get_next_sequence_number(series_type, current_year)
                year_suffix = str(current_year)[-2:]
                new_project_id = f"{series_type}-{year_suffix}-{sequence_num:03d}"
                
                # Generate new code
                gst_state = GstState.objects.filter(state_name=project.state, is_active=True).first()
                state_code = gst_state.state_code if gst_state else 'MH'
                new_code = get_next_state_code(state_code, series_type)
                
                # SAFETY CHECK: Ensure no operational data exists on TEMP project
                from operations.models import DailySpaceUtilization, MonthlyBilling
                from operations.models_adhoc import AdhocBillingEntry
                
                if DailySpaceUtilization.objects.filter(project=project).exists():
                    messages.error(request, "❌ Cannot activate: TEMP project has daily entries. Please contact admin.")
                    return redirect('projects:change_status', project_id=project_id)
                
                if AdhocBillingEntry.objects.filter(project=project).exists():
                    messages.error(request, "❌ Cannot activate: TEMP project has billing entries. Please contact admin.")
                    return redirect('projects:change_status', project_id=project_id)
                
                if MonthlyBilling.objects.filter(project=project).exists():
                    messages.error(request, "❌ Cannot activate: TEMP project has monthly billing. Please contact admin.")
                    return redirect('projects:change_status', project_id=project_id)
                
                # Store old TEMP ID for audit trail and messages
                old_temp_id = project.project_id
                
                # Create new project with permanent ID (copy all fields from TEMP project)
                new_project = ProjectCode.objects.create(
                project_id=new_project_id,
                code=new_code,
                series_type=series_type,
                # project_code will be auto-generated by existing logic
                client_name=project.client_name,
                vendor_name=project.vendor_name,
                warehouse_code=project.warehouse_code,
                location=project.location,
                state=project.state,
                project_status='Active',
                sales_manager=project.sales_manager,
                operation_coordinator=project.operation_coordinator,
                backup_coordinator=project.backup_coordinator,
                # billing_start_date removed - now stored in ProjectCard only
                notice_period_start_date=project.notice_period_start_date,
                notice_period_duration=project.notice_period_duration,
                notice_period_end_date=project.notice_period_end_date,
                operation_mode=project.operation_mode,
                mis_status=project.mis_status,
                billing_unit=project.billing_unit if hasattr(project, 'billing_unit') and project.billing_unit else None,
                minimum_billable_sqft=project.minimum_billable_sqft,
                minimum_billable_pallets=project.minimum_billable_pallets,
                client_card=project.client_card,
                vendor_warehouse=project.vendor_warehouse,
                created_at=project.created_at,
                updated_at=timezone.now(),
            )
                
                # Update ProjectCard FK to point to new project
                from operations.models_projectcard import ProjectCard
                project_cards = ProjectCard.objects.filter(project=project)
                for card in project_cards:
                    card.project = new_project
                    card.operation_start_date = operation_start_date
                    card.save()
                
                # Update ProjectDocuments FK to point to new project (if model exists)
                try:
                    from projects.models_document import ProjectDocument
                    ProjectDocument.objects.filter(project=project).update(project=new_project)
                except ImportError:
                    pass  # Model doesn't exist, skip
                
                # Create audit trail in UnusedProjectId
                UnusedProjectId.objects.update_or_create(
                    project_id=old_temp_id,
                    defaults={
                        'was_intended_for': f"{project.client_name}",
                        'intended_series': series_type,
                        'merged_into': new_project_id,
                        'created_at': project.created_at,
                        'deleted_by': request.user,
                        'reason': 'Activated as new independent project'
                    }
                )
                
                # Delete old TEMP project
                project.delete()
                
                messages.success(request, f'✅ Project activated as {new_code} (ID: {new_project_id})')
                messages.info(request, f'🗑️ Temporary ID {old_temp_id} has been archived')
                
            else:
                # ============================================================
                # PATH C: NON-TEMP PROJECT - Normal activation
                # ============================================================
                operation_start_date = request.POST.get('operation_start_date')
                
                if not operation_start_date:
                    messages.error(request, 'Operation Start Date is required')
                    return redirect('projects:change_status', project_id=project_id)
                
                old_status = project.project_status
                project.project_status = 'Active'
                project.updated_at = timezone.now()
                project.save()

                # Log status change
                log_status_change(project, 'project_status', old_status, 'Active', request.user, request)

                from operations.models_projectcard import ProjectCard
                project_card = ProjectCard.objects.filter(project=project).first()
                if project_card:
                    project_card.operation_start_date = operation_start_date
                    project_card.save()

                    # Log operation start date
                    log_status_change(project, 'operation_start_date', None, operation_start_date, request.user, request)

                    messages.success(request, f'✅ Project {project.code} is now Active (Start Date: {operation_start_date})')
                else:
                    messages.warning(request, f'⚠️ Project {project.code} activated but no project card found')

            # Common return for all activation paths
            return_url = get_return_url(request)
            if return_url:
                return redirect(return_url)
            return redirect('projects:project_list_all')
        
        # TRANSITION 2: Active → Notice Period
        elif current_status == 'Active' and new_status == 'Notice Period':
            notice_period_start_date = request.POST.get('notice_period_start_date')
            notice_period_duration = request.POST.get('notice_period_duration')
            
            if not notice_period_start_date or not notice_period_duration:
                messages.error(request, 'Notice Period Start Date and Duration are required.')
                return redirect('projects:change_status', project_id=project_id)
            
            try:
                # Convert to date and calculate end date
                start_date = datetime.strptime(notice_period_start_date, '%Y-%m-%d').date()
                duration_days = int(notice_period_duration)
                end_date = start_date + timedelta(days=duration_days)
                
                # Update all fields
                old_status = project.project_status
                project.project_status = 'Notice Period'
                project.notice_period_start_date = start_date
                project.notice_period_duration = duration_days
                project.notice_period_end_date = end_date
                project.updated_at = timezone.now()
                project.save()

                # Log all changes
                log_status_change(project, 'project_status', old_status, 'Notice Period', request.user, request)
                log_status_change(project, 'notice_period_start_date', None, start_date, request.user, request)
                log_status_change(project, 'notice_period_duration', None, f'{duration_days} days', request.user, request)
                log_status_change(project, 'notice_period_end_date', None, end_date, request.user, request)

                messages.warning(
                    request,
                    f'⚠️ Project {project.code} entered Notice Period | '
                    f'Start: {start_date.strftime("%d %b %Y")} | Duration: {duration_days} days | End: {end_date.strftime("%d %b %Y")}'
                )
                
            except Exception as e:
                messages.error(request, f'Error: {str(e)}')
                return redirect('projects:change_status', project_id=project_id)
        
        # TRANSITION 3: Notice Period → Inactive
        elif current_status == 'Notice Period' and new_status == 'Inactive':
            # Clear coordinators when moving to inactive
            old_status = project.project_status
            old_coordinator = project.operation_coordinator
            old_backup = project.backup_coordinator

            project.project_status = 'Inactive'
            project.operation_coordinator = None
            project.backup_coordinator = None
            project.updated_at = timezone.now()
            project.save()

            # Log all changes
            log_status_change(project, 'project_status', old_status, 'Inactive', request.user, request)
            if old_coordinator:
                log_status_change(project, 'operation_coordinator', old_coordinator, None, request.user, request)
            if old_backup:
                log_status_change(project, 'backup_coordinator', old_backup, None, request.user, request)

            messages.info(request, f'🔒 Project {project.code} is now Inactive. Coordinators have been cleared.')

        # TRANSITION 4: Notice Period → Active (Cancel Notice Period)
        elif current_status == 'Notice Period' and new_status == 'Active':
            confirm = request.POST.get('confirm_cancel_notice')
            
            if confirm != 'yes':
                messages.error(request, 'Please confirm cancelling the Notice Period.')
                return redirect('projects:change_status', project_id=project_id)
            
            old_status = project.project_status
            old_start = project.notice_period_start_date
            old_duration = project.notice_period_duration
            old_end = project.notice_period_end_date

            project.project_status = 'Active'
            project.notice_period_start_date = None
            project.notice_period_duration = None
            project.notice_period_end_date = None
            project.updated_at = timezone.now()
            project.save()

            # Log all changes
            log_status_change(project, 'project_status', old_status, 'Active', request.user, request)
            log_status_change(project, 'notice_period_start_date', old_start, None, request.user, request)
            log_status_change(project, 'notice_period_duration', old_duration, None, request.user, request)
            log_status_change(project, 'notice_period_end_date', old_end, None, request.user, request)

            messages.success(request, f'✅ Project {project.code} reactivated. Notice Period cancelled.')
        
        # TRANSITION 5: Active → Inactive (Direct - Skip Notice)
        elif current_status == 'Active' and new_status == 'Inactive':
            confirm = request.POST.get('confirm_skip_notice')
            
            if confirm != 'yes':
                messages.error(request, 'Please confirm skipping Notice Period to move directly to Inactive.')
                return redirect('projects:change_status', project_id=project_id)
            
            old_status = project.project_status
            old_coordinator = project.operation_coordinator
            old_backup = project.backup_coordinator

            project.project_status = 'Inactive'
            project.operation_coordinator = None
            project.backup_coordinator = None
            project.updated_at = timezone.now()
            project.save()

            # Log all changes
            log_status_change(project, 'project_status', old_status, 'Inactive', request.user, request)
            if old_coordinator:
                log_status_change(project, 'operation_coordinator', old_coordinator, None, request.user, request)
            if old_backup:
                log_status_change(project, 'backup_coordinator', old_backup, None, request.user, request)

            messages.info(request, f'🔒 Project {project.code} is now Inactive (Notice Period skipped).')
        
        # TRANSITION 6: Operation Not Started → Inactive
        elif current_status == 'Operation Not Started' and new_status == 'Inactive':
            confirm = request.POST.get('confirm_close_not_started')
            
            if confirm != 'yes':
                messages.error(request, 'Please confirm closing this project without starting operations.')
                return redirect('projects:change_status', project_id=project_id)
            
            # If TEMP project, archive the ID
            if project.project_id.startswith('TEMP-'):
                UnusedProjectId.objects.create(
                    project_id=project.project_id,
                    was_intended_for=f"{project.client_name}",
                    intended_series=project.series_type,
                    merged_into=None,
                    created_at=project.created_at,
                    deleted_by=request.user,
                    reason='Closed without activation'
                )
            
            old_status = project.project_status
            project.project_status = 'Inactive'
            project.updated_at = timezone.now()
            project.save()

            # Log status change
            log_status_change(project, 'project_status', old_status, 'Inactive', request.user, request)

            messages.info(request, f'🔒 Project {project.code} is now Inactive (never started).')
        
        # TRANSITION 7: Any → Operation Not Started (Reopen)
        elif new_status == 'Operation Not Started':
            confirm = request.POST.get('confirm_reopen')
            
            if confirm != 'yes':
                messages.error(request, 'Please confirm reopening project to Operation Not Started.')
                return redirect('projects:change_status', project_id=project_id)
            
            old_status = project.project_status
            old_notice_start = project.notice_period_start_date
            old_notice_duration = project.notice_period_duration
            old_notice_end = project.notice_period_end_date

            project.project_status = 'Operation Not Started'
            # Clear operation start date from project card if exists
            from operations.models_projectcard import ProjectCard
            project_card = ProjectCard.objects.filter(project=project).first()
            old_operation_start = None
            if project_card and project_card.operation_start_date:
                old_operation_start = project_card.operation_start_date
                project_card.operation_start_date = None
                project_card.save()

            project.notice_period_start_date = None
            project.notice_period_duration = None
            project.notice_period_end_date = None
            project.updated_at = timezone.now()
            project.save()

            # Log all changes
            log_status_change(project, 'project_status', old_status, 'Operation Not Started', request.user, request)
            if old_operation_start:
                log_status_change(project, 'operation_start_date', old_operation_start, None, request.user, request)
            if old_notice_start:
                log_status_change(project, 'notice_period_start_date', old_notice_start, None, request.user, request)
            if old_notice_duration:
                log_status_change(project, 'notice_period_duration', old_notice_duration, None, request.user, request)
            if old_notice_end:
                log_status_change(project, 'notice_period_end_date', old_notice_end, None, request.user, request)

            messages.success(request, f'🔄 Project {project.code} reopened to Operation Not Started.')
        
        # TRANSITION 8: Extend Notice Period
        elif current_status == 'Notice Period' and new_status == 'Notice Period':
            # This handles extending the notice period
            extend_days = request.POST.get('extend_days')
            
            if not extend_days:
                messages.error(request, 'Please select extension duration.')
                return redirect('projects:change_status', project_id=project_id)
            
            try:
                extend_days = int(extend_days)
                current_end = project.notice_period_end_date
                
                if current_end:
                    new_end_date = current_end + timedelta(days=extend_days)
                    new_duration = project.notice_period_duration + extend_days
                else:
                    # Fallback if end date not set
                    new_end_date = date.today() + timedelta(days=extend_days)
                    new_duration = extend_days
                
                old_end_date = project.notice_period_end_date
                old_duration = project.notice_period_duration

                project.notice_period_end_date = new_end_date
                project.notice_period_duration = new_duration
                project.updated_at = timezone.now()
                project.save()

                # Log the extension
                log_status_change(project, 'notice_period_end_date', old_end_date, new_end_date, request.user, request)
                log_status_change(project, 'notice_period_duration', f'{old_duration} days', f'{new_duration} days', request.user, request)

                messages.success(
                    request,
                    f'✅ Notice Period extended by {extend_days} days for {project.code}. '
                    f'New end date: {new_end_date.strftime("%d %b %Y")}'
                )
                
            except Exception as e:
                messages.error(request, f'Error extending notice period: {str(e)}')
                return redirect('projects:change_status', project_id=project_id)
        
        else:
            messages.error(request, f'Invalid status transition: {current_status} → {new_status}')
            return redirect('projects:change_status', project_id=project_id)
        
        # SUCCESS - RETURN TO WHERE USER CAME FROM
        return_url = get_return_url(request)
        if return_url:
            return redirect(return_url)
        return redirect('projects:project_list_all')
    
    # GET request - show status change form
    context = {
        'project': project,
        'current_status': project.project_status,
        'available_statuses': [choice[0] for choice in ProjectCode.STATUS_CHOICES],
        'today': date.today(),
        'is_temp_project': project.project_id.startswith('TEMP-'),
        'return_url': get_return_url(request),
    }
    
    return render(request, 'projects/change_status.html', context)


@login_required
def get_status_transition_requirements(request):
    """
    AJAX endpoint to get required fields for status transition
    """
    current_status = request.GET.get('current')
    new_status = request.GET.get('new')
    
    requirements = {
        'requires_date': False,
        'date_field': None,
        'date_label': None,
        'requires_confirmation': False,
        'confirmation_message': None,
        'requires_duration': False,
        'duration_options': [],
        'requires_extension': False,
    }
    
    # Operation Not Started → Active
    if current_status == 'Operation Not Started' and new_status == 'Active':
        requirements['requires_date'] = True
        requirements['date_field'] = 'operation_start_date'
        requirements['date_label'] = 'Operation Start Date'
    
    # Active → Notice Period
    elif current_status == 'Active' and new_status == 'Notice Period':
        requirements['requires_date'] = True
        requirements['date_field'] = 'notice_period_start_date'
        requirements['date_label'] = 'Notice Period Start Date'
        requirements['requires_duration'] = True
        requirements['duration_options'] = [
            {'value': 15, 'label': '15 Days'},
            {'value': 30, 'label': '1 Month (30 Days)'},
            {'value': 60, 'label': '2 Months (60 Days)'},
            {'value': 90, 'label': '3 Months (90 Days)'},
        ]
    
    # Active → Inactive (skip notice)
    elif current_status == 'Active' and new_status == 'Inactive':
        requirements['requires_confirmation'] = True
        requirements['confirmation_message'] = 'Skip Notice Period and move directly to Inactive? Coordinators will be cleared.'
    
    # Operation Not Started → Inactive
    elif current_status == 'Operation Not Started' and new_status == 'Inactive':
        requirements['requires_confirmation'] = True
        requirements['confirmation_message'] = 'Close this project without starting operations?'
    
    # Any → Operation Not Started (Reopen)
    elif new_status == 'Operation Not Started':
        requirements['requires_confirmation'] = True
        requirements['confirmation_message'] = 'Reopen this project? All dates will be cleared.'

    # Notice Period → Active (cancel notice)
    elif current_status == 'Notice Period' and new_status == 'Active':
        requirements['requires_confirmation'] = True
        requirements['confirmation_message'] = 'Cancel Notice Period and reactivate this project?'
    
    # Notice Period → Inactive
    elif current_status == 'Notice Period' and new_status == 'Inactive':
        requirements['requires_confirmation'] = True
        requirements['confirmation_message'] = 'Close this project? Notice Period will end and coordinators will be cleared.'
    
    return JsonResponse(requirements)


@login_required
def extend_notice_period(request, project_id):
    """
    Extend notice period for a project (called when notice period is about to end)
    """
    project = get_object_or_404(ProjectCode, project_id=project_id)
    
    # Check permissions
    if request.user.role not in ['admin', 'super_user', 'operation_controller', 'operation_manager']:
        messages.error(request, 'You do not have permission to extend notice period.')
        return redirect('projects:project_list_all')
    
    if project.project_status != 'Notice Period':
        messages.error(request, 'Project is not in Notice Period.')
        return redirect('projects:project_detail', project_id=project_id)
    
    if request.method == 'POST':
        extend_days = request.POST.get('extend_days')
        
        if not extend_days:
            messages.error(request, 'Please select extension duration.')
            return redirect('projects:extend_notice_period', project_id=project_id)
        
        try:
            extend_days = int(extend_days)
            current_end = project.notice_period_end_date
            
            if current_end:
                new_end_date = current_end + timedelta(days=extend_days)
                new_duration = (project.notice_period_duration or 0) + extend_days
            else:
                new_end_date = date.today() + timedelta(days=extend_days)
                new_duration = extend_days
            
            old_end_date = project.notice_period_end_date
            old_duration = project.notice_period_duration

            project.notice_period_end_date = new_end_date
            project.notice_period_duration = new_duration
            project.updated_at = timezone.now()
            project.save()

            # Log the extension
            log_status_change(project, 'notice_period_end_date', old_end_date, new_end_date, request.user, request)
            log_status_change(project, 'notice_period_duration', f'{old_duration} days', f'{new_duration} days', request.user, request)

            messages.success(
                request,
                f'✅ Notice Period extended by {extend_days} days for {project.code}. '
                f'New end date: {new_end_date.strftime("%d %b %Y")}'
            )
            
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        
        return redirect('projects:project_detail', project_id=project_id)
    
    # GET - show extension form
    context = {
        'project': project,
        'current_end_date': project.notice_period_end_date,
        'extension_options': [
            {'value': 15, 'label': '15 Days'},
            {'value': 30, 'label': '1 Month (30 Days)'},
            {'value': 60, 'label': '2 Months (60 Days)'},
            {'value': 90, 'label': '3 Months (90 Days)'},
        ],
    }
    
    return render(request, 'projects/extend_notice_period.html', context)


def get_notice_period_expiring_projects(days_threshold=5):
    """
    Get projects whose notice period is expiring within the threshold days.
    Used for alerts and dashboard widgets.
    
    Returns queryset of projects with additional 'days_remaining' annotation.
    """
    today = date.today()
    threshold_date = today + timedelta(days=days_threshold)
    
    projects = ProjectCode.objects.filter(
        project_status='Notice Period',
        notice_period_end_date__isnull=False,
        notice_period_end_date__lte=threshold_date,
        notice_period_end_date__gte=today
    ).order_by('notice_period_end_date')
    
    # Add days remaining to each project
    for project in projects:
        project.days_remaining = (project.notice_period_end_date - today).days
    
    return projects


def get_notice_period_expired_projects():
    """
    Get projects whose notice period has expired but are still in Notice Period status.
    These should be moved to Inactive.
    """
    today = date.today()
    
    return ProjectCode.objects.filter(
        project_status='Notice Period',
        notice_period_end_date__isnull=False,
        notice_period_end_date__lt=today
    ).order_by('notice_period_end_date')


def validate_project_merge(temp_project, old_project):
    """
    Validate if TEMP project can be merged into existing project.
    
    Returns: (is_valid, errors_list, warnings_list)
    """
    errors = []
    warnings = []
    
    # 1. Check source project status
    if temp_project.project_status != 'Operation Not Started':
        errors.append("Project must be in 'Operation Not Started' status")
    
    # 3. Check old project status
    if old_project.project_status not in ['Active', 'Notice Period']:
        errors.append(f"Cannot merge into project with status: {old_project.project_status}")
    
    # 4. Check series type compatibility
    if old_project.series_type != temp_project.series_type:
        errors.append(
            f"Series mismatch: Cannot merge {temp_project.series_type} into {old_project.series_type}"
        )
    
    # 5. CRITICAL: Location must match exactly
    if old_project.location != temp_project.location:
        errors.append(
            f"❌ Location mismatch: '{old_project.location}' vs '{temp_project.location}'. "
            f"Location changes require a new project code."
        )

    # 6. CRITICAL: State must match exactly
    if old_project.state != temp_project.state:
        errors.append(
            f"❌ State mismatch: '{old_project.state}' vs '{temp_project.state}'. "
            f"State changes require a new project code."
        )

    # 7. Check for data in source project
    from operations.models import DailySpaceUtilization
    from operations.models_adhoc import AdhocBillingEntry

    if temp_project.project_id.startswith('TEMP-'):
        # TEMP projects shouldn't have operational data
        if DailySpaceUtilization.objects.filter(project=temp_project).exists():
            errors.append("TEMP project has daily entries - cannot merge")
        if AdhocBillingEntry.objects.filter(project=temp_project).exists():
            errors.append("TEMP project has billing entries - cannot merge")
    else:
        # Non-TEMP projects may have data — it will be migrated
        daily_count = DailySpaceUtilization.objects.filter(project=temp_project).count()
        adhoc_count = AdhocBillingEntry.objects.filter(project=temp_project).count()
        if daily_count or adhoc_count:
            warnings.append(
                f"This project has {daily_count} daily entries and {adhoc_count} billing entries that will be migrated to the target project"
            )

    # 8. Warnings for allowed changes
    if old_project.vendor_name != temp_project.vendor_name:
        warnings.append(
            f"⚠️ VENDOR CHANGE: '{old_project.vendor_name}' → '{temp_project.vendor_name}'. "
            f"This is a vendor transition for the same client/location."
        )

    if old_project.client_name != temp_project.client_name:
        warnings.append(
            f"ℹ️ Client name will change: '{old_project.client_name}' → '{temp_project.client_name}'"
        )

    if old_project.sales_manager != temp_project.sales_manager:
        warnings.append(
            f"ℹ️ Sales manager will change: '{old_project.sales_manager or 'None'}' → '{temp_project.sales_manager or 'None'}'"
        )

    if old_project.operation_coordinator != temp_project.operation_coordinator:
        warnings.append(
            f"ℹ️ Coordinator will change: '{old_project.operation_coordinator or 'None'}' → '{temp_project.operation_coordinator or 'None'}'"
        )
    
    is_valid = len(errors) == 0
    return is_valid, errors, warnings

from django.db import transaction

def merge_temp_into_existing(temp_project, old_project, user, reason=''):
    """
    Merge TEMP project into existing project.
    Updates display fields, copies rate card, archives TEMP ID.
    
    Returns: (success, message, updated_project)
    """
    try:
        with transaction.atomic():
            # Store old values for audit
            old_client_name = old_project.client_name
            old_vendor_name = old_project.vendor_name
            old_code = old_project.code
            old_project_code = old_project.project_code

            # Store TEMP project values BEFORE deletion
            temp_client_name = temp_project.client_name
            temp_vendor_name = temp_project.vendor_name
            temp_code = temp_project.code
            temp_project_code = temp_project.project_code
            temp_sales_manager = temp_project.sales_manager
            temp_operation_coordinator = temp_project.operation_coordinator
            temp_backup_coordinator = temp_project.backup_coordinator
            temp_project_id = temp_project.project_id
            temp_created_at = temp_project.created_at

            # 1. Migrate operational data from TEMP to target project FIRST
            # This changes all FK references from temp_project to old_project
            # MUST be done BEFORE deleting temp_project
            from operations.models import DailySpaceUtilization, MonthlyBilling, DisputeLog
            from operations.models_adhoc import AdhocBillingEntry

            # Migrate daily entries
            daily_updated = DailySpaceUtilization.objects.filter(project=temp_project).update(project=old_project)

            # Migrate adhoc billing
            adhoc_updated = AdhocBillingEntry.objects.filter(project=temp_project).update(project=old_project)

            # Migrate monthly billing
            monthly_updated = MonthlyBilling.objects.filter(project=temp_project).update(project=old_project)

            # Migrate disputes
            disputes_updated = DisputeLog.objects.filter(project=temp_project).update(project=old_project)

            total_migrated = daily_updated + adhoc_updated + monthly_updated + disputes_updated

            # 2. Copy rate card from TEMP to old project
            from operations.models_projectcard import ProjectCard
            temp_card = ProjectCard.objects.filter(project=temp_project).first()

            if temp_card:
                # Create new rate card linked to old project
                new_card = ProjectCard.objects.create(
                    project=old_project,
                    client_card=temp_card.client_card,
                    vendor_warehouse=temp_card.vendor_warehouse,
                    operation_start_date=temp_card.operation_start_date,
                    billing_start_date=temp_card.billing_start_date,
                )

                # Copy all rates
                for rate in temp_card.storage_rates.all():
                    rate.pk = None
                    rate.project_card = new_card
                    rate.save()

                for rate in temp_card.handling_rates.all():
                    rate.pk = None
                    rate.project_card = new_card
                    rate.save()

                for service in temp_card.vas_services.all():
                    service.pk = None
                    service.project_card = new_card
                    service.save()

                for cost in temp_card.infrastructure_costs.all():
                    cost.pk = None
                    cost.project_card = new_card
                    cost.save()

            # 3. Archive TEMP project ID (before deletion)
            UnusedProjectId.objects.create(
                project_id=temp_project_id,
                was_intended_for=temp_client_name,
                intended_series=temp_project.series_type,
                merged_into=old_project.project_id,
                created_at=temp_created_at,
                deleted_by=user,
                reason=reason or f'Merged into {old_project.project_id} - {total_migrated} records migrated'
            )

            # 4. Delete TEMP project (frees up unique constraint on project_code)
            temp_project.delete()

            # 5. NOW update target project with TEMP's details (no constraint conflict)
            # project_id stays: WAAS-25-175 (primary key, cannot change)
            # code updates: MH236 -> MH289 (override with TEMP's code)
            # project_code updates: full string override
            # This maintains linear flow of client lifetime
            old_project.client_name = temp_client_name
            old_project.vendor_name = temp_vendor_name
            old_project.code = temp_code  # Override: MH236 -> MH289
            old_project.project_code = temp_project_code  # Override full string (NOW SAFE!)
            old_project.sales_manager = temp_sales_manager
            old_project.operation_coordinator = temp_operation_coordinator
            old_project.backup_coordinator = temp_backup_coordinator
            old_project.updated_at = timezone.now()
            old_project.save()

            # 6. Create audit log
            ProjectNameChangeLog.objects.create(
                project=old_project,
                old_client_name=old_client_name,
                new_client_name=temp_client_name,
                old_project_code=old_project_code,
                new_project_code=temp_project_code,
                changed_by=user,
                reason=reason or f'Merged from TEMP project {temp_project_id} - migrated {total_migrated} operational records'
            )

            return True, f"Successfully merged into {old_project.project_id} - {total_migrated} records migrated", old_project
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Error during merge: {str(e)}", None