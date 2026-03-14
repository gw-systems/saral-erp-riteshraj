from django.core.management.base import BaseCommand
from integrations.tallysync.services.sync_service import TallySyncService
import json


class Command(BaseCommand):
    help = 'Sync data from Tally to Django database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            default='all',
            help='Sync type: all, companies, master_data'
        )

    def handle(self, *args, **options):
        sync_type = options['type']
        service = TallySyncService()
        
        # Test connection first
        self.stdout.write("Testing Tally connection...")
        connection_result = service.test_connection()
        if not connection_result['success']:
            self.stdout.write(self.style.ERROR(connection_result['message']))
            self.stdout.write(self.style.WARNING(f"Status: {connection_result['status']}"))
            if connection_result['details']:
                self.stdout.write(f"Details: {json.dumps(connection_result['details'], indent=2)}")
            return

        self.stdout.write(self.style.SUCCESS(connection_result['message']))
        self.stdout.write(f"Server: {connection_result['details'].get('server_type', 'Unknown')}")
        self.stdout.write(f"Response time: {connection_result['details'].get('response_time_ms', 0):.0f}ms")
        
        if sync_type == 'companies':
            self.stdout.write("Syncing companies...")
            result = service.sync_companies(triggered_by_user='management_command')
            self._print_result(result)

        elif sync_type == 'master_data' or sync_type == 'all':
            self.stdout.write("Syncing all master data...")
            results = service.sync_all_master_data(triggered_by_user='management_command')
            
            self.stdout.write("\n📊 Companies:")
            self._print_result(results['companies'])
            
            for company_name, result in results['groups'].items():
                self.stdout.write(f"\n📁 Groups - {company_name}:")
                self._print_result(result)
            
            for company_name, result in results['ledgers'].items():
                self.stdout.write(f"\n📒 Ledgers - {company_name}:")
                self._print_result(result)
            
            for company_name, result in results['cost_centres'].items():
                self.stdout.write(f"\n🎯 Cost Centres - {company_name}:")
                self._print_result(result)
        
        self.stdout.write(self.style.SUCCESS('\n✅ Sync completed!'))
    
    def _print_result(self, result):
        if result['status'] == 'success':
            self.stdout.write(
                f"  ✅ Processed: {result['processed']}, "
                f"Created: {result['created']}, "
                f"Updated: {result['updated']}"
            )
        else:
            self.stdout.write(self.style.ERROR(f"  ❌ Error: {result.get('error')}"))