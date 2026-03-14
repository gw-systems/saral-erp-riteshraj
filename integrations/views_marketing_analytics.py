"""
Marketing Analytics Dashboard
Enterprise-grade cross-integration analytics: Google Ads → Gmail Leads → Bigin CRM → Conversions

This module provides comprehensive funnel tracking with 7 key use cases:
1. Campaign Performance Overview
2. Funnel Analysis (drop-off tracking)
3. Cost Analysis & ROI
4. Lead Quality by Campaign
5. Device Performance
6. Multi-Touch Attribution (future)
7. Daily Trend Analysis
"""

import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg, F, Q, Case, When, FloatField, Value, DecimalField, IntegerField
from django.db.models.functions import TruncDate, Coalesce, Cast
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from datetime import datetime, timedelta
import json
import csv

from integrations.models import LeadAttribution
from integrations.google_ads.models import CampaignPerformance, DevicePerformance, Campaign
from integrations.gmail_leads.models import LeadEmail
from integrations.bigin.models import BiginContact

logger = logging.getLogger(__name__)


@login_required
def marketing_analytics_dashboard(request):
    """
    Marketing Analytics Dashboard - Complete funnel tracking
    Access: digital_marketing, admin, director, crm_executive
    """
    # RBAC
    if request.user.role not in ['digital_marketing', 'admin', 'director', 'crm_executive']:
        return redirect('accounts:home')

    # Date range filters (default: last 30 days)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)

    start_date_str = request.GET.get('start_date', start_date.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', end_date.strftime('%Y-%m-%d'))

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        logger.warning(f"Invalid date format: {start_date_str} or {end_date_str}")

    # Campaign filter
    selected_campaigns = request.GET.getlist('campaign')

    # Export handling
    export_format = request.GET.get('export')
    if export_format in ['csv', 'excel']:
        return export_campaign_data(request, start_date, end_date, selected_campaigns, export_format)

    # === USE CASE 1: Campaign Performance ===
    campaign_performance = get_campaign_performance(start_date, end_date, selected_campaigns)

    # === USE CASE 2: Funnel Analysis ===
    funnel_data = get_funnel_data(start_date, end_date)

    # === USE CASE 3: Cost Analysis ===
    cost_analysis = get_cost_analysis(start_date, end_date, selected_campaigns)

    # === USE CASE 4: Lead Quality ===
    lead_quality = get_lead_quality(start_date, end_date, selected_campaigns)

    # === USE CASE 5: Device Analysis ===
    device_analysis = get_device_analysis(start_date, end_date)

    # === USE CASE 7: Trend Analysis ===
    daily_trend = get_daily_trend(start_date, end_date)

    # Get filter options
    all_campaigns = LeadAttribution.objects.filter(
        utm_campaign__isnull=False
    ).exclude(
        utm_campaign=''
    ).values_list(
        'utm_campaign', flat=True
    ).distinct().order_by('utm_campaign')

    # Prepare Chart.js data for daily trend
    import json
    trend_dates = json.dumps([item['day'].strftime('%b %d') for item in daily_trend['raw_data']])
    trend_leads = json.dumps([item['lead_count'] for item in daily_trend['raw_data']])
    trend_contacts = json.dumps([item['contacts'] for item in daily_trend['raw_data']])
    trend_conversions = json.dumps([item['conversions'] for item in daily_trend['raw_data']])

    # Prepare Chart.js data for device performance
    device_labels = json.dumps([item.get('device', 'Unknown').title() for item in device_analysis])
    device_data = json.dumps([item.get('total_clicks', 0) for item in device_analysis])

    context = {
        'page_title': 'Marketing Analytics Dashboard',
        'start_date': start_date,
        'end_date': end_date,
        'selected_campaigns': selected_campaigns,
        'all_campaigns': all_campaigns,

        # Data for each use case
        'campaign_performance': campaign_performance[:20],  # Top 20
        'funnel_data': funnel_data,
        'cost_analysis': cost_analysis[:10],  # Top 10 by spend
        'lead_quality': lead_quality[:10],  # Top 10 by quality score
        'device_analysis': device_analysis,
        'daily_trend': {
            'dates': trend_dates,
            'leads': trend_leads,
            'contacts': trend_contacts,
            'conversions': trend_conversions,
        },

        # Chart.js data
        'device_analysis_labels': device_labels,
        'device_analysis_data': device_data,

        # Summary stats
        'summary_stats': calculate_summary_stats(start_date, end_date, selected_campaigns),
    }

    return render(request, 'marketing_analytics/dashboard.html', context)


def calculate_summary_stats(start_date, end_date, campaign_filter=None):
    """
    Calculate high-level KPIs for summary cards
    """
    # Google Ads total cost and clicks
    google_ads_stats = CampaignPerformance.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    )

    if campaign_filter:
        google_ads_stats = google_ads_stats.filter(
            campaign__campaign_name__in=campaign_filter
        )

    google_ads_summary = google_ads_stats.aggregate(
        total_cost=Coalesce(Sum('cost'), Value(0.0), output_field=FloatField()),
        total_clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
        total_conversions=Coalesce(Sum('conversions'), Value(0), output_field=IntegerField())
    )

    # Gmail Leads
    gmail_leads_count = LeadEmail.objects.filter(
        date_received__gte=start_date,
        date_received__lte=end_date
    )

    if campaign_filter:
        gmail_leads_count = gmail_leads_count.filter(
            utm_campaign__in=campaign_filter
        )

    gmail_leads_count = gmail_leads_count.count()

    # Attributed contacts (via LeadAttribution)
    attributed_contacts = LeadAttribution.objects.filter(
        gmail_received_at__date__gte=start_date,
        gmail_received_at__date__lte=end_date
    )

    if campaign_filter:
        attributed_contacts = attributed_contacts.filter(
            utm_campaign__in=campaign_filter
        )

    contacts_count = attributed_contacts.values('bigin_contact_id').distinct().count()

    # Conversions (contacts with "converted" status)
    conversions_count = attributed_contacts.filter(
        bigin_contact__status__icontains='converted'
    ).values('bigin_contact_id').distinct().count()

    # Calculate metrics
    total_cost = google_ads_summary['total_cost']
    cpl = total_cost / gmail_leads_count if gmail_leads_count > 0 else 0
    cost_per_contact = total_cost / contacts_count if contacts_count > 0 else 0
    cost_per_conversion = total_cost / conversions_count if conversions_count > 0 else 0
    lead_to_contact_rate = (contacts_count / gmail_leads_count * 100) if gmail_leads_count > 0 else 0
    conversion_rate = (conversions_count / contacts_count * 100) if contacts_count > 0 else 0

    return {
        'total_cost': total_cost,
        'total_clicks': google_ads_summary['total_clicks'],
        'total_leads': gmail_leads_count,
        'total_contacts': contacts_count,
        'total_conversions': conversions_count,
        'cpl': cpl,
        'cost_per_contact': cost_per_contact,
        'cost_per_conversion': cost_per_conversion,
        'lead_to_contact_rate': lead_to_contact_rate,
        'conversion_rate': conversion_rate,
    }


