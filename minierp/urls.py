from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect, render
from django.utils import timezone
# Marketing Analytics imports
from integrations import views_marketing_analytics, workers_marketing_analytics

# --- ADD THESE TWO IMPORTS ---
from django.conf import settings
from django.conf.urls.static import static

def test_error_page(request):
    """DEV ONLY: preview error.html with fake data — remove before production"""
    context = {
        'exception_type': 'ValueError',
        'exception_message': "Test error — this is a fake exception for UI preview",
        'traceback': (
            'Traceback (most recent call last):\n'
            '  File "/app/accounts/views.py", line 42, in dashboard\n'
            '    result = some_function(user)\n'
            '  File "/app/accounts/utils.py", line 18, in some_function\n'
            '    raise ValueError("Test error — this is a fake exception for UI preview")\n'
            'ValueError: Test error — this is a fake exception for UI preview\n'
        ),
        'request_path': request.get_full_path(),
        'request_method': request.method,
        'user': request.user if request.user.is_authenticated else None,
        'timestamp': timezone.now(),
        'error_id': 'ERR-TEST-0001',
        'revision': 'local-dev',
        'environment': 'development',
        'ip_address': '127.0.0.1',
        'user_agent': request.META.get('HTTP_USER_AGENT', '—'),
        'referer': '—',
    }
    return render(request, 'errors/error.html', context, status=500)


def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    return redirect('accounts:login')

urlpatterns = [
    path('', home_redirect, name='home'),
    path('saral-manage/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('projects/', include('projects.urls')),
    path('operations/', include('operations.urls')),
    path('activity/', include('activity_logs.urls', namespace='activity_logs')),
    path('supply/', include('supply.urls')),
    path('gmail/', include('gmail.urls', namespace='gmail')),
    path('integrations/bigin/', include('integrations.bigin.urls', namespace='bigin')),
    path('integrations/gmail-leads/', include('integrations.gmail_leads.urls', namespace='gmail_leads')),
    path('integrations/callyzer/', include('integrations.callyzer.urls', namespace='callyzer')),
    path('integrations/google-ads/', include('integrations.google_ads.urls', namespace='google_ads')),
    path('integrations/adobe-sign/', include('integrations.adobe_sign.urls', namespace='adobe_sign')),
    path('expense-log/', include('integrations.expense_log.urls', namespace='expense_log')),
    path('transport-sheet/', include('integrations.transport_sheet.urls', namespace='transport_sheet')),
    path('integrations/', include('integrations.urls', namespace='integrations')),  # Cross-integration features
    path('master-data/', include('dropdown_master_data.urls')),

    path('tallysync/', include('integrations.tallysync.urls')),

    # Marketing Analytics (cross-integration)
    path('marketing-analytics/',
         views_marketing_analytics.marketing_analytics_dashboard,
         name='marketing_analytics_dashboard'),
    path('marketing-analytics/export/',
         views_marketing_analytics.export_campaign_data,
         name='export_campaign_data'),
    path('marketing-analytics/workers/refresh-attributions/',
         workers_marketing_analytics.refresh_lead_attributions_worker,
         name='refresh_attributions_worker'),

]

# --- ADD THIS BLOCK AT THE END ---
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [path('test-error-page/', test_error_page)]