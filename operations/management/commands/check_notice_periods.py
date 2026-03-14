"""
Daily cron job to check notice periods and send alerts
Run daily at 9 AM: python manage.py check_notice_periods
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from projects.models import ProjectCode
from operations.models import InAppAlert
from accounts.models import User


class Command(BaseCommand):
    help = 'Check notice periods and send alerts for expiring projects'

    def handle(self, *args, **kwargs):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        # Get all projects in Notice Period
        notice_projects = ProjectCode.objects.filter(
            project_status='Notice Period',
            notice_period_end_date__isnull=False
        )
        
        self.stdout.write(f"Checking {notice_projects.count()} projects in Notice Period...")
        
        expiring_tomorrow = []
        expiring_today = []
        
        for project in notice_projects:
            end_date = project.notice_period_end_date
            
            # Projects expiring tomorrow (1 day warning)
            if end_date == tomorrow:
                expiring_tomorrow.append(project)
                self.send_expiry_warning(project, days_left=1)
            
            # Projects expiring today (auto-deactivate)
            elif end_date == today:
                expiring_today.append(project)
                self.auto_deactivate_project(project)
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Notice Period Check Complete:\n'
                f'  - {len(expiring_tomorrow)} projects expiring tomorrow (alerts sent)\n'
                f'  - {len(expiring_today)} projects expired today (auto-deactivated)'
            )
        )
    
    def send_expiry_warning(self, project, days_left):
        """Send alert to managers that notice period is ending"""
        # Get operation managers and controllers
        recipients = User.objects.filter(
            role__in=['operation_manager', 'operation_controller', 'admin'],
            is_active=True
        )
        
        message = (
            f"⚠️ Notice Period Ending: {project.code} ({project.client_name})\n"
            f"End Date: {project.notice_period_end_date}\n"
            f"Days Left: {days_left}\n"
            f"Action: Project will auto-deactivate tomorrow unless extended."
        )
        
        for user in recipients:
            InAppAlert.objects.create(
                user=user,
                alert_type='manager_notification',
                title=f'Notice Period Expiring: {project.code}',
                message=message,
                severity='warning',
                related_url=f'/projects/status/change/{project.project_id}/'
            )
        
        self.stdout.write(f"  ⚠️  Alert sent for {project.code} (expires in {days_left} day)")
    
    def auto_deactivate_project(self, project):
        """Automatically move project to Inactive status"""
        project.project_status = 'Inactive'
        project.operation_coordinator = None
        project.backup_coordinator = None
        project.updated_at = timezone.now()
        project.save()
        
        # Notify managers
        recipients = User.objects.filter(
            role__in=['operation_manager', 'operation_controller', 'admin'],
            is_active=True
        )
        
        message = (
            f"🔒 Project Auto-Deactivated: {project.code} ({project.client_name})\n"
            f"Notice period ended on: {project.notice_period_end_date}\n"
            f"Status: Now Inactive\n"
            f"Coordinators: Cleared"
        )
        
        for user in recipients:
            InAppAlert.objects.create(
                user=user,
                alert_type='system_alert',
                title=f'Project Deactivated: {project.code}',
                message=message,
                severity='info',
                related_url='/projects/list/all/'
            )
        
        self.stdout.write(
            self.style.WARNING(f"  🔒 Auto-deactivated: {project.code}")
        )