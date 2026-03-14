"""
Management command to automatically create renewal and escalation trackers
Run daily via cron: python manage.py create_renewal_escalation_trackers
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from operations.models_projectcard import ProjectCard
from operations.models_agreements import AgreementRenewalTracker, EscalationTracker
from projects.models import ProjectCode


class Command(BaseCommand):
    help = 'Auto-create renewal and escalation trackers 60 days in advance'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.now().date()
        
        # 60 days from now
        target_date = today + timedelta(days=60)
        
        self.stdout.write(self.style.SUCCESS(f'\n🔍 Checking for renewals and escalations due around {target_date}...\n'))
        
        # Get all active WAAS projects
        active_projects = ProjectCode.objects.filter(
            series_type='WAAS',
            project_status__in=['Active', 'Operation Not Started', 'Notice Period']
        )
        
        self.stdout.write(f'Found {active_projects.count()} active WAAS projects\n')
        
        renewal_created = 0
        escalation_created = 0
        renewal_skipped = 0
        escalation_skipped = 0
        
        # ============================================================
        # RENEWAL TRACKERS
        # ============================================================
        self.stdout.write(self.style.WARNING('\n--- CHECKING RENEWALS ---'))
        
        for project in active_projects:
            # Get latest project card
            project_card = ProjectCard.objects.filter(
                project=project
            ).order_by('-created_at').first()
            
            if not project_card:
                continue
            
            if not project_card.agreement_end_date:
                continue
            
            # Check if agreement expires in next 60 days OR already expired
            days_until_expiry = (project_card.agreement_end_date - today).days
            
            # Create tracker if:
            # 1. Expiring in next 60 days (0 to 60 days)
            # 2. Already expired (negative days)
            if days_until_expiry <= 60:
                # Check if tracker already exists
                existing = AgreementRenewalTracker.objects.filter(
                    project_card=project_card
                ).first()
                
                if existing:
                    renewal_skipped += 1
                    status_emoji = '⏭️'
                    if days_until_expiry < 0:
                        status_emoji = '🚨'
                    self.stdout.write(
                        f'{status_emoji} SKIP: {project.project_code} - Tracker exists (Expires: {project_card.agreement_end_date}, Status: {existing.status})'
                    )
                    continue
                
                # Determine urgency
                if days_until_expiry < 0:
                    urgency = f'🚨 OVERDUE by {abs(days_until_expiry)} days'
                elif days_until_expiry <= 15:
                    urgency = f'🔴 URGENT - {days_until_expiry} days left'
                elif days_until_expiry <= 30:
                    urgency = f'🟠 SOON - {days_until_expiry} days left'
                else:
                    urgency = f'🟡 {days_until_expiry} days left'
                
                if dry_run:
                    self.stdout.write(
                        f'  [DRY RUN] Would create renewal tracker: {project.project_code} - {urgency}'
                    )
                else:
                    # Create tracker (no created_by for automated creation)
                    tracker = AgreementRenewalTracker.objects.create(
                        project_card=project_card,
                        status='pending',
                        created_by=None,  # System-created
                        remarks=f'Auto-created by system on {today}'
                    )
                    renewal_created += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'  ✅ Created renewal tracker: {project.project_code} - {urgency}')
                    )
        
        # ============================================================
        # ESCALATION TRACKERS
        # ============================================================
        self.stdout.write(self.style.WARNING('\n\n--- CHECKING ESCALATIONS ---'))
        
        for project in active_projects:
            project_card = ProjectCard.objects.filter(
                project=project
            ).order_by('-created_at').first()
            
            if not project_card:
                continue
            
            if not project_card.agreement_start_date or not project_card.agreement_end_date:
                continue
            
            # Skip if no escalation configured
            if not project_card.has_fixed_escalation:
                continue
            
            # Calculate all escalation dates for this agreement
            agreement_start = project_card.agreement_start_date
            agreement_end = project_card.agreement_end_date
            
            # Calculate agreement duration in years
            agreement_years = (agreement_end - agreement_start).days / 365.25
            
            # Generate escalation dates (Year 2, Year 3, etc.)
            escalation_dates = []
            for year in range(1, int(agreement_years) + 1):
                escalation_date = agreement_start + timedelta(days=365 * year)
                
                # Only if escalation date is before agreement end
                if escalation_date < agreement_end:
                    escalation_dates.append((year + 1, escalation_date))  # Year 2, Year 3, etc.
            
            # Check each escalation date
            for escalation_year, escalation_date in escalation_dates:
                days_until_escalation = (escalation_date - today).days
                
                # Create tracker if escalation in next 60 days OR already passed
                if days_until_escalation <= 60:
                    # Check if tracker already exists for this year
                    existing = EscalationTracker.objects.filter(
                        project_card=project_card,
                        escalation_year=escalation_year
                    ).first()
                    
                    if existing:
                        escalation_skipped += 1
                        status_emoji = '⏭️'
                        if days_until_escalation < 0:
                            status_emoji = '🚨'
                        self.stdout.write(
                            f'{status_emoji} SKIP: {project.project_code} - Year {escalation_year} tracker exists (Due: {escalation_date}, Status: {existing.status})'
                        )
                        continue
                    
                    # Determine urgency
                    if days_until_escalation < 0:
                        urgency = f'🚨 OVERDUE by {abs(days_until_escalation)} days'
                    elif days_until_escalation <= 15:
                        urgency = f'🔴 URGENT - {days_until_escalation} days left'
                    elif days_until_escalation <= 30:
                        urgency = f'🟠 SOON - {days_until_escalation} days left'
                    else:
                        urgency = f'🟡 {days_until_escalation} days left'
                    
                    if dry_run:
                        self.stdout.write(
                            f'  [DRY RUN] Would create escalation tracker: {project.project_code} - Year {escalation_year} - {urgency}'
                        )
                    else:
                        # Create tracker
                        tracker = EscalationTracker.objects.create(
                            project_card=project_card,
                            escalation_year=escalation_year,
                            escalation_percentage=project_card.annual_escalation_percent,
                            status='pending',
                            created_by=None,  # System-created
                            remarks=f'Auto-created by system on {today}'
                        )
                        escalation_created += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'  ✅ Created escalation tracker: {project.project_code} - Year {escalation_year} - {urgency}')
                        )
        
        # ============================================================
        # SUMMARY
        # ============================================================
        self.stdout.write(self.style.SUCCESS('\n\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write(self.style.SUCCESS('='*60))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n🔍 DRY RUN MODE - Nothing was created\n'))
        
        self.stdout.write(f'📋 Renewals:')
        self.stdout.write(f'   ✅ Created: {renewal_created}')
        self.stdout.write(f'   ⏭️  Skipped (exists): {renewal_skipped}')
        
        self.stdout.write(f'\n📈 Escalations:')
        self.stdout.write(f'   ✅ Created: {escalation_created}')
        self.stdout.write(f'   ⏭️  Skipped (exists): {escalation_skipped}')
        
        self.stdout.write(f'\n📊 Total:')
        self.stdout.write(f'   ✅ Total Created: {renewal_created + escalation_created}')
        self.stdout.write(f'   ⏭️  Total Skipped: {renewal_skipped + escalation_skipped}')
        
        self.stdout.write(self.style.SUCCESS('\n✅ Done!\n'))