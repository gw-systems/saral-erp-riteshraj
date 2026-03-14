"""
Helper functions for Agreement Renewal & Escalation system
Auto-create trackers, batch operations, analytics
"""

from django.utils import timezone
from django.db.models import Q, Count, Min, Max
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from operations.models_projectcard import ProjectCard
from operations.models_agreements import EscalationTracker, AgreementRenewalTracker


# ==================== AUTO-CREATE TRACKERS ====================

def auto_create_escalation_trackers(project_card, user=None):
    """
    Auto-create escalation trackers based on agreement duration
    Called when new ProjectCard is created or agreement is renewed
    
    Example: 3-year agreement → creates Year 1, Year 2, Year 3 trackers
    """
    if not project_card.agreement_start_date or not project_card.agreement_end_date:
        return []
    
    # Calculate agreement duration in years
    duration = relativedelta(project_card.agreement_end_date, project_card.agreement_start_date)
    total_years = duration.years
    
    # If duration has extra months, add one more year
    if duration.months > 0 or duration.days > 0:
        total_years += 1
    
    created_trackers = []
    
    # Create tracker for each escalation year
    for year in range(1, total_years + 1):
        # Check if tracker already exists
        existing = EscalationTracker.objects.filter(
            project_card=project_card,
            escalation_year=year
        ).first()
        
        if not existing:
            # Determine escalation percentage
            escalation_pct = None
            if project_card.escalation_terms == 'FIXED':
                escalation_pct = project_card.annual_escalation_percent
            
            # Create tracker
            tracker = EscalationTracker.objects.create(
                project_card=project_card,
                escalation_year=year,
                escalation_percentage=escalation_pct,
                status='pending',
                created_by=user,
                last_updated_by=user,
            )
            created_trackers.append(tracker)
    
    return created_trackers


def auto_create_renewal_tracker(project_card, user=None):
    """
    Auto-create renewal tracker for a project card
    Called when agreement is approaching end date
    """
    if not project_card.agreement_end_date:
        return None
    
    # Check if renewal tracker already exists
    existing = AgreementRenewalTracker.objects.filter(
        project_card=project_card,
        status__in=['pending', 'in_progress', 'client_responded']
    ).first()
    
    if existing:
        return existing
    
    # Create renewal tracker
    tracker = AgreementRenewalTracker.objects.create(
        project_card=project_card,
        status='pending',
        created_by=user,
        last_updated_by=user,
    )
    
    return tracker


def create_trackers_for_all_active_cards(user=None):
    """
    Batch operation: Create missing trackers for all active ProjectCards
    Useful for initial setup or data migration
    """
    active_cards = ProjectCard.objects.filter(is_active=True)
    
    stats = {
        'cards_processed': 0,
        'escalation_trackers_created': 0,
        'renewal_trackers_created': 0,
        'errors': []
    }
    
    for card in active_cards:
        try:
            # Create escalation trackers
            escalation_trackers = auto_create_escalation_trackers(card, user)
            stats['escalation_trackers_created'] += len(escalation_trackers)
            
            # Create renewal tracker if agreement end date exists
            if card.agreement_end_date:
                renewal_tracker = auto_create_renewal_tracker(card, user)
                if renewal_tracker:
                    stats['renewal_trackers_created'] += 1
            
            stats['cards_processed'] += 1
            
        except Exception as e:
            stats['errors'].append(f"Error with card {card.id}: {str(e)}")
    
    return stats


# ==================== ANALYTICS & QUERIES ====================