def get_campaign_performance(start_date, end_date, campaign_filter=None):
    """
    Use Case 1: Campaign Performance Overview

    Metrics: Leads, Contacts, Conversions, Conversion rates by campaign
    """
    qs = LeadAttribution.objects.filter(
        gmail_received_at__date__gte=start_date,
        gmail_received_at__date__lte=end_date
    )

    if campaign_filter:
        qs = qs.filter(utm_campaign__in=campaign_filter)

    # Aggregate by campaign
    campaign_stats = qs.values('utm_campaign').annotate(
        total_leads=Count('gmail_lead_id', distinct=True),
        total_contacts=Count('bigin_contact_id', distinct=True),

        # Count converted contacts
        converted_contacts=Count(
            'bigin_contact_id',
            filter=Q(bigin_contact__status__icontains='converted'),
            distinct=True
        ),

        # Count hot/warm leads
        hot_leads=Count(
            'bigin_contact_id',
            filter=Q(bigin_contact__status__icontains='hot'),
            distinct=True
        ),
        warm_leads=Count(
            'bigin_contact_id',
            filter=Q(bigin_contact__status__icontains='warm'),
            distinct=True
        ),

        # Average time to contact
        avg_time_to_contact=Avg('time_to_contact_hours'),
    ).annotate(
        # Calculate conversion rates
        lead_to_contact_rate=Case(
            When(total_leads__gt=0, then=F('total_contacts') * 100.0 / F('total_leads')),
            default=Value(0.0),
            output_field=FloatField()
        ),
        contact_to_conversion_rate=Case(
            When(total_contacts__gt=0, then=F('converted_contacts') * 100.0 / F('total_contacts')),
            default=Value(0.0),
            output_field=FloatField()
        ),
    ).order_by('-total_leads')

    # Enhance with Google Ads cost data
    for campaign in campaign_stats:
        campaign_name = campaign['utm_campaign']

        # Get Google Ads performance for this campaign
        google_ads_perf = CampaignPerformance.objects.filter(
            campaign__campaign_name=campaign_name,
            date__gte=start_date,
            date__lte=end_date
        ).aggregate(
            total_cost=Coalesce(Sum('cost'), Value(0.0), output_field=FloatField()),
            total_clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
            total_impressions=Coalesce(Sum('impressions'), Value(0), output_field=IntegerField()),
            avg_cpc=Coalesce(Avg('avg_cpc'), Value(0.0), output_field=FloatField()),
        )

        campaign['cost'] = google_ads_perf['total_cost']
        campaign['clicks'] = google_ads_perf['total_clicks']
        campaign['impressions'] = google_ads_perf['total_impressions']
        campaign['avg_cpc'] = google_ads_perf['avg_cpc'] or 0

        # Calculate cost metrics
        campaign['cpl'] = campaign['cost'] / campaign['total_leads'] if campaign['total_leads'] > 0 else 0
        campaign['cost_per_contact'] = campaign['cost'] / campaign['total_contacts'] if campaign['total_contacts'] > 0 else 0
        campaign['cost_per_conversion'] = campaign['cost'] / campaign['converted_contacts'] if campaign['converted_contacts'] > 0 else 0

        # ROI (assuming placeholder conversion value)
        # TODO: Pull actual conversion value from deals
        campaign['roi'] = 0  # Placeholder

    return list(campaign_stats)


