"""
Full Sync Test - All Apps with Real Data
Performs actual full syncs and tracks completion time for each app
"""

import os
import sys
import django
import time
from datetime import datetime

# Setup Django
sys.path.insert(0, '/Users/apple/Documents/DataScienceProjects/ERP')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'minierp.settings')
django.setup()

class Colors:
    HEADER = '\033[95m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def format_duration(seconds):
    """Format duration in human-readable format"""
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.2f}s"

def test_google_ads_full_sync():
    """Test Google Ads full sync with real data"""
    print_header("1. Google Ads Full Sync")

    try:
        from integrations.google_ads.models import GoogleAdsToken
        from integrations.google_ads.google_ads_sync import GoogleAdsSync

        tokens = GoogleAdsToken.objects.filter(is_active=True)

        if not tokens.exists():
            print(f"{Colors.WARNING}⚠ No active Google Ads tokens - SKIPPED{Colors.ENDC}")
            return None

        print(f"Found {tokens.count()} active token(s)")

        start_time = time.time()

        for token in tokens:
            print(f"\nSyncing: {token.account_name}")
            sync_engine = GoogleAdsSync(token.id)
            stats = sync_engine.sync_all(
                sync_yesterday=True,
                sync_current_month_search_terms=True
            )
            print(f"  Campaigns: {stats['campaigns']['total']}")
            print(f"  Performance: {stats['performance']['total']}")
            print(f"  Device Performance: {stats['device_performance']['total']}")
            print(f"  Search Terms: {stats['search_terms']['total']}")

        duration = time.time() - start_time
        print(f"\n{Colors.OKGREEN}✓ Google Ads sync completed in {format_duration(duration)}{Colors.ENDC}")
        return duration

    except Exception as e:
        print(f"{Colors.FAIL}✗ Google Ads sync failed: {e}{Colors.ENDC}")
        return None

