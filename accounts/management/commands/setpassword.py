from django.core.management.base import BaseCommand
from accounts.models import User

class Command(BaseCommand):
    help = 'Set user password non-interactively'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)
        parser.add_argument('password', type=str)

    def handle(self, *args, **options):
        user = User.objects.get(username=options['username'])
        user.set_password(options['password'])
        user.save()
        self.stdout.write(self.success_message(f"Password updated for {options['username']}"))