def get_escalation_dashboard_stats():
    """
    Get summary statistics for escalation dashboard
    """
    today = timezone.now().date()
    
    # All active trackers
    all_trackers = EscalationTracker.objects.select_related('project_card__project').all()
    
    # Categorize trackers
    overdue = []
    upcoming_30_days = []
    upcoming_60_days = []
    in_progress = []
    
    for tracker in all_trackers:
        escalation_date = tracker.escalation_effective_date
        
        if not escalation_date:
            continue
        
        if tracker.status == 'escalation_applied':
            continue
        
        days_until = (escalation_date - today).days
        
        if days_until < 0:  # Overdue
            overdue.append({
                'tracker': tracker,
                'days_overdue': abs(days_until),
                'project': tracker.project_card.project.project_code,
                'year': tracker.escalation_year,
            })
        elif days_until <= 30:  # Upcoming 30 days
            upcoming_30_days.append({
                'tracker': tracker,
                'days_until': days_until,
                'project': tracker.project_card.project.project_code,
                'year': tracker.escalation_year,
            })
        elif days_until <= 60:  # Upcoming 60 days
            upcoming_60_days.append({
                'tracker': tracker,
                'days_until': days_until,
                'project': tracker.project_card.project.project_code,
                'year': tracker.escalation_year,
            })
        
        if tracker.status == 'in_progress':
            in_progress.append(tracker)
    
    return {
        'total_active': all_trackers.count(),
        'overdue': sorted(overdue, key=lambda x: x['days_overdue'], reverse=True),
        'overdue_count': len(overdue),
        'upcoming_30': sorted(upcoming_30_days, key=lambda x: x['days_until']),
        'upcoming_30_count': len(upcoming_30_days),
        'upcoming_60': sorted(upcoming_60_days, key=lambda x: x['days_until']),
        'upcoming_60_count': len(upcoming_60_days),
        'in_progress': in_progress,
        'in_progress_count': len(in_progress),
    }


def get_renewal_dashboard_stats():
    """
    Get summary statistics for renewal dashboard
    """
    today = timezone.now().date()
    
    # All active trackers
    all_trackers = AgreementRenewalTracker.objects.select_related('project_card__project').all()
    
    # Categorize trackers
    overdue = []
    upcoming_30_days = []
    upcoming_60_days = []
    in_progress = []
    
    for tracker in all_trackers:
        renewal_date = tracker.renewal_due_date
        
        if not renewal_date:
            continue
        
        if tracker.status in ['renewed', 'not_renewed', 'cancelled']:
            continue
        
        days_until = (renewal_date - today).days
        
        if days_until < 0:  # Overdue
            overdue.append({
                'tracker': tracker,
                'days_overdue': abs(days_until),
                'project': tracker.project_card.project.project_code,
            })
        elif days_until <= 30:  # Upcoming 30 days
            upcoming_30_days.append({
                'tracker': tracker,
                'days_until': days_until,
                'project': tracker.project_card.project.project_code,
            })
        elif days_until <= 60:  # Upcoming 60 days
            upcoming_60_days.append({
                'tracker': tracker,
                'days_until': days_until,
                'project': tracker.project_card.project.project_code,
            })
        
        if tracker.status == 'in_progress':
            in_progress.append(tracker)
    
    return {
        'total_active': all_trackers.count(),
        'overdue': sorted(overdue, key=lambda x: x['days_overdue'], reverse=True),
        'overdue_count': len(overdue),
        'upcoming_30': sorted(upcoming_30_days, key=lambda x: x['days_until']),
        'upcoming_30_count': len(upcoming_30_days),
        'upcoming_60': sorted(upcoming_60_days, key=lambda x: x['days_until']),
        'upcoming_60_count': len(upcoming_60_days),
        'in_progress': in_progress,
        'in_progress_count': len(in_progress),
    }


def get_trackers_needing_action():
    """
    Get all trackers that need immediate action
    Used for daily notification emails
    """
    today = timezone.now().date()
    
    needs_action = {
        'overdue_escalations': [],
        'overdue_renewals': [],
        'upcoming_escalations': [],
        'upcoming_renewals': [],
    }
    
    # Overdue escalations
    for tracker in EscalationTracker.objects.filter(status__in=['pending', 'in_progress']):
        if tracker.is_overdue:
            needs_action['overdue_escalations'].append({
                'project': tracker.project_card.project.project_code,
                'year': tracker.escalation_year,
                'days_overdue': tracker.days_overdue,
                'next_action': tracker.get_next_action()[0],
            })
    
    # Overdue renewals
    for tracker in AgreementRenewalTracker.objects.filter(status__in=['pending', 'in_progress']):
        if tracker.is_overdue:
            needs_action['overdue_renewals'].append({
                'project': tracker.project_card.project.project_code,
                'days_overdue': tracker.days_overdue,
                'next_action': tracker.get_next_action()[0],
            })
    
    # Upcoming escalations (within 7 days)
    for tracker in EscalationTracker.objects.filter(status='pending'):
        if tracker.days_until_due and 0 <= tracker.days_until_due <= 7:
            needs_action['upcoming_escalations'].append({
                'project': tracker.project_card.project.project_code,
                'year': tracker.escalation_year,
                'days_until': tracker.days_until_due,
                'escalation_date': tracker.escalation_effective_date,
            })
    
    # Upcoming renewals (within 7 days)
    for tracker in AgreementRenewalTracker.objects.filter(status='pending'):
        if tracker.days_until_due and 0 <= tracker.days_until_due <= 7:
            needs_action['upcoming_renewals'].append({
                'project': tracker.project_card.project.project_code,
                'days_until': tracker.days_until_due,
                'renewal_date': tracker.renewal_due_date,
            })
    
    return needs_action