def get_funnel_data(start_date, end_date):
    """
    Use Case 2: Funnel Analysis

    Stages: Ad Clicks → Gmail Leads → CRM Contacts → Qualified → Deals Won
    """
    # Stage 1: Ad Clicks
    ad_clicks = CampaignPerformance.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    ).aggregate(total_clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()))['total_clicks']

    # Stage 2: Gmail Leads
    gmail_leads_count = LeadEmail.objects.filter(
        date_received__gte=start_date,
        date_received__lte=end_date,
        utm_campaign__isnull=False
    ).exclude(utm_campaign='').count()

    # Stage 3: Bigin Contacts (matched via attribution)
    attributions = LeadAttribution.objects.filter(
        gmail_received_at__date__gte=start_date,
        gmail_received_at__date__lte=end_date
    )

    bigin_contacts_count = attributions.values('bigin_contact_id').distinct().count()

    # Stage 4: Qualified Leads (Hot/Warm)
    qualified_count = attributions.filter(
        Q(bigin_contact__status__icontains='hot') | Q(bigin_contact__status__icontains='warm')
    ).values('bigin_contact_id').distinct().count()

    # Stage 5: Deals Won (Converted)
    deals_won_count = attributions.filter(
        bigin_contact__status__icontains='converted'
    ).values('bigin_contact_id').distinct().count()

    # Calculate conversion rates between stages
    funnel_stages = [
        {'name': 'Ad Clicks', 'count': ad_clicks, 'percentage': 100.0},
        {
            'name': 'Gmail Leads',
            'count': gmail_leads_count,
            'percentage': (gmail_leads_count / ad_clicks * 100) if ad_clicks > 0 else 0,
            'conversion_from_previous': (gmail_leads_count / ad_clicks * 100) if ad_clicks > 0 else 0
        },
        {
            'name': 'CRM Contacts',
            'count': bigin_contacts_count,
            'percentage': (bigin_contacts_count / ad_clicks * 100) if ad_clicks > 0 else 0,
            'conversion_from_previous': (bigin_contacts_count / gmail_leads_count * 100) if gmail_leads_count > 0 else 0
        },
        {
            'name': 'Qualified (Hot/Warm)',
            'count': qualified_count,
            'percentage': (qualified_count / ad_clicks * 100) if ad_clicks > 0 else 0,
            'conversion_from_previous': (qualified_count / bigin_contacts_count * 100) if bigin_contacts_count > 0 else 0
        },
        {
            'name': 'Deals Won',
            'count': deals_won_count,
            'percentage': (deals_won_count / ad_clicks * 100) if ad_clicks > 0 else 0,
            'conversion_from_previous': (deals_won_count / qualified_count * 100) if qualified_count > 0 else 0
        },
    ]

    return {
        'stages': funnel_stages,
        'overall_conversion': (deals_won_count / ad_clicks * 100) if ad_clicks > 0 else 0
    }


