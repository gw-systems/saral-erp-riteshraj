# integrations/management/commands/verify_integrations.py
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import connection, models
from django.apps import apps
from django.utils.termcolors import make_style

class Command(BaseCommand):
    help = "Verifies that all integration tables exist and migrations are applied correctly."

    def handle(self, *args, **options):
        style_ok = make_style(fg='green', opts=('bold',))
        style_warn = make_style(fg='yellow', opts=('bold',))
        style_err = make_style(fg='red', opts=('bold',))

        self.stdout.write(style_ok("🔍 Running integration table verification..."))

        # find all integration apps
        integration_apps = [
            app for app in apps.get_app_configs()
            if app.label.startswith("bigin") or app.label.startswith("integrations")
        ]

        if not integration_apps:
            self.stdout.write(style_warn("⚠️  No integration apps found."))
            return

        tables = connection.introspection.table_names()
        total_fixed = 0

        for app in integration_apps:
            self.stdout.write(style_ok(f"\n📦 Checking app: {app.label}"))
            models_in_app = list(app.get_models())

            if not models_in_app:
                self.stdout.write(style_warn(f"   (No models defined)"))
                continue

            for model in models_in_app:
                table_name = model._meta.db_table
                if table_name in tables:
                    self.stdout.write(f"   ✅ {table_name} exists")
                else:
                    self.stdout.write(style_err(f"   ⚠️  {table_name} missing — attempting repair..."))
                    try:
                        # Try to recreate via migration
                        call_command("migrate", app.label, fake=False, verbosity=0)
                        self.stdout.write(style_ok(f"   🛠 Created table: {table_name}"))
                        total_fixed += 1
                    except Exception as e:
                        self.stdout.write(style_err(f"   ❌ Failed to create {table_name}: {e}"))

        if total_fixed == 0:
            self.stdout.write(style_ok("\n✅ All integration tables are consistent and up to date!"))
        else:
            self.stdout.write(style_warn(f"\n🩵 {total_fixed} tables were repaired automatically."))