# ==================== UTILITY FUNCTIONS ====================

def get_project_card_history(project):
    """
    Get complete version history of ProjectCards for a project
    Shows escalation trail
    """
    cards = ProjectCard.objects.filter(
        project=project
    ).order_by('version')
    
    history = []
    for card in cards:
        history.append({
            'version': card.version,
            'valid_from': card.valid_from,
            'valid_to': card.valid_to,
            'is_active': card.is_active,
            'agreement_period': f"{card.agreement_start_date} to {card.agreement_end_date}",
            'escalation_percentage': card.annual_escalation_percent,
        })
    
    return history


def find_applicable_project_card(project, date=None):
    """
    Find which ProjectCard version is applicable for a given date
    Used by billing system to determine rates
    """
    if date is None:
        date = timezone.now().date()
    
    # Find active card first
    active_card = ProjectCard.objects.filter(
        project=project,
        is_active=True
    ).first()
    
    if active_card and active_card.valid_from and active_card.valid_from <= date:
        if not active_card.valid_to or active_card.valid_to >= date:
            return active_card
    
    # Find historical card valid for this date
    historical_card = ProjectCard.objects.filter(
        project=project,
        valid_from__lte=date,
        valid_to__gte=date
    ).first()
    
    return historical_card


def check_tracker_consistency():
    """
    Audit function: Check for missing or duplicate trackers
    Returns issues that need to be fixed
    """
    issues = {
        'missing_escalation_trackers': [],
        'duplicate_escalation_trackers': [],
        'missing_renewal_trackers': [],
        'duplicate_renewal_trackers': [],
    }
    
    active_cards = ProjectCard.objects.filter(is_active=True)
    
    for card in active_cards:
        # Check escalation trackers
        if card.agreement_start_date and card.agreement_end_date:
            duration = relativedelta(card.agreement_end_date, card.agreement_start_date)
            expected_years = duration.years + (1 if duration.months > 0 or duration.days > 0 else 0)
            
            for year in range(1, expected_years + 1):
                trackers = EscalationTracker.objects.filter(
                    project_card=card,
                    escalation_year=year
                )
                
                if trackers.count() == 0:
                    issues['missing_escalation_trackers'].append({
                        'project': card.project.project_code,
                        'card_version': card.version,
                        'missing_year': year,
                    })
                elif trackers.count() > 1:
                    issues['duplicate_escalation_trackers'].append({
                        'project': card.project.project_code,
                        'card_version': card.version,
                        'year': year,
                        'count': trackers.count(),
                    })
        
        # Check renewal tracker
        if card.agreement_end_date:
            renewal_trackers = AgreementRenewalTracker.objects.filter(
                project_card=card,
                status__in=['pending', 'in_progress']
            )
            
            if renewal_trackers.count() == 0:
                # Only flag if renewal is within 90 days
                days_until = (card.agreement_end_date - timezone.now().date()).days
                if days_until <= 90:
                    issues['missing_renewal_trackers'].append({
                        'project': card.project.project_code,
                        'card_version': card.version,
                        'agreement_end': card.agreement_end_date,
                        'days_until': days_until,
                    })
            elif renewal_trackers.count() > 1:
                issues['duplicate_renewal_trackers'].append({
                    'project': card.project.project_code,
                    'card_version': card.version,
                    'count': renewal_trackers.count(),
                })
    
    return issues