"""
Utility functions for identifying incomplete project cards
"""

def get_incomplete_projects():
    """
    Get all active projects with incomplete project cards.
    
    Returns:
        list: List of dicts with project and missing_items
        [
            {
                'project': ProjectCode object,
                'project_card': ProjectCard object or None,
                'missing_items': ['Payment terms', 'Storage rates', ...]
            },
            ...
        ]
    """
    from projects.models import ProjectCode
    from operations.models_projectcard import ProjectCard
    
    # Get all active WAAS projects only
    active_projects = ProjectCode.objects.filter(
        series_type='WAAS',
        project_status__in=['Active', 'Operation Not Started', 'Notice Period']
    )
    
    incomplete_list = []
    
    for project in active_projects:
        # Get most recent project card
        project_card = ProjectCard.objects.filter(project=project).order_by('-created_at').first()
        
        missing_items = []
        
        # Check if project card exists
        if not project_card:
            incomplete_list.append({
                'project': project,
                'project_card': None,
                'missing_items': ['Project Card not created']
            })
            continue
        
        # Check payment terms
        if not project_card.storage_payment_days and not project_card.handling_payment_days:
            missing_items.append('Payment terms')
        
        # Check storage rates (client commercials)
        if not project_card.storage_rates.exists():
            missing_items.append('Storage rates')
        
        # Check handling rates (client commercials)
        if not project_card.handling_rates.exists():
            missing_items.append('Handling rates')
        
        # Check agreement details
        if not project_card.agreement_start_date or not project_card.agreement_end_date:
            missing_items.append('Agreement dates')
        
        # If any items missing, add to list
        if missing_items:
            incomplete_list.append({
                'project': project,
                'project_card': project_card,
                'missing_items': missing_items
            })
    
    return incomplete_list


def get_incomplete_projects_count():
    """
    Get count of incomplete projects.
    
    Returns:
        int: Count of projects with incomplete project cards
    """
    return len(get_incomplete_projects())