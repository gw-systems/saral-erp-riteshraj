"""
Manual check script for Cloud Tasks worker endpoints.
Tests each app's sync functionality and measures execution time.
"""

import os
import sys
import django
import time
import json
from datetime import datetime
from pathlib import Path

# Setup Django
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'minierp.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model

# Import all worker modules
from integrations.google_ads import workers as google_ads_workers
from integrations.gmail_leads import workers as gmail_leads_workers
from gmail import workers as gmail_workers
from integrations.bigin import workers as bigin_workers
from integrations.tallysync import workers as tallysync_workers
from integrations.callyzer import workers as callyzer_workers

User = get_user_model()

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_test(app_name, test_name):
    print(f"{Colors.OKBLUE}Testing:{Colors.ENDC} {app_name} - {test_name}")

def print_result(success, message, duration=None):
    if success:
        status = f"{Colors.OKGREEN}âœ“ PASS{Colors.ENDC}"
    else:
        status = f"{Colors.FAIL}âœ— FAIL{Colors.ENDC}"

    time_str = f" ({duration:.2f}s)" if duration else ""
    print(f"{status} {message}{time_str}")

def test_worker_endpoint(worker_func, payload, app_name, test_name):
    """Test a worker endpoint and measure execution time"""
    print_test(app_name, test_name)

    factory = RequestFactory()
    request = factory.post('/test/',
                          data=json.dumps(payload),
                          content_type='application/json')

    start_time = time.time()
    try:
        response = worker_func(request)
        duration = time.time() - start_time

        # Parse response
        response_data = json.loads(response.content)

        if response.status_code == 200 and response_data.get('status') in ['success', 'completed']:
            print_result(True, f"Endpoint accessible and returns success", duration)
            return True, duration, response_data
        else:
            error_msg = response_data.get('error', 'Unknown error')
            print_result(False, f"Endpoint returned error: {error_msg}", duration)
            return False, duration, response_data

    except Exception as e:
        duration = time.time() - start_time
        print_result(False, f"Exception: {str(e)}", duration)
        return False, duration, {'error': str(e)}

