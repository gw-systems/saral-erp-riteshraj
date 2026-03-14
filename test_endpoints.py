"""
Endpoint tester — checks all GET-based URL patterns return non-500 responses.
Run: python test_endpoints.py
Skips: worker endpoints, API/AJAX, OAuth, POST-only actions.
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'minierp.settings')
django.setup()

# Allow testserver host used by Django test client
from django.conf import settings
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS = list(settings.ALLOWED_HOSTS) + ['testserver', 'localhost', '127.0.0.1']

from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()

# ── Auth ──────────────────────────────────────────────────────────────────────
client = Client()
su = User.objects.filter(is_superuser=True).first()
if su:
    client.force_login(su)
    print(f"Logged in as: {su.username} (superuser)")
else:
    u = User.objects.first()
    if u:
        client.force_login(u)
        print(f"Logged in as: {u.username}")
    else:
        print("WARNING: No users found — testing unauthenticated")

# ── Pages to test (GET, no path params, no side effects) ────────────────────
PAGES = [
    # Root
    '/',

    # ── Accounts / Dashboards ──────────────────────────────────────────────
    '/accounts/login/',
    '/accounts/dashboard/',
    '/accounts/backoffice-dashboard/',
    '/accounts/dashboard/admin/home/',
    '/accounts/dashboard/admin/finance/',
    '/accounts/dashboard/admin/integrations/',
    '/accounts/dashboard/admin/operations/',
    '/accounts/dashboard/admin/projects/',
    '/accounts/dashboard/admin/supply/',
    '/accounts/dashboard/admin/system/',
    '/accounts/dashboard/admin/team/',
    '/accounts/dashboard/admin/file-manager/',
    '/accounts/dashboard/director/',
    '/accounts/dashboard/director/analytics/',
    '/accounts/dashboard/super-user/',
    '/accounts/crm-executive-dashboard/',
    '/accounts/digital-marketing-dashboard/',
    '/accounts/sales-manager-dashboard/',
    '/accounts/operation-controller-dashboard/',
    '/accounts/operation-coordinator-dashboard/',
    '/accounts/operation-manager-dashboard/',
    '/accounts/finance-manager/',
    '/accounts/warehouse-manager-dashboard/',
    '/accounts/supply-manager-dashboard/',
    '/accounts/operation-controller/daily/missing-entries/',
    '/accounts/operation-controller/daily/inventory-turnover/',
    '/accounts/operation-controller/daily/space-inventory/',
    '/accounts/operation-controller/daily/variance-alerts/',
    '/accounts/operation-controller/monthly/max-inventory/',
    '/accounts/operation-controller-team/',
    '/accounts/profile/',
    '/accounts/users/',
    '/accounts/users/create/',
    '/accounts/notifications/',
    '/accounts/impersonation-logs/',
    '/accounts/password-history/',
    '/accounts/change-password/',
    '/accounts/errors/',

    # ── Projects ───────────────────────────────────────────────────────────
    '/projects/list/active/',
    '/projects/list/all/',
    '/projects/list/inactive/',
    '/projects/list/pending/',
    '/projects/my-projects/',
    '/projects/create/',
    '/projects/admin/project-codes/',
    '/projects/admin/change-logs/',
    '/projects/admin/temp-cleanup/',
    '/projects/project-mapping/',
    '/projects/project-cards/',
    '/projects/project-cards/create/',
    '/projects/project-cards/incomplete/',
    '/projects/escalations/',
    '/projects/renewals/',
    '/projects/quotations/',
    '/projects/quotations/create/',
    '/projects/quotations/settings/',
    '/projects/gst-states/',
    '/projects/gst-states/create/',
    '/projects/clients/',
    '/projects/clients/create/',
    '/projects/rate-cards/',

    # ── Operations ─────────────────────────────────────────────────────────
    '/projects/project-cards/',
    '/projects/project-cards/incomplete/',
    '/operations/mis/',
    '/operations/mis/all-history/',
    '/operations/monthly-billing/',
    '/operations/adhoc-billing/',
    '/operations/adhoc-billing/create/',
    '/operations/disputes/',
    '/operations/disputes/create/',
    '/operations/disputes/analysis/',
    '/operations/calendar/',
    '/operations/daily-entry/',
    '/operations/daily-entry/bulk/',
    '/operations/daily-entry/all-history/',
    '/operations/pending-entries/',
    '/operations/coordinator-performance/',
    '/operations/holidays/',
    '/operations/holidays/create/',
    '/operations/lr/',
    '/operations/lr/create/',

    # ── Supply ─────────────────────────────────────────────────────────────
    '/supply/vendors/',
    '/supply/vendors/create/',
    '/supply/warehouses/',
    '/supply/warehouses/create/',
    '/supply/rfqs/',
    '/supply/rfqs/create/',
    '/supply/analytics/',
    '/supply/locations/',
    '/supply/locations/create/',
    '/supply/warehouse-availability/',
    '/supply/map/',

    # ── Adobe Sign ─────────────────────────────────────────────────────────
    '/integrations/adobe-sign/',
    '/integrations/adobe-sign/agreements/add/',
    '/integrations/adobe-sign/agreements/pending/',
    '/integrations/adobe-sign/templates/',
    '/integrations/adobe-sign/templates/create/',
    '/integrations/adobe-sign/settings/',

    # ── Bigin ──────────────────────────────────────────────────────────────
    '/integrations/bigin/dashboard/',
    '/integrations/bigin/leads/',
    '/integrations/bigin/contacts/create/',
    '/integrations/bigin/sync-audit/',

    # ── Callyzer ───────────────────────────────────────────────────────────
    '/integrations/callyzer/',
    '/integrations/callyzer/analytics/',
    '/integrations/callyzer/reports/',
    '/integrations/callyzer/logs/',

    # ── Google Ads ─────────────────────────────────────────────────────────
    '/integrations/google-ads/',
    '/integrations/google-ads/detailed-report/',
    '/integrations/google-ads/search-terms/',
    '/integrations/google-ads/logs/',

    # ── Gmail Leads ────────────────────────────────────────────────────────
    '/integrations/gmail-leads/',
    '/integrations/gmail-leads/logs/',

    # ── Gmail ──────────────────────────────────────────────────────────────
    '/gmail/',
    '/gmail/sync-logs/',

    # ── Expense Log ────────────────────────────────────────────────────────
    '/expense-log/dashboard/',
    '/expense-log/transport-projectwise/',
    '/expense-log/user-mappings/',

    # ── Tallysync ──────────────────────────────────────────────────────────
    '/tallysync/reconciliation/',
    '/tallysync/reconciliation/detail/',
    '/tallysync/cash-liquidity/',
    '/tallysync/gst-compliance/',
    '/tallysync/operations/',
    '/tallysync/project-profitability/',
    '/tallysync/sales-financial-detail/',

    # ── Marketing Analytics ────────────────────────────────────────────────
    '/marketing-analytics/',

    # ── Master Data ────────────────────────────────────────────────────────
    '/master-data/',

    # ── Integrations hub ───────────────────────────────────────────────────
    '/integrations/scheduled-jobs/',
    '/integrations/monitoring/',
]

# ── Run ───────────────────────────────────────────────────────────────────────
results = {'ok': [], 'redirect': [], 'error': [], 'not_found': []}
SKIP_PREFIXES = ('/accounts/api/', '/tallysync/api/', '/integrations/bigin/api/',
                 '/gmail/api/', '/gmail/ajax/', '/supply/ajax/')

print(f"\nTesting {len(PAGES)} endpoints as {su.username if su else 'anon'}...\n{'─'*65}")

for path in PAGES:
    if any(path.startswith(p) for p in SKIP_PREFIXES):
        continue
    try:
        resp = client.get(path, follow=False)
        code = resp.status_code
        if code in (200, 201):
            results['ok'].append((path, code))
            print(f"  ✓  {code}  {path}")
        elif code in (301, 302, 303, 307, 308):
            loc = resp.get('Location', '?')
            results['redirect'].append((path, code))
            print(f"  →  {code}  {path}  →  {loc}")
        elif code == 404:
            results['not_found'].append((path, code))
            print(f"  ✗  404  {path}")
        elif code >= 500:
            results['error'].append((path, code))
            print(f"  !!  {code}  {path}  ← SERVER ERROR")
        else:
            results['redirect'].append((path, code))
            print(f"  →  {code}  {path}")
    except Exception as e:
        results['error'].append((path, str(e)))
        print(f"  !!  ERR  {path}  — {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
total = len(results['ok']) + len(results['redirect']) + len(results['not_found']) + len(results['error'])
print(f"\n{'═'*65}")
print(f"  Tested:      {total}")
print(f"  ✓ 200 OK:    {len(results['ok'])}")
print(f"  → Redirect:  {len(results['redirect'])}")
print(f"  ✗ 404:       {len(results['not_found'])}")
print(f"  !! 5xx/Err:  {len(results['error'])}")

if results['error']:
    print("\n🔴 SERVER ERRORS — fix these:")
    for path, code in results['error']:
        print(f"  {code}  {path}")

if results['not_found']:
    print("\n🟡 404s — URL may have changed:")
    for path, code in results['not_found']:
        print(f"  {path}")

sys.exit(0 if not results['error'] else 1)
