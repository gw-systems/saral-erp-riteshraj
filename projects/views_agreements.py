"""
Agreement Renewal and Escalation Views
Handles workflow for renewals and annual escalations
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Min, Max
from django.utils import timezone
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from operations.models_agreements import (
    EscalationTracker,
    EscalationLog,
    AgreementRenewalTracker,
    AgreementRenewalLog,
)
from operations.models_projectcard import ProjectCard
from projects.models import ProjectCode


# ==================== ESCALATION VIEWS ====================

@login_required
def escalation_tracker_list(request):
    """
    List all escalation trackers with overdue/upcoming split
    """
    today = timezone.now().date()
    
    # Get all trackers
    trackers = EscalationTracker.objects.select_related(
        'project_card__project',
        'created_by',
        'last_updated_by'
    ).all()
    
    # Annotate with calculated fields
    overdue_trackers = []
    upcoming_trackers = []
    
    for tracker in trackers:
        # Add calculated properties directly to tracker object
        tracker.escalation_date = tracker.escalation_effective_date
        tracker.next_action_text, tracker.is_urgent = tracker.get_next_action()
        
        # Split into overdue vs upcoming
        if tracker.is_overdue:
            overdue_trackers.append(tracker)
        else:
            upcoming_trackers.append(tracker)
    
    # Sort overdue by most overdue first
    overdue_trackers.sort(key=lambda x: x.days_overdue, reverse=True)
    
    # Sort upcoming by soonest first
    upcoming_trackers.sort(key=lambda x: x.days_until_due if x.days_until_due else 999)
    
    # Filters
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        overdue_trackers = [t for t in overdue_trackers if t.status == status_filter]
        upcoming_trackers = [t for t in upcoming_trackers if t.status == status_filter]
    
    search_query = request.GET.get('search', '')
    if search_query:
        overdue_trackers = [
            t for t in overdue_trackers 
            if search_query.lower() in t.project_card.project.project_code.lower()
        ]
        upcoming_trackers = [
            t for t in upcoming_trackers 
            if search_query.lower() in t.project_card.project.project_code.lower()
        ]
    
    context = {
        'overdue_trackers': overdue_trackers,
        'upcoming_trackers': upcoming_trackers,
        'overdue_count': len(overdue_trackers),
        'upcoming_count': len(upcoming_trackers),
        'status_filter': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'operations/escalation_tracker_list.html', context)


@login_required
def escalation_tracker_create(request, project_card_id):
    """
    Create new escalation tracker for a project card
    """
    project_card = get_object_or_404(ProjectCard, id=project_card_id)
    
    if request.method == 'POST':
        escalation_year = int(request.POST.get('escalation_year'))
        escalation_percentage = request.POST.get('escalation_percentage')
        
        # Check if tracker already exists for this year
        existing = EscalationTracker.objects.filter(
            project_card=project_card,
            escalation_year=escalation_year
        ).first()
        
        if existing:
            messages.error(request, f'Escalation tracker for Year {escalation_year} already exists!')
            return redirect('operations:escalation_tracker_detail', tracker_id=existing.id)
        
        # Get escalation % from project card if not provided
        if not escalation_percentage:
            if project_card.escalation_terms == 'FIXED':
                escalation_percentage = project_card.annual_escalation_percent
            else:
                escalation_percentage = None
        
        # Create tracker
        tracker = EscalationTracker.objects.create(
            project_card=project_card,
            escalation_year=escalation_year,
            escalation_percentage=escalation_percentage,
            status='pending',
            created_by=request.user,
            last_updated_by=request.user,
        )
        
        # Create log entry
        EscalationLog.objects.create(
            tracker=tracker,
            action_type='tracker_created',
            action_date=timezone.now().date(),
            notes=f'Tracker created for Year {escalation_year} escalation',
            performed_by=request.user,
        )
        
        messages.success(request, f'Escalation tracker created for Year {escalation_year}')
        return redirect('operations:escalation_tracker_detail', tracker_id=tracker.id)
    
    # Calculate next escalation year
    existing_years = EscalationTracker.objects.filter(
        project_card=project_card
    ).values_list('escalation_year', flat=True)
    
    next_year = max(existing_years) + 1 if existing_years else 1
    
    context = {
        'project_card': project_card,
        'next_year': next_year,
        'escalation_percentage': project_card.annual_escalation_percent,
        'escalation_terms': project_card.get_escalation_terms_display() if project_card.escalation_terms else 'Not Set',
    }
    
    return render(request, 'operations/escalation_tracker_create.html', context)


@login_required
def escalation_tracker_detail(request, tracker_id):
    """
    View detailed escalation tracker with timeline and logs
    """
    tracker = get_object_or_404(
        EscalationTracker.objects.select_related(
            'project_card__project',
            'created_by',
            'last_updated_by'
        ),
        id=tracker_id
    )
    
    # Get logs
    logs = tracker.logs.select_related('performed_by').all()
    
    # Calculate escalation date
    escalation_date = tracker.escalation_effective_date
    
    # Build timeline
    timeline = []
    
    if tracker.initial_intimation_sent:
        timeline.append({
            'date': tracker.initial_intimation_sent,
            'action': 'Initial Intimation Sent',
            'status': 'completed'
        })
    
    if tracker.first_reminder_sent:
        timeline.append({
            'date': tracker.first_reminder_sent,
            'action': '1st Reminder Sent',
            'status': 'completed'
        })
    
    if tracker.second_reminder_sent:
        timeline.append({
            'date': tracker.second_reminder_sent,
            'action': '2nd Reminder Sent',
            'status': 'completed'
        })
    
    if tracker.sales_manager_informed_date:
        timeline.append({
            'date': tracker.sales_manager_informed_date,
            'action': 'Sales Manager Informed',
            'status': 'completed'
        })
    
    if tracker.final_notice_sent:
        timeline.append({
            'date': tracker.final_notice_sent,
            'action': 'Final Notice Sent',
            'status': 'completed'
        })
    
    if tracker.finance_team_informed_date:
        timeline.append({
            'date': tracker.finance_team_informed_date,
            'action': 'Finance Team Informed',
            'status': 'completed'
        })
    
    if tracker.client_acknowledgment_date:
        timeline.append({
            'date': tracker.client_acknowledgment_date,
            'action': 'Client Acknowledged',
            'status': 'completed'
        })
    
    if tracker.escalation_applied_date:
        timeline.append({
            'date': tracker.escalation_applied_date,
            'action': 'Escalation Applied',
            'status': 'completed'
        })
    
    # Sort timeline by date
    timeline.sort(key=lambda x: x['date'])
    
    context = {
        'tracker': tracker,
        'escalation_date': escalation_date,
        'is_overdue': tracker.is_overdue,
        'days_overdue': tracker.days_overdue,
        'days_until_due': tracker.days_until_due,
        'next_action': tracker.get_next_action(),
        'workflow_stage': tracker.get_workflow_stage(),
        'timeline': timeline,
        'logs': logs,
    }
    
    return render(request, 'operations/escalation_tracker_detail.html', context)


@login_required
def escalation_tracker_send_email(request, tracker_id):
    """
    Mark email as sent (manual marking - no actual email sent from system)
    """
    tracker = get_object_or_404(EscalationTracker, id=tracker_id)
    
    if request.method == 'POST':
        email_type = request.POST.get('email_type')
        email_to = request.POST.get('email_to', '')
        email_subject = request.POST.get('email_subject', '')
        notes = request.POST.get('notes', '')
        
        today = timezone.now().date()
        
        # Update tracker based on email type
        if email_type == 'initial_intimation':
            tracker.initial_intimation_sent = today
            action_type = 'initial_intimation'
            action_display = 'Initial Intimation'
            
        elif email_type == 'reminder_1':
            tracker.first_reminder_sent = today
            action_type = 'reminder_1'
            action_display = '1st Reminder'
            
        elif email_type == 'reminder_2':
            tracker.second_reminder_sent = today
            action_type = 'reminder_2'
            action_display = '2nd Reminder'
            
        elif email_type == 'final_notice':
            tracker.final_notice_sent = today
            action_type = 'final_notice'
            action_display = 'Final Notice'
            
        else:
            messages.error(request, 'Invalid email type')
            return redirect('operations:escalation_tracker_detail', tracker_id=tracker.id)
        
        # Update status if still pending
        if tracker.status == 'pending':
            tracker.status = 'in_progress'
        
        tracker.last_updated_by = request.user
        tracker.save()
        
        # Create log entry
        EscalationLog.objects.create(
            tracker=tracker,
            action_type=action_type,
            action_date=today,
            notes=notes,
            email_sent_to=email_to,
            email_subject=email_subject,
            performed_by=request.user,
        )
        
        messages.success(request, f'{action_display} marked as sent')
        return redirect('operations:escalation_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
    }
    
    return render(request, 'operations/escalation_tracker_send_email.html', context)


@login_required
def escalation_tracker_inform_sales(request, tracker_id):
    """
    Record sales manager intimation
    """
    tracker = get_object_or_404(EscalationTracker, id=tracker_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        tracker.sales_manager_informed_date = timezone.now().date()
        tracker.sales_manager_notes = notes
        tracker.last_updated_by = request.user
        tracker.save()
        
        # Create log entry
        EscalationLog.objects.create(
            tracker=tracker,
            action_type='sales_informed',
            action_date=timezone.now().date(),
            notes=notes,
            performed_by=request.user,
        )
        
        messages.success(request, 'Sales manager intimation recorded')
        return redirect('operations:escalation_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
    }
    
    return render(request, 'operations/escalation_tracker_inform_sales.html', context)


@login_required
def escalation_tracker_inform_finance(request, tracker_id):
    """
    Record finance team intimation
    """
    tracker = get_object_or_404(EscalationTracker, id=tracker_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        tracker.finance_team_informed_date = timezone.now().date()
        tracker.finance_team_notes = notes
        tracker.last_updated_by = request.user
        tracker.save()
        
        # Create log entry
        EscalationLog.objects.create(
            tracker=tracker,
            action_type='finance_informed',
            action_date=timezone.now().date(),
            notes=notes,
            performed_by=request.user,
        )
        
        messages.success(request, 'Finance team intimation recorded')
        return redirect('operations:escalation_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
    }
    
    return render(request, 'operations/escalation_tracker_inform_finance.html', context)


@login_required
def escalation_tracker_client_acknowledged(request, tracker_id):
    """
    Record client acknowledgment
    """
    tracker = get_object_or_404(EscalationTracker, id=tracker_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        tracker.client_acknowledged = True
        tracker.client_acknowledgment_date = timezone.now().date()
        tracker.client_response_notes = notes
        tracker.status = 'client_acknowledged'
        tracker.last_updated_by = request.user
        tracker.save()
        
        # Create log entry
        EscalationLog.objects.create(
            tracker=tracker,
            action_type='client_acknowledged',
            action_date=timezone.now().date(),
            notes=notes,
            performed_by=request.user,
        )
        
        messages.success(request, 'Client acknowledgment recorded')
        return redirect('operations:escalation_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
    }
    
    return render(request, 'operations/escalation_tracker_client_acknowledged.html', context)


@login_required
def escalation_tracker_apply_escalation(request, tracker_id):
    """
    Apply escalation - creates new ProjectCard version with escalated rates
    """
    tracker = get_object_or_404(EscalationTracker, id=tracker_id)
    
    if request.method == 'POST':
        escalation_percent = request.POST.get('escalation_percentage')
        
        if not escalation_percent:
            messages.error(request, 'Escalation percentage is required')
            return redirect('operations:escalation_tracker_detail', tracker_id=tracker.id)
        
        try:
            escalation_percent = float(escalation_percent)
            
            # Create new ProjectCard version with escalated rates
            old_card = tracker.project_card
            new_card = old_card.create_new_version(
                user=request.user,
                escalation_percent=escalation_percent,
                new_agreement_dates=None  # Same agreement, just rate change
            )
            
            # Update tracker
            tracker.escalation_applied_date = timezone.now().date()
            tracker.applied_percentage = escalation_percent
            tracker.status = 'escalation_applied'
            tracker.last_updated_by = request.user
            tracker.save()
            
            # Create log entry
            EscalationLog.objects.create(
                tracker=tracker,
                action_type='escalation_applied',
                action_date=timezone.now().date(),
                notes=f'Escalation of {escalation_percent}% applied. New ProjectCard v{new_card.version} created.',
                performed_by=request.user,
            )
            
            messages.success(
                request, 
                f'Escalation applied! New ProjectCard v{new_card.version} created with {escalation_percent}% rate increase.'
            )
            return redirect('operations:project_card_detail', card_id=new_card.id)
            
        except Exception as e:
            messages.error(request, f'Error applying escalation: {str(e)}')
            return redirect('operations:escalation_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
        'suggested_percentage': tracker.escalation_percentage or tracker.project_card.annual_escalation_percent,
    }
    
    return render(request, 'operations/escalation_tracker_apply_escalation.html', context)


@login_required
def escalation_tracker_update_status(request, tracker_id):
    """
    Update tracker status
    """
    tracker = get_object_or_404(EscalationTracker, id=tracker_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        old_status = tracker.status
        tracker.status = new_status
        tracker.last_updated_by = request.user
        tracker.save()
        
        # Create log entry
        EscalationLog.objects.create(
            tracker=tracker,
            action_type='status_changed',
            action_date=timezone.now().date(),
            notes=f'Status changed from {old_status} to {new_status}. {notes}',
            performed_by=request.user,
        )
        
        messages.success(request, f'Status updated to {tracker.get_status_display()}')
        return redirect('operations:escalation_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
        'status_choices': EscalationTracker.STATUS_CHOICES,
    }
    
    return render(request, 'operations/escalation_tracker_update_status.html', context)


# ==================== RENEWAL VIEWS ====================

@login_required
def renewal_tracker_list(request):
    """
    List all renewal trackers with overdue/upcoming split
    """
    today = timezone.now().date()
    
    # Get all trackers
    trackers = AgreementRenewalTracker.objects.select_related(
        'project_card__project',
        'created_by',
        'last_updated_by'
    ).all()
    
    # Annotate with calculated fields
    overdue_trackers = []
    upcoming_trackers = []
    
    for tracker in trackers:
        # Add calculated properties directly to tracker object
        tracker.renewal_date_display = tracker.renewal_due_date
        tracker.next_action_text, tracker.is_urgent = tracker.get_next_action()
        
        # Split into overdue vs upcoming
        if tracker.is_overdue:
            overdue_trackers.append(tracker)
        else:
            upcoming_trackers.append(tracker)
    
    # Sort overdue by most overdue first
    overdue_trackers.sort(key=lambda x: x.days_overdue, reverse=True)
    
    # Sort upcoming by soonest first
    upcoming_trackers.sort(key=lambda x: x.days_until_due if x.days_until_due else 999)
    
    # Filters
    status_filter = request.GET.get('status', 'all')
    if status_filter != 'all':
        overdue_trackers = [t for t in overdue_trackers if t.status == status_filter]
        upcoming_trackers = [t for t in upcoming_trackers if t.status == status_filter]
    
    search_query = request.GET.get('search', '')
    if search_query:
        overdue_trackers = [
            t for t in overdue_trackers 
            if search_query.lower() in t.project_card.project.project_code.lower()
        ]
        upcoming_trackers = [
            t for t in upcoming_trackers 
            if search_query.lower() in t.project_card.project.project_code.lower()
        ]
    
    context = {
        'overdue_trackers': overdue_trackers,
        'upcoming_trackers': upcoming_trackers,
        'overdue_count': len(overdue_trackers),
        'upcoming_count': len(upcoming_trackers),
        'status_filter': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'operations/renewal_tracker_list.html', context)


@login_required
def renewal_tracker_create(request, project_card_id):
    """
    Create new renewal tracker for a project card
    """
    project_card = get_object_or_404(ProjectCard, id=project_card_id)
    
    # Check if tracker already exists
    existing = AgreementRenewalTracker.objects.filter(
        project_card=project_card,
        status__in=['pending', 'in_progress']
    ).first()
    
    if existing:
        messages.warning(request, 'Active renewal tracker already exists!')
        return redirect('operations:renewal_tracker_detail', tracker_id=existing.id)
    
    if request.method == 'POST':
        # Create tracker
        tracker = AgreementRenewalTracker.objects.create(
            project_card=project_card,
            status='pending',
            created_by=request.user,
            last_updated_by=request.user,
        )
        
        # Create log entry
        AgreementRenewalLog.objects.create(
            tracker=tracker,
            action_type='tracker_created',
            action_date=timezone.now().date(),
            notes='Renewal tracker created',
            performed_by=request.user,
        )
        
        messages.success(request, 'Renewal tracker created successfully')
        return redirect('operations:renewal_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'project_card': project_card,
        'renewal_due_date': project_card.agreement_end_date,
    }
    
    return render(request, 'operations/renewal_tracker_create.html', context)


@login_required
def renewal_tracker_detail(request, tracker_id):
    """
    View detailed renewal tracker with timeline and logs
    """
    tracker = get_object_or_404(
        AgreementRenewalTracker.objects.select_related(
            'project_card__project',
            'created_by',
            'last_updated_by'
        ),
        id=tracker_id
    )
    
    # Get logs
    logs = tracker.logs.select_related('performed_by').all()
    
    # Calculate renewal date
    renewal_date = tracker.renewal_due_date
    
    # Build timeline
    timeline = []
    
    if tracker.initial_email_sent:
        timeline.append({
            'date': tracker.initial_email_sent,
            'action': 'Initial Email Sent',
            'status': 'completed'
        })
    
    if tracker.first_reminder_sent:
        timeline.append({
            'date': tracker.first_reminder_sent,
            'action': '1st Reminder Sent',
            'status': 'completed'
        })
    
    if tracker.second_reminder_sent:
        timeline.append({
            'date': tracker.second_reminder_sent,
            'action': '2nd Reminder Sent',
            'status': 'completed'
        })
    
    if tracker.third_reminder_sent:
        timeline.append({
            'date': tracker.third_reminder_sent,
            'action': '3rd Reminder Sent',
            'status': 'completed'
        })
    
    if tracker.sales_manager_informed_1_date:
        timeline.append({
            'date': tracker.sales_manager_informed_1_date,
            'action': 'Sales Manager Informed',
            'status': 'completed'
        })
    
    if tracker.final_intimation_sent:
        timeline.append({
            'date': tracker.final_intimation_sent,
            'action': 'Final Intimation Sent',
            'status': 'completed'
        })
    
    if tracker.client_response_date:
        timeline.append({
            'date': tracker.client_response_date,
            'action': 'Client Responded',
            'status': 'completed'
        })
    
    if tracker.renewal_completed_date:
        timeline.append({
            'date': tracker.renewal_completed_date,
            'action': 'Renewal Completed',
            'status': 'completed'
        })
    
    # Sort timeline by date
    timeline.sort(key=lambda x: x['date'])
    
    context = {
        'tracker': tracker,
        'renewal_date': renewal_date,
        'is_overdue': tracker.is_overdue,
        'days_overdue': tracker.days_overdue,
        'days_until_due': tracker.days_until_due,
        'next_action': tracker.get_next_action(),
        'workflow_stage': tracker.get_workflow_stage(),
        'timeline': timeline,
        'logs': logs,
    }
    
    return render(request, 'operations/renewal_tracker_detail.html', context)


@login_required
def renewal_tracker_send_email(request, tracker_id):
    """
    Mark renewal email as sent
    """
    tracker = get_object_or_404(AgreementRenewalTracker, id=tracker_id)
    
    if request.method == 'POST':
        email_type = request.POST.get('email_type')
        email_to = request.POST.get('email_to', '')
        email_subject = request.POST.get('email_subject', '')
        notes = request.POST.get('notes', '')
        
        today = timezone.now().date()
        
        # Update tracker based on email type
        if email_type == 'initial_email':
            tracker.initial_email_sent = today
            action_type = 'initial_email'
            action_display = 'Initial Email'
            
        elif email_type == 'reminder_1':
            tracker.first_reminder_sent = today
            action_type = 'reminder_1'
            action_display = '1st Reminder'
            
        elif email_type == 'reminder_2':
            tracker.second_reminder_sent = today
            action_type = 'reminder_2'
            action_display = '2nd Reminder'
            
        elif email_type == 'reminder_3':
            tracker.third_reminder_sent = today
            action_type = 'reminder_3'
            action_display = '3rd Reminder'
            
        elif email_type == 'final_intimation':
            tracker.final_intimation_sent = today
            action_type = 'final_intimation'
            action_display = 'Final Intimation'
            
        else:
            messages.error(request, 'Invalid email type')
            return redirect('operations:renewal_tracker_detail', tracker_id=tracker.id)
        
        # Update status if still pending
        if tracker.status == 'pending':
            tracker.status = 'in_progress'
        
        tracker.last_updated_by = request.user
        tracker.save()
        
        # Create log entry
        AgreementRenewalLog.objects.create(
            tracker=tracker,
            action_type=action_type,
            action_date=today,
            notes=notes,
            email_sent_to=email_to,
            email_subject=email_subject,
            performed_by=request.user,
        )
        
        messages.success(request, f'{action_display} marked as sent')
        return redirect('operations:renewal_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
    }
    
    return render(request, 'operations/renewal_tracker_send_email.html', context)


@login_required
def renewal_tracker_inform_sales(request, tracker_id):
    """
    Record sales manager intimation
    """
    tracker = get_object_or_404(AgreementRenewalTracker, id=tracker_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        # Determine if this is first or second time
        if not tracker.sales_manager_informed_1_date:
            tracker.sales_manager_informed_1_date = timezone.now().date()
            tracker.sales_manager_informed_1_notes = notes
            action_type = 'sales_informed_1'
        else:
            tracker.sales_manager_informed_2_date = timezone.now().date()
            tracker.sales_manager_informed_2_notes = notes
            action_type = 'sales_informed_2'
        
        tracker.last_updated_by = request.user
        tracker.save()
        
        # Create log entry
        AgreementRenewalLog.objects.create(
            tracker=tracker,
            action_type=action_type,
            action_date=timezone.now().date(),
            notes=notes,
            performed_by=request.user,
        )
        
        messages.success(request, 'Sales manager intimation recorded')
        return redirect('operations:renewal_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
    }
    
    return render(request, 'operations/renewal_tracker_inform_sales.html', context)


@login_required
def renewal_tracker_client_response(request, tracker_id):
    """
    Record client response
    """
    tracker = get_object_or_404(AgreementRenewalTracker, id=tracker_id)
    
    if request.method == 'POST':
        response_summary = request.POST.get('response_summary', '')
        
        tracker.client_responded = True
        tracker.client_response_date = timezone.now().date()
        tracker.client_response_summary = response_summary
        tracker.status = 'client_responded'
        tracker.last_updated_by = request.user
        tracker.save()
        
        # Create log entry
        AgreementRenewalLog.objects.create(
            tracker=tracker,
            action_type='client_responded',
            action_date=timezone.now().date(),
            notes=response_summary,
            performed_by=request.user,
        )
        
        messages.success(request, 'Client response recorded')
        return redirect('operations:renewal_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
    }
    
    return render(request, 'operations/renewal_tracker_client_response.html', context)


@login_required
def renewal_tracker_complete_renewal(request, tracker_id):
    """
    Complete renewal - creates new ProjectCard version with new agreement dates
    Can optionally apply escalation at the same time
    """
    tracker = get_object_or_404(AgreementRenewalTracker, id=tracker_id)
    
    if request.method == 'POST':
        new_start_date = request.POST.get('new_start_date')
        new_end_date = request.POST.get('new_end_date')
        apply_escalation = request.POST.get('apply_escalation') == 'yes'
        escalation_percent = request.POST.get('escalation_percentage')
        
        if not new_start_date or not new_end_date:
            messages.error(request, 'New agreement dates are required')
            return redirect('operations:renewal_tracker_detail', tracker_id=tracker.id)
        
        try:
            new_start_date = datetime.strptime(new_start_date, '%Y-%m-%d').date()
            new_end_date = datetime.strptime(new_end_date, '%Y-%m-%d').date()
            
            if new_end_date <= new_start_date:
                messages.error(request, 'End date must be after start date')
                return redirect('operations:renewal_tracker_detail', tracker_id=tracker.id)
            
            # Determine escalation percentage
            escalation_pct = None
            if apply_escalation:
                if escalation_percent:
                    escalation_pct = float(escalation_percent)
                else:
                    escalation_pct = float(tracker.project_card.annual_escalation_percent or 0)
            
            # Create new ProjectCard version
            old_card = tracker.project_card
            new_card = old_card.create_new_version(
                user=request.user,
                escalation_percent=escalation_pct,
                new_agreement_dates={
                    'start': new_start_date,
                    'end': new_end_date
                }
            )
            
            # Update tracker
            tracker.renewal_completed_date = timezone.now().date()
            tracker.status = 'renewed'
            tracker.last_updated_by = request.user
            tracker.save()
            
            # Create log entry
            escalation_note = f' with {escalation_pct}% escalation' if apply_escalation else ''
            AgreementRenewalLog.objects.create(
                tracker=tracker,
                action_type='renewed',
                action_date=timezone.now().date(),
                notes=f'Renewal completed{escalation_note}. New ProjectCard v{new_card.version} created for {new_start_date} to {new_end_date}.',
                performed_by=request.user,
            )
            
            messages.success(
                request, 
                f'Renewal completed! New ProjectCard v{new_card.version} created.'
            )
            return redirect('operations:project_card_detail', card_id=new_card.id)
            
        except Exception as e:
            messages.error(request, f'Error completing renewal: {str(e)}')
            return redirect('operations:renewal_tracker_detail', tracker_id=tracker.id)
    
    # Suggest next period dates
    old_card = tracker.project_card
    if old_card.agreement_end_date:
        suggested_start = old_card.agreement_end_date + timedelta(days=1)
        
        # Calculate duration of current agreement
        if old_card.agreement_start_date:
            duration = relativedelta(old_card.agreement_end_date, old_card.agreement_start_date)
            suggested_end = suggested_start + duration
        else:
            # Default to 1 year
            suggested_end = suggested_start + relativedelta(years=1) - timedelta(days=1)
    else:
        suggested_start = None
        suggested_end = None
    
    context = {
        'tracker': tracker,
        'suggested_start_date': suggested_start,
        'suggested_end_date': suggested_end,
        'current_escalation_percent': old_card.annual_escalation_percent,
    }
    
    return render(request, 'operations/renewal_tracker_complete_renewal.html', context)


@login_required
def renewal_tracker_update_status(request, tracker_id):
    """
    Update renewal tracker status
    """
    tracker = get_object_or_404(AgreementRenewalTracker, id=tracker_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        old_status = tracker.status
        tracker.status = new_status
        tracker.last_updated_by = request.user
        tracker.save()
        
        # Create log entry
        AgreementRenewalLog.objects.create(
            tracker=tracker,
            action_type='status_changed',
            action_date=timezone.now().date(),
            notes=f'Status changed from {old_status} to {new_status}. {notes}',
            performed_by=request.user,
        )
        
        messages.success(request, f'Status updated to {tracker.get_status_display()}')
        return redirect('operations:renewal_tracker_detail', tracker_id=tracker.id)
    
    context = {
        'tracker': tracker,
        'status_choices': AgreementRenewalTracker.STATUS_CHOICES,
    }
    
    return render(request, 'operations/renewal_tracker_update_status.html', context)