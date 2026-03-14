"""
Digital Marketing Dashboard View
Dedicated dashboard for digital_marketing role with Bigin, Gmail Leads, and Google Ads overview
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg
from datetime import datetime, timedelta
from django.utils import timezone

# Import models from integrations
from integrations.bigin.models import BiginContact
from integrations.gmail_leads.models import LeadEmail, GmailLeadsToken
from integrations.google_ads.models import Campaign, CampaignPerformance, GoogleAdsToken


@login_required
def digital_marketing_dashboard(request):
    """
    Digital Marketing Dashboard - Overview of all marketing integrations
    Access: digital_marketing, admin, director
    """
    # Permission check
    if request.user.role not in ['digital_marketing', 'admin', 'director']:
        return redirect('accounts:home')

    # Date range for stats (last 30 days)
    start_date = timezone.now().date() - timedelta(days=30)
    end_date = timezone.now().date()

    # === Bigin CRM Stats ===
    bigin_stats = {
        'total_contacts': BiginContact.objects.count(),
        'hot_leads': BiginContact.objects.filter(status='hot').count(),
        'warm_leads': BiginContact.objects.filter(status='warm').count(),
        'recent_contacts': BiginContact.objects.filter(
            created_time__gte=start_date
        ).count()
    }

    # === Gmail Leads Stats ===
    gmail_stats = {
        'total_leads': LeadEmail.objects.count(),
        'contact_us': LeadEmail.objects.filter(lead_type='CONTACT_US').count(),
        'saas_inventory': LeadEmail.objects.filter(lead_type='SAAS_INVENTORY').count(),
        'recent_leads': LeadEmail.objects.filter(
            date_received__gte=start_date
        ).count(),
        'active_accounts': GmailLeadsToken.objects.filter(is_active=True).count()
    }

    # === Google Ads Stats ===
    # Get performance data for last 30 days
    google_ads_performance = CampaignPerformance.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    ).aggregate(
        total_impressions=Sum('impressions'),
        total_clicks=Sum('clicks'),
        total_cost=Sum('cost'),
        total_conversions=Sum('conversions'),
        avg_ctr=Avg('ctr')
    )

    google_ads_stats = {
        'active_campaigns': Campaign.objects.filter(campaign_status='ENABLED').count(),
        'total_campaigns': Campaign.objects.count(),
        'impressions': google_ads_performance.get('total_impressions') or 0,
        'clicks': google_ads_performance.get('total_clicks') or 0,
        'cost': google_ads_performance.get('total_cost') or 0,
        'conversions': google_ads_performance.get('total_conversions') or 0,
        'ctr': google_ads_performance.get('avg_ctr') or 0,
        'active_accounts': GoogleAdsToken.objects.filter(is_active=True).count()
    }

    context = {
        'page_title': 'Digital Marketing Dashboard',
        'bigin_stats': bigin_stats,
        'gmail_stats': gmail_stats,
        'google_ads_stats': google_ads_stats,
        'start_date': start_date,
        'end_date': end_date,
    }

    return render(request, 'dashboards/digital_marketing_dashboard.html', context)
