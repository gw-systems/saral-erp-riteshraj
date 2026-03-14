from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = 'Create initial users for all roles (for testing)'

    def handle(self, *args, **kwargs):
        """
        Create sample users for each role
        """
        
        roles_to_create = [
            # Tier 1
            ('admin', 'Admin', 'User', 'admin@godamwale.com'),
            ('super_user', 'Super', 'User', 'superuser@godamwale.com'),
            
            # Tier 2
            ('director', 'Director', 'User', 'director@godamwale.com'),
            
            # Tier 3
            ('finance_manager', 'Finance', 'Manager', 'finance@godamwale.com'),
            ('operation_controller', 'Operation', 'Controller', 'opcontroller@godamwale.com'),
            ('operation_manager', 'Operation', 'Manager', 'opmanager@godamwale.com'),
            ('sales_manager', 'Sales', 'Manager', 'sales@godamwale.com'),
            
            # Tier 4
            ('operation_coordinator', 'Operation', 'Coordinator', 'opcoordinator@godamwale.com'),
            ('warehouse_manager', 'Warehouse', 'Manager', 'warehouse@godamwale.com'),
            ('backoffice', 'Back', 'Office', 'backoffice@godamwale.com'),
            ('crm_executive', 'CRM', 'Executive', 'crm@godamwale.com'),
            
            # Tier 5
            ('client', 'Client', 'User', 'client@example.com'),
            ('vendor', 'Vendor', 'User', 'vendor@example.com'),
        ]
        
        created_count = 0
        existing_count = 0
        
        for role, first_name, last_name, email in roles_to_create:
            # Check if user already exists
            if User.objects.filter(username=role).exists():
                self.stdout.write(
                    self.style.WARNING(f'User {role} already exists')
                )
                existing_count += 1
                continue
            
            # Create user
            user = User.objects.create_user(
                username=role,
                email=email,
                password='password123',  # Change in production
                first_name=first_name,
                last_name=last_name,
                role=role,
                is_active=True,
            )
            
            # Make admin and super_user as staff
            if role in ['admin', 'super_user']:
                user.is_staff = True
                user.is_superuser = (role == 'admin')
                user.save()
            
            self.stdout.write(
                self.style.SUCCESS(f'Created user: {role} ({email})')
            )
            created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary: Created {created_count} users, '
                f'{existing_count} already existed'
            )
        )
        self.stdout.write(
            self.style.WARNING(
                '\nDefault password for all users: password123'
            )
        )
        self.stdout.write(
            self.style.WARNING(
                'IMPORTANT: Change passwords in production!'
            )
        )