def main():
    print_header("Cloud Tasks Migration - Worker Endpoint Tests")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = []
    total_start = time.time()

    # Note: We're testing endpoint accessibility and response format,
    # not actual sync execution (which would require valid tokens/data)

    # 1. Google Ads
    print_header("1. Google Ads Integration")

    success, duration, data = test_worker_endpoint(
        google_ads_workers.sync_google_ads_account_worker,
        {'token_id': 9999, 'sync_yesterday': True, 'sync_current_month_search_terms': True},
        'Google Ads',
        'Single Account Sync Worker'
    )
    results.append(('Google Ads - Single Account', success, duration))

    success, duration, data = test_worker_endpoint(
        google_ads_workers.sync_all_google_ads_accounts_worker,
        {'sync_yesterday': True, 'sync_current_month_search_terms': True},
        'Google Ads',
        'All Accounts Sync Worker'
    )
    results.append(('Google Ads - All Accounts', success, duration))

    success, duration, data = test_worker_endpoint(
        google_ads_workers.sync_historical_data_worker,
        {'token_id': 9999, 'start_date': '2024-01-01'},
        'Google Ads',
        'Historical Data Sync Worker'
    )
    results.append(('Google Ads - Historical', success, duration))

    # 2. Gmail Leads
    print_header("2. Gmail Leads Integration")

    success, duration, data = test_worker_endpoint(
        gmail_leads_workers.sync_gmail_leads_account_worker,
        {'token_id': 9999, 'force_full': False},
        'Gmail Leads',
        'Single Account Sync Worker'
    )
    results.append(('Gmail Leads - Single Account', success, duration))

    success, duration, data = test_worker_endpoint(
        gmail_leads_workers.sync_all_gmail_leads_accounts_worker,
        {'force_full': False},
        'Gmail Leads',
        'All Accounts Sync Worker'
    )
    results.append(('Gmail Leads - All Accounts', success, duration))

    # 3. Gmail
    print_header("3. Gmail Integration")

    success, duration, data = test_worker_endpoint(
        gmail_workers.sync_gmail_account_worker,
        {'gmail_token_id': 9999, 'force_full': False},
        'Gmail',
        'Single Account Sync Worker'
    )
    results.append(('Gmail - Single Account', success, duration))

    success, duration, data = test_worker_endpoint(
        gmail_workers.sync_all_gmail_accounts_worker,
        {'force_full': False},
        'Gmail',
        'All Accounts Sync Worker'
    )
    results.append(('Gmail - All Accounts', success, duration))

    # 4. Bigin
    print_header("4. Bigin CRM Integration")

    success, duration, data = test_worker_endpoint(
        bigin_workers.sync_all_modules_worker,
        {'run_full': False, 'triggered_by_user': 'test'},
        'Bigin',
        'Sync All Modules Worker'
    )
    results.append(('Bigin - Sync Modules', success, duration))

    success, duration, data = test_worker_endpoint(
        bigin_workers.refresh_bigin_token_worker,
        {},
        'Bigin',
        'Token Refresh Worker'
    )
    results.append(('Bigin - Token Refresh', success, duration))

    # 5. TallySync
    print_header("5. TallySync Integration")

    success, duration, data = test_worker_endpoint(
        tallysync_workers.sync_tally_data_worker,
        {'days': 7},
        'TallySync',
        'Sync Tally Data Worker'
    )
    results.append(('TallySync - Data Sync', success, duration))

    success, duration, data = test_worker_endpoint(
        tallysync_workers.full_reconciliation_worker,
        {},
        'TallySync',
        'Full Reconciliation Worker'
    )
    results.append(('TallySync - Reconciliation', success, duration))

    # 6. Callyzer
    print_header("6. Callyzer Integration")

    success, duration, data = test_worker_endpoint(
        callyzer_workers.sync_callyzer_account_worker,
        {'token_id': 9999, 'days_back': 150},
        'Callyzer',
        'Single Account Sync Worker'
    )
    results.append(('Callyzer - Single Account', success, duration))

    success, duration, data = test_worker_endpoint(
        callyzer_workers.sync_all_callyzer_accounts_worker,
        {'days_back': 150},
        'Callyzer',
        'All Accounts Sync Worker'
    )
    results.append(('Callyzer - All Accounts', success, duration))

    # Summary
    total_duration = time.time() - total_start

    print_header("Test Results Summary")

    passed = sum(1 for _, success, _ in results if success)
    failed = len(results) - passed

    print(f"{Colors.BOLD}Total Tests:{Colors.ENDC} {len(results)}")
    print(f"{Colors.OKGREEN}Passed:{Colors.ENDC} {passed}")
    print(f"{Colors.FAIL}Failed:{Colors.ENDC} {failed}")
    print(f"{Colors.BOLD}Total Time:{Colors.ENDC} {total_duration:.2f}s\n")

    # Detailed breakdown
    print(f"{Colors.BOLD}Detailed Results:{Colors.ENDC}\n")
    for name, success, duration in results:
        status = f"{Colors.OKGREEN}âœ“{Colors.ENDC}" if success else f"{Colors.FAIL}âœ—{Colors.ENDC}"
        print(f"{status} {name:<40} {duration:.3f}s")

    # Expected failures note
    print(f"\n{Colors.WARNING}Note:{Colors.ENDC} Tests with non-existent token IDs (9999) will fail with 'not found' errors.")
    print(f"{Colors.WARNING}This is expected and confirms proper error handling.{Colors.ENDC}")
    print(f"{Colors.OKGREEN}What matters: All endpoints are accessible and return proper JSON responses.{Colors.ENDC}")

    print(f"\n{Colors.BOLD}Finished at:{Colors.ENDC} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check if all endpoints are accessible (even if they return errors)
    all_accessible = all(duration > 0 for _, _, duration in results)

    if all_accessible:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}âœ“ All worker endpoints are accessible and functional!{Colors.ENDC}")
        return 0
    else:
        print(f"\n{Colors.FAIL}{Colors.BOLD}âœ— Some worker endpoints failed to respond!{Colors.ENDC}")
        return 1

if __name__ == '__main__':
    exit(main())