def get_cost_analysis(start_date, end_date, campaign_filter=None):
    """
    Use Case 3: Cost Analysis & ROI by Campaign
    """
    # Get campaign performance (already has cost data)
    return get_campaign_performance(start_date, end_date, campaign_filter)


def get_lead_quality(start_date, end_date, campaign_filter=None):
    """
    Use Case 4: Lead Quality by Campaign

    Metrics: Hot/Warm/Cold distribution, Conversion rate, Quality score
    """
    qs = LeadAttribution.objects.filter(
        gmail_received_at__date__gte=start_date,
        gmail_received_at__date__lte=end_date
    )

    if campaign_filter:
        qs = qs.filter(utm_campaign__in=campaign_filter)

    quality_stats = qs.values('utm_campaign').annotate(
        total_leads=Count('id'),

        # Temperature distribution
        hot_count=Count('id', filter=Q(bigin_contact__status__icontains='hot')),
        warm_count=Count('id', filter=Q(bigin_contact__status__icontains='warm')),
        cold_count=Count('id', filter=Q(bigin_contact__status__icontains='cold')),
        converted_count=Count('id', filter=Q(bigin_contact__status__icontains='converted')),

        # Average time to contact
        avg_time_to_contact=Avg('time_to_contact_hours'),
    ).annotate(
        # Conversion rate
        conversion_rate=Case(
            When(total_leads__gt=0, then=F('converted_count') * 100.0 / F('total_leads')),
            default=Value(0.0),
            output_field=FloatField()
        ),

        # Quality score (weighted: hot=3, warm=2, converted=5)
        quality_score=Case(
            When(total_leads__gt=0, then=(
                F('hot_count') * 3 + F('warm_count') * 2 + F('converted_count') * 5
            ) * 100.0 / F('total_leads')),
            default=Value(0.0),
            output_field=FloatField()
        ),

        # Percentages
        hot_percentage=Case(
            When(total_leads__gt=0, then=F('hot_count') * 100.0 / F('total_leads')),
            default=Value(0.0),
            output_field=FloatField()
        ),
        warm_percentage=Case(
            When(total_leads__gt=0, then=F('warm_count') * 100.0 / F('total_leads')),
            default=Value(0.0),
            output_field=FloatField()
        ),
        cold_percentage=Case(
            When(total_leads__gt=0, then=F('cold_count') * 100.0 / F('total_leads')),
            default=Value(0.0),
            output_field=FloatField()
        ),
    ).order_by('-quality_score')

    return list(quality_stats)


