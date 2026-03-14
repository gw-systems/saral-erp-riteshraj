from django.core.management.base import BaseCommand
from projects.models import ProjectCode
from accounts.models import User


class Command(BaseCommand):
    help = 'Sync project managers - No longer needed as assignments are in ProjectCode model'

    def handle(self, *args, **kwargs):
        self.stdout.write(
            self.style.WARNING(
                'This command is deprecated. '
                'Project assignments are now stored directly in ProjectCode model '
                'via operation_coordinator and backup_coordinator fields.'
            )
        )
        
        # Show current assignments
        projects = ProjectCode.objects.all()
        
        for project in projects:
            if project.operation_coordinator or project.backup_coordinator:
                self.stdout.write(
                    f'Project {project.code}: '
                    f'Coordinator={project.operation_coordinator}, '
                    f'Backup={project.backup_coordinator}'
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nTotal projects: {projects.count()}'
            )
        )