def test_gmail_leads_full_sync():
    """Test Gmail Leads full sync"""
    print_header("2. Gmail Leads Full Sync")

    try:
        from integrations.gmail_leads.gmail_leads_sync import sync_all_gmail_leads_accounts

        start_time = time.time()
        stats = sync_all_gmail_leads_accounts(force_full=False)
        duration = time.time() - start_time

        print(f"Total accounts: {stats['total_accounts']}")
        print(f"Successful: {stats['successful']}")
        print(f"Failed: {stats['failed']}")
        print(f"Leads created: {stats['total_leads_created']}")

        print(f"\n{Colors.OKGREEN}✓ Gmail Leads sync completed in {format_duration(duration)}{Colors.ENDC}")
        return duration

    except Exception as e:
        print(f"{Colors.FAIL}✗ Gmail Leads sync failed: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return None

def test_gmail_full_sync():
    """Test Gmail full sync"""
    print_header("3. Gmail Full Sync")

    try:
        from gmail.gmail_sync import sync_all_gmail_accounts

        start_time = time.time()
        stats = sync_all_gmail_accounts(force_full=False)
        duration = time.time() - start_time

        print(f"Total accounts: {stats['total_accounts']}")
        print(f"Successful: {stats['successful']}")
        print(f"Total emails: {stats['total_emails']}")

        print(f"\n{Colors.OKGREEN}✓ Gmail sync completed in {format_duration(duration)}{Colors.ENDC}")
        return duration

    except Exception as e:
        print(f"{Colors.FAIL}✗ Gmail sync failed: {e}{Colors.ENDC}")
        return None

def test_bigin_full_sync():
    """Test Bigin full sync"""
    print_header("4. Bigin Full Sync")

    try:
        from integrations.bigin.sync_service import run_sync_all_modules

        start_time = time.time()
        run_sync_all_modules(run_full=False, triggered_by_user='test_script')
        duration = time.time() - start_time

        print(f"\n{Colors.OKGREEN}✓ Bigin sync completed in {format_duration(duration)}{Colors.ENDC}")
        return duration

    except RuntimeError as e:
        if "already running" in str(e):
            print(f"{Colors.WARNING}⚠ Another sync already running - SKIPPED{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}✗ Bigin sync failed: {e}{Colors.ENDC}")
        return None
    except Exception as e:
        print(f"{Colors.FAIL}✗ Bigin sync failed: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return None

def test_tallysync_full_sync():
    """Test TallySync full sync"""
    print_header("5. TallySync Full Sync")

    try:
        from integrations.tallysync.services.sync_service import TallySyncService
        from integrations.tallysync.services.snapshot_service import SnapshotService
        from integrations.tallysync.models import TallyCompany
        from django.utils import timezone as tz
        from datetime import timedelta

        companies = TallyCompany.objects.filter(is_active=True)

        if not companies.exists():
            print(f"{Colors.WARNING}⚠ No active Tally companies - SKIPPED{Colors.ENDC}")
            return None

        print(f"Found {companies.count()} active company(ies)")

        start_time = time.time()
        sync_service = TallySyncService()

        today = tz.now().date()
        week_ago = today - timedelta(days=7)

        synced = 0
        for company in companies:
            print(f"\nSyncing: {company.name}")
            result = sync_service.sync_vouchers(
                company=company,
                from_date=week_ago.strftime('%Y%m%d'),
                to_date=today.strftime('%Y%m%d')
            )
            if result['status'] == 'success':
                print(f"  Processed: {result['processed']} vouchers")
                synced += 1

        # Update snapshots
        print(f"\nUpdating snapshots...")
        snapshot_service = SnapshotService()
        snapshot_result = snapshot_service.populate_project_snapshots()
        print(f"  Created: {snapshot_result['created']}")
        print(f"  Updated: {snapshot_result['updated']}")

        duration = time.time() - start_time
        print(f"\n{Colors.OKGREEN}✓ TallySync completed in {format_duration(duration)}{Colors.ENDC}")
        return duration

    except Exception as e:
        print(f"{Colors.FAIL}✗ TallySync failed: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return None

def test_callyzer_full_sync():
    """Test Callyzer full sync"""
    print_header("6. Callyzer Full Sync")

    try:
        from integrations.callyzer.callyzer_sync import sync_all_callyzer_accounts

        start_time = time.time()
        stats = sync_all_callyzer_accounts(days_back=150)
        duration = time.time() - start_time

        print(f"Total accounts: {stats['total_accounts']}")
        print(f"Successful: {stats['successful']}")

        print(f"\n{Colors.OKGREEN}✓ Callyzer sync completed in {format_duration(duration)}{Colors.ENDC}")
        return duration

    except Exception as e:
        print(f"{Colors.FAIL}✗ Callyzer sync failed: {e}{Colors.ENDC}")
        return None

def main():
    print_header("Full Sync Test - All Apps with Real Data")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = {}
    total_start = time.time()

    # Run all sync tests
    results['Google Ads'] = test_google_ads_full_sync()
    results['Gmail Leads'] = test_gmail_leads_full_sync()
    results['Gmail'] = test_gmail_full_sync()
    results['Bigin'] = test_bigin_full_sync()
    results['TallySync'] = test_tallysync_full_sync()
    results['Callyzer'] = test_callyzer_full_sync()

    total_duration = time.time() - total_start

    # Summary
    print_header("Summary - Sync Completion Times")

    print(f"{Colors.BOLD}{'App':<20} {'Status':<15} {'Duration':<15}{Colors.ENDC}")
    print("-" * 50)

    for app, duration in results.items():
        if duration is not None:
            status = f"{Colors.OKGREEN}✓ Completed{Colors.ENDC}"
            time_str = format_duration(duration)
        else:
            status = f"{Colors.WARNING}⚠ Skipped/Failed{Colors.ENDC}"
            time_str = "N/A"

        print(f"{app:<20} {status:<24} {time_str:<15}")

    print("-" * 50)
    print(f"{'Total Time:':<20} {Colors.BOLD}{format_duration(total_duration)}{Colors.ENDC}")

    # Calculate successful syncs
    successful = sum(1 for d in results.values() if d is not None)
    print(f"\n{Colors.BOLD}Successful syncs: {successful}/{len(results)}{Colors.ENDC}")
    print(f"\n{Colors.BOLD}Finished at:{Colors.ENDC} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()