def get_device_analysis(start_date, end_date):
    """
    Use Case 5: Device Performance Analysis

    Metrics: Clicks, Cost, Leads, Conversions by device
    """
    device_stats = DevicePerformance.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    ).values('device').annotate(
        total_clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
        total_cost=Coalesce(Sum('cost'), Value(0.0), output_field=FloatField()),
        total_impressions=Coalesce(Sum('impressions'), Value(0), output_field=IntegerField()),
        avg_cpc=Coalesce(Avg('avg_cpc'), Value(0.0), output_field=FloatField()),
        total_conversions=Coalesce(Sum('conversions'), Value(0), output_field=IntegerField()),
    ).order_by('-total_clicks')

    # Note: Gmail Leads don't track device type
    # Future enhancement: Add device tracking to LeadEmail model

    return list(device_stats)


def get_daily_trend(start_date, end_date):
    """
    Use Case 7: Daily Trend Analysis

    Metrics: Daily lead volume, conversions, trends over time
    """
    # Daily lead counts
    daily_leads = LeadEmail.objects.filter(
        date_received__gte=start_date,
        date_received__lte=end_date
    ).annotate(
        day=TruncDate('date_received')
    ).values('day').annotate(
        lead_count=Count('id')
    ).order_by('day')

    # Daily conversion counts (from attributions)
    daily_conversions = LeadAttribution.objects.filter(
        gmail_received_at__date__gte=start_date,
        gmail_received_at__date__lte=end_date,
        bigin_contact__status__icontains='converted'
    ).annotate(
        day=TruncDate('gmail_received_at')
    ).values('day').annotate(
        conversion_count=Count('bigin_contact_id', distinct=True)
    ).order_by('day')

    # Daily contact creation counts
    daily_contacts = LeadAttribution.objects.filter(
        gmail_received_at__date__gte=start_date,
        gmail_received_at__date__lte=end_date
    ).annotate(
        day=TruncDate('gmail_received_at')
    ).values('day').annotate(
        contact_count=Count('bigin_contact_id', distinct=True)
    ).order_by('day')

    # Merge data by date
    conversions_dict = {item['day']: item['conversion_count'] for item in daily_conversions}
    contacts_dict = {item['day']: item['contact_count'] for item in daily_contacts}

    for day_data in daily_leads:
        day = day_data['day']
        day_data['conversions'] = conversions_dict.get(day, 0)
        day_data['contacts'] = contacts_dict.get(day, 0)

    # Format for Chart.js
    labels = [d['day'].strftime('%b %d') for d in daily_leads]
    lead_counts = [d['lead_count'] for d in daily_leads]
    contact_counts = [d['contacts'] for d in daily_leads]
    conversion_counts = [d['conversions'] for d in daily_leads]

    return {
        'labels': json.dumps(labels),
        'lead_counts': json.dumps(lead_counts),
        'contact_counts': json.dumps(contact_counts),
        'conversion_counts': json.dumps(conversion_counts),
        'raw_data': list(daily_leads),
    }


@login_required
def export_campaign_data(request):
    """
    Export campaign performance data to CSV
    Access: digital_marketing, admin, director, crm_executive
    """
    # RBAC
    if request.user.role not in ['digital_marketing', 'admin', 'director', 'crm_executive']:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    # Get date range from query params
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)

    start_date_str = request.GET.get('start_date', start_date.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', end_date.strftime('%Y-%m-%d'))

    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format'}, status=400)

    # Campaign filter
    selected_campaigns = request.GET.getlist('campaign')

    # Get campaign data
    campaign_data = get_campaign_performance(start_date, end_date, selected_campaigns)

    # Create CSV response
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="marketing_analytics_{start_date}_{end_date}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Campaign', 'Clicks', 'Cost (INR)', 'Leads', 'Contacts', 'Hot Leads',
        'CPL (INR)', 'Conversion %', 'ROI %'
    ])

    for campaign in campaign_data:
        writer.writerow([
            campaign.get('campaign', '(No Campaign)'),
            campaign.get('clicks', 0),
            f"{campaign.get('cost', 0):.2f}",
            campaign.get('leads', 0),
            campaign.get('contacts', 0),
            campaign.get('hot_leads', 0),
            f"{campaign.get('cost_per_lead', 0):.2f}",
            f"{campaign.get('conversion_rate', 0):.1f}",
            f"{campaign.get('roi', 0):.1f}",
        ])

    return response
