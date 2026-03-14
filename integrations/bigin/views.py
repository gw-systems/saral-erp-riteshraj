from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count, Avg
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.contrib import messages
import requests
import logging
from datetime import timedelta, datetime
from django.conf import settings

logger = logging.getLogger(__name__)
from integrations.bigin.models import BiginAuthToken, BiginContact
from integrations.bigin.bigin_sync import fetch_contact_notes


@login_required
def oauth_start(request):
    """
    Initiates Zoho Bigin OAuth2 flow
    """
    import secrets
    from integrations.bigin.utils.settings_helper import get_bigin_config
    bigin_config = get_bigin_config()

    # Generate and store CSRF state token
    state = secrets.token_urlsafe(32)
    request.session['bigin_oauth_state'] = state

    # Build authorization URL
    auth_url = (
        f"{bigin_config['auth_url']}?"
        f"scope={bigin_config['scope']}&"
        f"client_id={bigin_config['client_id']}&"
        f"response_type=code&"
        f"redirect_uri={bigin_config['redirect_uri']}&"
        f"access_type=offline&"
        f"prompt=consent&"
        f"state={state}"
    )

    return redirect(auth_url)


@login_required
def oauth_callback(request):
    """
    Handles Zoho OAuth2 redirect with ?code=...
    Exchanges code for tokens and stores them in DB.
    """
    # Validate OAuth state parameter (CSRF protection)
    expected_state = request.session.pop('bigin_oauth_state', None)
    if not expected_state or expected_state != request.GET.get('state'):
        return HttpResponse("Invalid OAuth state. Please restart the authorization flow.", status=400)

    code = request.GET.get("code")
    error = request.GET.get("error")

    if error:
        return HttpResponse(f"Authorization failed: {error}", status=400)

    if not code:
        return HttpResponse("Missing authorization code.", status=400)

    from integrations.bigin.utils.settings_helper import get_bigin_config
    bigin_config = get_bigin_config()

    data = {
        "code": code,
        "client_id": bigin_config['client_id'],
        "client_secret": bigin_config['client_secret'],
        "redirect_uri": bigin_config['redirect_uri'],
        "grant_type": "authorization_code",
    }

    response = requests.post(bigin_config['token_url'], data=data)

    if response.status_code != 200:
        logger.error(f"Bigin token exchange failed: {response.status_code} {response.text}")
        return HttpResponse("Token exchange failed. Check server logs for details.", status=response.status_code)

    token_data = response.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not access_token or not refresh_token:
        logger.error(f"Bigin token exchange returned no tokens: {token_data}")
        return HttpResponse("Token exchange failed — no tokens returned. Check server logs.", status=500)

    expires_in = token_data.get("expires_in", 3600)

    BiginAuthToken.objects.all().delete()
    token = BiginAuthToken(expires_at=timezone.now() + timedelta(seconds=expires_in))
    token.set_tokens(access_token=access_token, refresh_token=refresh_token)
    token.save()

    return JsonResponse({
        'status': 'success',
        'message': 'Bigin authentication successful. Tokens saved securely.',
        'expires_at': token.expires_at.isoformat()
    })


@login_required
def bigin_leads(request):
    """
    Detailed lead table view with RBAC and searchable multi-select filters.
    - Sales Manager: Only their assigned leads
    - CRM Executive: All leads
    """
    # AUTO-POPULATE LeadAttribution table on first access (production-grade, zero manual intervention)
    from integrations.models import LeadAttribution
    from datetime import timedelta

    try:
        matched_count = LeadAttribution.objects.refresh_attributions()
        if matched_count > 0:
            logger.info(f"✅ LeadAttribution: {matched_count} new matches created")
    except Exception as e:
        logger.error(f"❌ LeadAttribution refresh failed: {e}", exc_info=True)

    # Base queryset
    contacts = BiginContact.objects.filter(module='Contacts').order_by('-created_time')
    
    # RBAC: Filter by owner for Sales Managers
    if request.user.role == 'sales_manager':
        user_full_name = request.user.get_full_name()
        contacts = contacts.filter(owner__iexact=user_full_name)
    
    # Get filter parameters
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    # Helper function to parse filters - handles both comma-separated and multi-select formats
    def parse_filter_list(param_name):
        # First try getlist (for multi-select dropdowns: ?param=val1&param=val2)
        values = request.GET.getlist(param_name)
        if values:
            # If any value contains comma, split it
            result = []
            for val in values:
                if ',' in val:
                    result.extend([v.strip() for v in val.split(',') if v.strip()])
                else:
                    result.append(val)
            return result
        # Also try single param with comma-separated values: ?param=val1,val2
        single_val = request.GET.get(param_name, '')
        if single_val:
            return [v.strip() for v in single_val.split(',') if v.strip()]
        return []

    # Multi-select filters - handles both formats
    owner_list = parse_filter_list('owner')
    contact_type_list = parse_filter_list('contact_type')
    status_list = parse_filter_list('status')
    lead_stage_list = parse_filter_list('lead_stage')
    industry_type_list = parse_filter_list('industry_type')
    location_list = parse_filter_list('location')
    lead_source_list = parse_filter_list('lead_source')
    reason_list = parse_filter_list('reason')

    # UTM filters (new)
    utm_campaign_list = parse_filter_list('utm_campaign')
    utm_medium_list = parse_filter_list('utm_medium')
    utm_term_list = parse_filter_list('utm_term')
    utm_content_list = parse_filter_list('utm_content')

    # Area range filter
    area_range = request.GET.get('area_range', '')
    
    # Apply date filters
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            contacts = contacts.filter(created_time__gte=start_dt)
        except ValueError:
            pass
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            contacts = contacts.filter(created_time__lte=end_dt)
        except ValueError:
            pass

    # Universal search filter
    search_query = request.GET.get('search', '').strip()
    if search_query:
        search_q = Q(full_name__icontains=search_query) | \
                   Q(account_name__icontains=search_query) | \
                   Q(email__icontains=search_query) | \
                   Q(mobile__icontains=search_query) | \
                   Q(location__icontains=search_query) | \
                   Q(industry_type__icontains=search_query) | \
                   Q(contact_type__icontains=search_query) | \
                   Q(lead_source__icontains=search_query) | \
                   Q(status__icontains=search_query) | \
                   Q(description__icontains=search_query) | \
                   Q(notes__icontains=search_query)
        contacts = contacts.filter(search_q)

    # Apply owner filter (multi-select) - NEW
    if owner_list:
        if 'blank' in owner_list:
            owner_query = Q(owner__isnull=True) | Q(owner='')
            for owner in owner_list:
                if owner != 'blank':
                    owner_query |= Q(owner__iexact=owner)
            contacts = contacts.filter(owner_query)
        else:
            owner_query = Q()
            for owner in owner_list:
                owner_query |= Q(owner__iexact=owner)
            contacts = contacts.filter(owner_query)

    # Apply contact_type filter (multi-select)
    if contact_type_list:
        if 'blank' in contact_type_list:
            type_query = Q(contact_type__isnull=True) | Q(contact_type='')
            for ct in contact_type_list:
                if ct != 'blank':
                    type_query |= Q(contact_type__iexact=ct)
            contacts = contacts.filter(type_query)
        else:
            type_query = Q()
            for ct in contact_type_list:
                type_query |= Q(contact_type__iexact=ct)
            contacts = contacts.filter(type_query)
    
    # Apply status filter (multi-select, comma-separated in DB)
    if status_list:
        if 'blank' in status_list:
            status_query = Q(status__isnull=True) | Q(status='')
            for status in status_list:
                if status != 'blank':
                    status_query |= Q(status__icontains=status)
            contacts = contacts.filter(status_query)
        else:
            status_query = Q()
            for status in status_list:
                status_query |= Q(status__icontains=status)
            contacts = contacts.filter(status_query)
    
    # Apply lead_stage filter (multi-select)
    if lead_stage_list:
        if 'blank' in lead_stage_list:
            stage_query = Q(lead_stage__isnull=True) | Q(lead_stage='')
            for stage in lead_stage_list:
                if stage != 'blank':
                    stage_query |= Q(lead_stage__iexact=stage)
            contacts = contacts.filter(stage_query)
        else:
            stage_query = Q()
            for stage in lead_stage_list:
                stage_query |= Q(lead_stage__iexact=stage)
            contacts = contacts.filter(stage_query)
    
    # Apply industry_type filter (multi-select)
    if industry_type_list:
        if 'blank' in industry_type_list:
            industry_query = Q(industry_type__isnull=True) | Q(industry_type='')
            for industry in industry_type_list:
                if industry != 'blank':
                    industry_query |= Q(industry_type__iexact=industry)
            contacts = contacts.filter(industry_query)
        else:
            industry_query = Q()
            for industry in industry_type_list:
                industry_query |= Q(industry_type__iexact=industry)
            contacts = contacts.filter(industry_query)
    
    # Apply location filter (NEW - multi-select, substring match)
    if location_list:
        if 'blank' in location_list:
            location_query = Q(locations__isnull=True) | Q(locations='')
            for loc in location_list:
                if loc != 'blank':
                    location_query |= Q(locations__icontains=loc)
            contacts = contacts.filter(location_query)
        else:
            location_query = Q()
            for loc in location_list:
                location_query |= Q(locations__icontains=loc)
            contacts = contacts.filter(location_query)
    
    # Apply lead_source filter (multi-select)
    if lead_source_list:
        if 'blank' in lead_source_list:
            source_query = Q(lead_source__isnull=True) | Q(lead_source='')
            for source in lead_source_list:
                if source != 'blank':
                    source_query |= Q(lead_source__iexact=source)
            contacts = contacts.filter(source_query)
        else:
            source_query = Q()
            for source in lead_source_list:
                source_query |= Q(lead_source__iexact=source)
            contacts = contacts.filter(source_query)

    # Apply reason filter (multi-select)
    if reason_list:
        if 'blank' in reason_list:
            reason_query = Q(reason__isnull=True) | Q(reason='')
            for r in reason_list:
                if r != 'blank':
                    reason_query |= Q(reason__iexact=r)
            contacts = contacts.filter(reason_query)
        else:
            reason_query = Q()
            for r in reason_list:
                reason_query |= Q(reason__iexact=r)
            contacts = contacts.filter(reason_query)

    # Apply UTM filters (via LeadAttribution JOIN)
    from integrations.models import LeadAttribution

    if utm_campaign_list:
        # Get bigin_contact IDs that match UTM campaign filter
        if 'blank' in utm_campaign_list:
            # Include contacts with no attribution OR empty campaign
            attribution_ids = LeadAttribution.objects.filter(
                Q(utm_campaign__isnull=True) | Q(utm_campaign='')
            ).values_list('bigin_contact_id', flat=True)
            contacts_with_blank = contacts.exclude(
                id__in=LeadAttribution.objects.values_list('bigin_contact_id', flat=True)
            )

            # Add contacts with specific campaigns
            campaign_query = Q()
            for campaign in utm_campaign_list:
                if campaign != 'blank':
                    campaign_query |= Q(utm_campaign__iexact=campaign)
            if campaign_query:
                attribution_ids_with_value = LeadAttribution.objects.filter(campaign_query).values_list('bigin_contact_id', flat=True)
                contacts = contacts.filter(Q(id__in=attribution_ids) | Q(id__in=attribution_ids_with_value)) | contacts_with_blank
            else:
                contacts = contacts.filter(Q(id__in=attribution_ids)) | contacts_with_blank
        else:
            campaign_query = Q()
            for campaign in utm_campaign_list:
                campaign_query |= Q(utm_campaign__iexact=campaign)
            attribution_ids = LeadAttribution.objects.filter(campaign_query).values_list('bigin_contact_id', flat=True)
            contacts = contacts.filter(id__in=attribution_ids)

    if utm_medium_list:
        if 'blank' in utm_medium_list:
            attribution_ids = LeadAttribution.objects.filter(
                Q(utm_medium__isnull=True) | Q(utm_medium='')
            ).values_list('bigin_contact_id', flat=True)
            contacts_with_blank = contacts.exclude(
                id__in=LeadAttribution.objects.values_list('bigin_contact_id', flat=True)
            )

            medium_query = Q()
            for medium in utm_medium_list:
                if medium != 'blank':
                    medium_query |= Q(utm_medium__iexact=medium)
            if medium_query:
                attribution_ids_with_value = LeadAttribution.objects.filter(medium_query).values_list('bigin_contact_id', flat=True)
                contacts = contacts.filter(Q(id__in=attribution_ids) | Q(id__in=attribution_ids_with_value)) | contacts_with_blank
            else:
                contacts = contacts.filter(Q(id__in=attribution_ids)) | contacts_with_blank
        else:
            medium_query = Q()
            for medium in utm_medium_list:
                medium_query |= Q(utm_medium__iexact=medium)
            attribution_ids = LeadAttribution.objects.filter(medium_query).values_list('bigin_contact_id', flat=True)
            contacts = contacts.filter(id__in=attribution_ids)

    if utm_term_list:
        if 'blank' in utm_term_list:
            attribution_ids = LeadAttribution.objects.filter(
                Q(utm_term__isnull=True) | Q(utm_term='')
            ).values_list('bigin_contact_id', flat=True)
            contacts_with_blank = contacts.exclude(
                id__in=LeadAttribution.objects.values_list('bigin_contact_id', flat=True)
            )

            term_query = Q()
            for term in utm_term_list:
                if term != 'blank':
                    term_query |= Q(utm_term__icontains=term)
            if term_query:
                attribution_ids_with_value = LeadAttribution.objects.filter(term_query).values_list('bigin_contact_id', flat=True)
                contacts = contacts.filter(Q(id__in=attribution_ids) | Q(id__in=attribution_ids_with_value)) | contacts_with_blank
            else:
                contacts = contacts.filter(Q(id__in=attribution_ids)) | contacts_with_blank
        else:
            term_query = Q()
            for term in utm_term_list:
                term_query |= Q(utm_term__icontains=term)
            attribution_ids = LeadAttribution.objects.filter(term_query).values_list('bigin_contact_id', flat=True)
            contacts = contacts.filter(id__in=attribution_ids)

    if utm_content_list:
        if 'blank' in utm_content_list:
            attribution_ids = LeadAttribution.objects.filter(
                Q(utm_content__isnull=True) | Q(utm_content='')
            ).values_list('bigin_contact_id', flat=True)
            contacts_with_blank = contacts.exclude(
                id__in=LeadAttribution.objects.values_list('bigin_contact_id', flat=True)
            )

            content_query = Q()
            for content in utm_content_list:
                if content != 'blank':
                    content_query |= Q(utm_content__icontains=content)
            if content_query:
                attribution_ids_with_value = LeadAttribution.objects.filter(content_query).values_list('bigin_contact_id', flat=True)
                contacts = contacts.filter(Q(id__in=attribution_ids) | Q(id__in=attribution_ids_with_value)) | contacts_with_blank
            else:
                contacts = contacts.filter(Q(id__in=attribution_ids)) | contacts_with_blank
        else:
            content_query = Q()
            for content in utm_content_list:
                content_query |= Q(utm_content__icontains=content)
            attribution_ids = LeadAttribution.objects.filter(content_query).values_list('bigin_contact_id', flat=True)
            contacts = contacts.filter(id__in=attribution_ids)

    # Apply area_range filter (area_requirement is CharField, so we filter in Python)
    if area_range and area_range != 'blank':
        # Since area_requirement is a CharField, we need to filter in Python after fetching
        # Store the range for later filtering
        pass  # Will be handled in pagination section
    elif area_range == 'blank':
        contacts = contacts.filter(Q(area_requirement__isnull=True) | Q(area_requirement='') | Q(area_requirement='0'))
    
    # Process contacts for display
    contacts_list = list(contacts)
    
    # Get contact IDs for deal lookup
    contact_ids = [c.bigin_id for c in contacts_list]
    
    # Fetch related deals for conversion dates
    from integrations.bigin.models import BiginRecord
    deals = BiginRecord.objects.filter(
        module='Pipelines',
        raw__Contact_Name__id__in=contact_ids
    ).values('raw')
    
    # Create contact_id -> conversion_date mapping
    contact_to_conversion_date = {}
    for deal in deals:
        contact_id = deal['raw'].get('Contact_Name', {}).get('id')
        conversion_date = deal['raw'].get('Conversion_Date')
        if contact_id and conversion_date:
            if contact_id not in contact_to_conversion_date:
                contact_to_conversion_date[contact_id] = conversion_date
    
    # Enrich contacts for display
    for contact in contacts_list:
        # Add conversion date
        raw_date = contact_to_conversion_date.get(contact.bigin_id)
        if raw_date:
            try:
                date_obj = datetime.strptime(raw_date, '%Y-%m-%d')
                contact.conversion_date = date_obj.strftime('%d-%b-%Y')
            except:
                contact.conversion_date = raw_date
        else:
            contact.conversion_date = None
        
        # Clean locations - handle JSON array format
        if contact.locations:
            try:
                import json
                # Try parsing as JSON array first
                if contact.locations.startswith('['):
                    locations_data = json.loads(contact.locations)
                    contact.locations_list = [loc.strip() for loc in locations_data if loc and loc.strip()]
                else:
                    # Fallback to comma-separated
                    contact.locations_list = [loc.strip() for loc in contact.locations.split(',') if loc.strip()]
            except (json.JSONDecodeError, TypeError):
                # Fallback to comma-separated
                cleaned = contact.locations.replace('[', '').replace(']', '').replace("'", "").replace('"', '')
                contact.locations_list = [loc.strip() for loc in cleaned.split(',') if loc.strip()]
        elif hasattr(contact, 'location') and contact.location:
            contact.locations_list = [contact.location]
        else:
            contact.locations_list = []
        
        # Clean status
        if contact.status:
            contact.status_list = [s.strip() for s in contact.status.split(',') if s.strip()]
        else:
            contact.status_list = []

    # Get unique values for dropdown filters (based on RBAC) - with caching
    if request.user.role == 'sales_manager':
        base_filter = Q(owner__iexact=request.user.get_full_name(), module='Contacts')
        cache_key_prefix = f'bigin_filters_{request.user.id}'
    else:
        base_filter = Q(module='Contacts')
        cache_key_prefix = 'bigin_filters_all'

    # Try to get from cache (1-hour TTL)
    cache_key = f'{cache_key_prefix}_v1'
    cached_filters = cache.get(cache_key)

    if cached_filters:
        owners = cached_filters['owners']
        types = cached_filters['types']
        lead_stages = cached_filters['lead_stages']
        industry_types = cached_filters['industry_types']
        lead_sources = cached_filters['lead_sources']
        reasons = cached_filters.get('reasons', [])
    else:
        # Get distinct values with separate queries (optimized with indexes)
        owners = list(BiginContact.objects.filter(base_filter, owner__isnull=False).exclude(owner='').values_list('owner', flat=True).distinct().order_by('owner'))
        types = list(BiginContact.objects.filter(base_filter, contact_type__isnull=False).exclude(contact_type='').values_list('contact_type', flat=True).distinct().order_by('contact_type'))
        lead_stages = list(BiginContact.objects.filter(base_filter, lead_stage__isnull=False).exclude(lead_stage='').values_list('lead_stage', flat=True).distinct().order_by('lead_stage'))
        industry_types = list(BiginContact.objects.filter(base_filter, industry_type__isnull=False).exclude(industry_type='').values_list('industry_type', flat=True).distinct().order_by('industry_type'))
        lead_sources = list(BiginContact.objects.filter(base_filter, lead_source__isnull=False).exclude(lead_source='').values_list('lead_source', flat=True).distinct().order_by('lead_source'))
        reasons = list(BiginContact.objects.filter(base_filter, reason__isnull=False).exclude(reason='').values_list('reason', flat=True).distinct().order_by('reason'))

        # Cache for 1 hour
        cache.set(cache_key, {
            'owners': owners,
            'types': types,
            'lead_stages': lead_stages,
            'industry_types': industry_types,
            'lead_sources': lead_sources,
            'reasons': reasons,
        }, 3600)
    
    # Parse locations to get unique individual locations (only from May 2025 onwards)
    from django.utils import timezone as tz
    
    may_2025_start = tz.make_aware(datetime(2025, 5, 1))
    all_locations = set()
    location_contacts = BiginContact.objects.filter(
        base_filter, 
        locations__isnull=False,
        created_time__gte=may_2025_start  # Only consider records from May 2025 onwards
    ).exclude(locations='')
    
    for contact in location_contacts:
        if contact.locations:
            # Clean and parse locations
            cleaned = contact.locations.replace('[', '').replace(']', '').replace("'", "").replace('"', '')
            locs = [loc.strip() for loc in cleaned.split(',') if loc.strip()]
            all_locations.update(locs)
    
    # Sort locations alphabetically
    locations = sorted(all_locations)

    # Apply area_range filter (since area_requirement is CharField, filter in Python)
    if area_range and area_range != 'blank':
        def get_area_as_int(contact):
            try:
                return int(contact.area_requirement or 0)
            except (ValueError, TypeError):
                return 0

        if area_range == '0-1000':
            contacts_list = [c for c in contacts_list if 0 <= get_area_as_int(c) <= 1000]
        elif area_range == '1001-3000':
            contacts_list = [c for c in contacts_list if 1001 <= get_area_as_int(c) <= 3000]
        elif area_range == '3001-5000':
            contacts_list = [c for c in contacts_list if 3001 <= get_area_as_int(c) <= 5000]
        elif area_range == '5001-10000':
            contacts_list = [c for c in contacts_list if 5001 <= get_area_as_int(c) <= 10000]
        elif area_range == '10001-20000':
            contacts_list = [c for c in contacts_list if 10001 <= get_area_as_int(c) <= 20000]
        elif area_range == '20001-30000':
            contacts_list = [c for c in contacts_list if 20001 <= get_area_as_int(c) <= 30000]
        elif area_range == '30001+':
            contacts_list = [c for c in contacts_list if get_area_as_int(c) >= 30001]

    # Get distinct UTM values from LeadAttribution (for filter dropdowns)
    utm_campaigns = list(
        LeadAttribution.objects.filter(
            utm_campaign__isnull=False
        ).exclude(
            utm_campaign=''
        ).values_list('utm_campaign', flat=True).distinct().order_by('utm_campaign')
    )

    utm_mediums = list(
        LeadAttribution.objects.filter(
            utm_medium__isnull=False
        ).exclude(
            utm_medium=''
        ).values_list('utm_medium', flat=True).distinct().order_by('utm_medium')
    )

    utm_terms = list(
        LeadAttribution.objects.filter(
            utm_term__isnull=False
        ).exclude(
            utm_term=''
        ).values_list('utm_term', flat=True).distinct().order_by('utm_term')
    )

    utm_contents = list(
        LeadAttribution.objects.filter(
            utm_content__isnull=False
        ).exclude(
            utm_content=''
        ).values_list('utm_content', flat=True).distinct().order_by('utm_content')
    )

    # ── Callyzer call lookup (mobile number mapping) ────────────────────────
    import re
    from integrations.callyzer.models import CallHistory

    def normalize_phone(number):
        """Strip to last 10 digits (handles +91, 0, spaces, dashes)."""
        if not number:
            return None
        digits = re.sub(r'\D', '', str(number))
        return digits[-10:] if len(digits) >= 10 else None

    try:
        call_cutoff = timezone.now() - timedelta(days=180)
        all_calls = (
            CallHistory.objects
            .filter(call_date__gte=call_cutoff.date())
            .values('client_number', 'call_type', 'call_date', 'call_time', 'recording_url')
            .order_by('call_date', 'call_time')
        )
        call_lookup = {}
        for call in all_calls:
            norm = normalize_phone(call['client_number'])
            if not norm:
                continue
            if norm not in call_lookup:
                call_lookup[norm] = {
                    'call_count': 0,
                    'last_call_date': None,
                    'last_call_type': None,
                    'last_recording_url': None,
                }
            s = call_lookup[norm]
            s['call_count'] += 1
            s['last_call_date'] = call['call_date']
            s['last_call_type'] = call['call_type']
            s['last_recording_url'] = call['recording_url'] or s['last_recording_url']
    except Exception:
        call_lookup = {}

    # Pagination
    paginator = Paginator(contacts_list, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Pre-fetch lead attributions for this page to avoid N+1 queries
    from integrations.models import LeadAttribution
    page_contact_ids = [c.id for c in page_obj]
    attributions_map = {}
    for attr in LeadAttribution.objects.filter(
        bigin_contact_id__in=page_contact_ids
    ).select_related('gmail_lead'):
        attributions_map[attr.bigin_contact_id] = attr

    # Attach call stats and pre-fetched attributions to each contact on this page
    for contact in page_obj:
        norm = normalize_phone(contact.mobile)
        contact.call_stats = call_lookup.get(norm)
        attr = attributions_map.get(contact.id)
        contact._cached_attribution = attr
        contact._cached_gmail_lead = attr.gmail_lead if attr else None

    context = {
        'page_obj': page_obj,
        'owners': owners,  # NEW
        'types': types,
        'lead_stages': lead_stages,  # NEW
        'industry_types': industry_types,
        'locations': locations,  # NEW
        'lead_sources': lead_sources,
        'reasons': reasons,
        'utm_campaigns': utm_campaigns,  # NEW
        'utm_mediums': utm_mediums,  # NEW
        'utm_terms': utm_terms,  # NEW
        'utm_contents': utm_contents,  # NEW
        'filters': {
            'search': search_query,
            'start_date': start_date,
            'end_date': end_date,
            'owner_list': owner_list,  # NEW
            'contact_type_list': contact_type_list,
            'status_list': status_list,
            'lead_stage_list': lead_stage_list,
            'industry_type_list': industry_type_list,
            'location_list': location_list,  # NEW
            'lead_source_list': lead_source_list,
            'reason_list': reason_list,
            'area_range': area_range,
            'utm_campaign_list': utm_campaign_list,  # NEW
            'utm_medium_list': utm_medium_list,  # NEW
            'utm_term_list': utm_term_list,  # NEW
            'utm_content_list': utm_content_list,  # NEW
        }
    }
    
    return render(request, 'bigin/bigin_leads.html', context)


@login_required
def bigin_dashboard(request):
    """
    Analytics dashboard with comprehensive metrics.
    Accessible to CRM Executives, Admin, and Director.
    """
    # RBAC: CRM executives, admin, director, and digital marketing can access
    if request.user.role not in ['crm_executive', 'admin', 'director', 'digital_marketing']:
        return HttpResponse("Access denied. This dashboard is only available to CRM Executives, Admin, Director, and Digital Marketing.", status=403)

    # Default to current month
    today = timezone.now().date()
    first_day_current_month = today.replace(day=1)
    # Get last day of current month
    if today.month == 12:
        last_day_current_month = today.replace(day=31)
    else:
        last_day_current_month = (today.replace(month=today.month + 1, day=1) - timedelta(days=1))

    # Get filter parameters (default to current month)
    start_date = request.GET.get('start_date', first_day_current_month.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', last_day_current_month.strftime('%Y-%m-%d'))
    contact_type = request.GET.get('contact_type', '3pl')
    lead_source_list = request.GET.getlist('lead_source')  # Multi-select lead source filter
    
    # Base queryset
    leads = BiginContact.objects.filter(module='Contacts')
    
    # Apply filters
    if start_date:
        try:
            from django.utils import timezone as tz
            start_dt = tz.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
            leads = leads.filter(created_time__gte=start_dt)
        except ValueError:
            pass
    
    if end_date:
        try:
            from django.utils import timezone as tz
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
            end_dt = tz.make_aware(end_dt)
            leads = leads.filter(created_time__lte=end_dt)
        except ValueError:
            pass
    
    if contact_type:
        leads = leads.filter(contact_type__icontains=contact_type)

    # Apply lead source filter (multi-select)
    if lead_source_list:
        if 'blank' in lead_source_list:
            source_query = Q(lead_source__isnull=True) | Q(lead_source='')
            for source in lead_source_list:
                if source != 'blank':
                    source_query |= Q(lead_source__iexact=source)
            leads = leads.filter(source_query)
        else:
            source_query = Q()
            for source in lead_source_list:
                source_query |= Q(lead_source__iexact=source)
            leads = leads.filter(source_query)

    # Helper function to get effective area
    def get_effective_area(area_str):
        try:
            area = int(area_str or 0)
            return 500 if area == 0 else area
        except (ValueError, TypeError):
            return 500

    # Materialise leads once (1 DB query) — all subsequent calculations are in Python
    leads_data = list(leads.only(
        'status', 'area_requirement', 'lead_stage',
        'industry_type', 'reason', 'owner', 'lead_source'
    ))

    # Build owner index and aggregate lookups (kept as DB queries for ordering/grouping)
    owners = leads.values('owner').annotate(count=Count('id')).order_by('-count')
    stages = leads.values('lead_stage').annotate(count=Count('id')).order_by('-count')
    sources = leads.values('lead_source').annotate(count=Count('id')).order_by('-count')[:10]

    # Group leads_data by owner for fast lookups
    from collections import defaultdict
    leads_by_owner = defaultdict(list)
    for _l in leads_data:
        leads_by_owner[_l.owner].append(_l)

    # ── Summary metrics (pure Python) ──────────────────────────────────────
    total_leads = len(leads_data)
    total_sqft = sum(get_effective_area(l.area_requirement) for l in leads_data)

    def _status_group(data, keyword):
        return [l for l in data if keyword in (l.status or '').lower()]

    converted_d = _status_group(leads_data, 'converted')
    hot_d       = _status_group(leads_data, 'hot')
    warm_d      = _status_group(leads_data, 'warm')
    cold_d      = _status_group(leads_data, 'cold')
    closed_d    = _status_group(leads_data, 'closed')
    junk_d      = _status_group(leads_data, 'junk')

    converted_count = len(converted_d)
    hot_count       = len(hot_d)
    warm_count      = len(warm_d)
    cold_count      = len(cold_d)
    closed_count    = len(closed_d)
    junk_count      = len(junk_d)

    converted_sqft = sum(get_effective_area(l.area_requirement) for l in converted_d)
    hot_sqft       = sum(get_effective_area(l.area_requirement) for l in hot_d)
    warm_sqft      = sum(get_effective_area(l.area_requirement) for l in warm_d)
    cold_sqft      = sum(get_effective_area(l.area_requirement) for l in cold_d)
    closed_sqft    = sum(get_effective_area(l.area_requirement) for l in closed_d)
    junk_sqft      = sum(get_effective_area(l.area_requirement) for l in junk_d)

    conversion_rate = (converted_count / total_leads * 100) if total_leads > 0 else 0
    avg_area = total_sqft / total_leads if total_leads > 0 else 0

    # Blank/0 field metrics — Python
    area_blank_or_zero = sum(
        1 for l in leads_data
        if not l.area_requirement or l.area_requirement in ('', '0')
    )
    status_blank = sum(1 for l in leads_data if not l.status)
    lead_stage_blank = sum(1 for l in leads_data if not l.lead_stage)
    industry_type_blank = sum(1 for l in leads_data if not l.industry_type)
    reason_blank = sum(
        1 for l in leads_data
        if (not l.reason)
        and any(x in (l.status or '').lower() for x in ('cold', 'closed', 'junk'))
    )

    # Calculate percentages for blank fields
    area_blank_pct = (area_blank_or_zero / total_leads * 100) if total_leads > 0 else 0
    status_blank_pct = (status_blank / total_leads * 100) if total_leads > 0 else 0
    lead_stage_blank_pct = (lead_stage_blank / total_leads * 100) if total_leads > 0 else 0
    industry_type_blank_pct = (industry_type_blank / total_leads * 100) if total_leads > 0 else 0
    reason_blank_pct = (reason_blank / total_leads * 100) if total_leads > 0 else 0

    metrics = {
        'total_leads': total_leads,
        'total_sqft': total_sqft,
        'converted_count': converted_count,
        'converted_sqft': converted_sqft,
        'conversion_rate': conversion_rate,
        'hot_count': hot_count,
        'hot_sqft': hot_sqft,
        'warm_count': warm_count,
        'warm_sqft': warm_sqft,
        'cold_count': cold_count,
        'cold_sqft': cold_sqft,
        'closed_count': closed_count,
        'closed_sqft': closed_sqft,
        'junk_count': junk_count,
        'junk_sqft': junk_sqft,
        'avg_area': avg_area,
        'area_blank_or_zero': area_blank_or_zero,
        'area_blank_pct': area_blank_pct,
        'status_blank': status_blank,
        'status_blank_pct': status_blank_pct,
        'lead_stage_blank': lead_stage_blank,
        'lead_stage_blank_pct': lead_stage_blank_pct,
        'industry_type_blank': industry_type_blank,
        'industry_type_blank_pct': industry_type_blank_pct,
        'reason_blank': reason_blank,
        'reason_blank_pct': reason_blank_pct,
    }
    
    # Area requirement buckets with status breakdown (updated ranges as per requirement)
    area_ranges = [
        ('0-1000', 0, 1000),
        ('1001-3000', 1001, 3000),
        ('3001-5000', 3001, 5000),
        ('5001-10000', 5001, 10000),
        ('10001-20000', 10001, 20000),
        ('20001-30000', 20001, 30000),
        ('30001+', 30001, 999999999),
    ]

    area_buckets = []
    status_totals = {
        'hot_count': 0, 'hot_sqft': 0,
        'warm_count': 0, 'warm_sqft': 0,
        'cold_count': 0, 'cold_sqft': 0,
        'closed_count': 0, 'closed_sqft': 0,
        'junk_count': 0, 'junk_sqft': 0,
        'converted_count': 0, 'converted_sqft': 0,
    }

    for range_label, min_area, max_area in area_ranges:
        bucket_leads = [lead for lead in leads_data if min_area <= get_effective_area(lead.area_requirement) <= max_area]
        bucket_count = len(bucket_leads)
        bucket_sqft = sum(get_effective_area(lead.area_requirement) for lead in bucket_leads)
        bucket_pct = (bucket_sqft / total_sqft * 100) if total_sqft > 0 else 0

        # Count and sqft for each status
        hot_leads = [lead for lead in bucket_leads if 'hot' in (lead.status or '').lower()]
        warm_leads = [lead for lead in bucket_leads if 'warm' in (lead.status or '').lower()]
        cold_leads = [lead for lead in bucket_leads if 'cold' in (lead.status or '').lower()]
        closed_leads = [lead for lead in bucket_leads if 'closed' in (lead.status or '').lower()]
        junk_leads = [lead for lead in bucket_leads if 'junk' in (lead.status or '').lower()]
        converted_leads = [lead for lead in bucket_leads if 'converted' in (lead.status or '').lower()]
        lead_gen_leads = [lead for lead in bucket_leads if 'lead generation' in (lead.status or '').lower()]

        hot_count = len(hot_leads)
        warm_count = len(warm_leads)
        cold_count = len(cold_leads)
        closed_count = len(closed_leads)
        junk_count = len(junk_leads)
        converted_count = len(converted_leads)
        lead_gen_count = len(lead_gen_leads)

        hot_sqft = sum(get_effective_area(lead.area_requirement) for lead in hot_leads)
        warm_sqft = sum(get_effective_area(lead.area_requirement) for lead in warm_leads)
        cold_sqft = sum(get_effective_area(lead.area_requirement) for lead in cold_leads)
        closed_sqft = sum(get_effective_area(lead.area_requirement) for lead in closed_leads)
        junk_sqft = sum(get_effective_area(lead.area_requirement) for lead in junk_leads)
        converted_sqft = sum(get_effective_area(lead.area_requirement) for lead in converted_leads)
        lead_gen_sqft = sum(get_effective_area(lead.area_requirement) for lead in lead_gen_leads)

        # Update totals
        status_totals['hot_count'] += hot_count
        status_totals['hot_sqft'] += hot_sqft
        status_totals['warm_count'] += warm_count
        status_totals['warm_sqft'] += warm_sqft
        status_totals['cold_count'] += cold_count
        status_totals['cold_sqft'] += cold_sqft
        status_totals['closed_count'] += closed_count
        status_totals['closed_sqft'] += closed_sqft
        status_totals['junk_count'] += junk_count
        status_totals['junk_sqft'] += junk_sqft
        status_totals['converted_count'] += converted_count
        status_totals['converted_sqft'] += converted_sqft

        # Calculate new metrics
        lead_gen_pct = (bucket_count / total_leads * 100) if total_leads > 0 else 0
        sqft_variation_pct = (bucket_sqft / total_sqft * 100) if total_sqft > 0 else 0
        avg_sqft_per_lead = (bucket_sqft / bucket_count) if bucket_count > 0 else 0

        area_buckets.append({
            'range': range_label,
            'total_count': bucket_count,
            'total_sqft': bucket_sqft,
            'percentage': bucket_pct,
            'hot_count': hot_count,
            'hot_sqft': hot_sqft,
            'warm_count': warm_count,
            'warm_sqft': warm_sqft,
            'cold_count': cold_count,
            'cold_sqft': cold_sqft,
            'closed_count': closed_count,
            'closed_sqft': closed_sqft,
            'junk_count': junk_count,
            'junk_sqft': junk_sqft,
            'converted_count': converted_count,
            'converted_sqft': converted_sqft,
            'lead_gen_pct': lead_gen_pct,
            'sqft_variation_pct': sqft_variation_pct,
            'avg_sqft_per_lead': avg_sqft_per_lead,
        })
    
    # Status breakdown
    status_config = [
        ('hot', 'Hot', '🔥'),
        ('warm', 'Warm', '🌡️'),
        ('cold', 'Cold', '❄️'),
        ('converted', 'Converted', '✅'),
        ('closed', 'Closed', '🔒'),
        ('junk', 'Junk', '🗑️'),
    ]
    
    status_breakdown = []
    for status_key, status_label, emoji in status_config:
        # Python filter over materialised data — no extra DB query
        status_leads_d = [l for l in leads_data if status_key in (l.status or '').lower()]
        status_count = len(status_leads_d)
        status_sqft = sum(get_effective_area(l.area_requirement) for l in status_leads_d)
        status_pct = (status_count / total_leads * 100) if total_leads > 0 else 0

        status_breakdown.append({
            'label': status_label,
            'emoji': emoji,
            'count': status_count,
            'sqft': status_sqft,
            'percentage': status_pct
        })

    # Lead source breakdown — sources already fetched via DB aggregate above
    source_breakdown = []
    # Use same light blue color for all source cards
    source_card_color = 'from-blue-200 to-cyan-300'

    for idx, source in enumerate(sources):
        if not source['lead_source']:
            continue
        src_name = source['lead_source']
        source_sqft = sum(
            get_effective_area(l.area_requirement)
            for l in leads_data if l.lead_source == src_name
        )
        source_pct = (source['count'] / total_leads * 100) if total_leads > 0 else 0

        source_breakdown.append({
            'name': src_name,
            'count': source['count'],
            'sqft': source_sqft,
            'percentage': source_pct,
            'color': source_card_color
        })

    # Team performance — owners already fetched via DB aggregate above
    team_performance = []

    for owner in owners:
        owner_key = owner['owner']
        owner_name = owner_key if owner_key else 'Unassigned'

        # All leads for this owner — from in-memory dict
        od = leads_by_owner.get(owner_key, [])
        owner_count = len(od)
        owner_sqft = sum(get_effective_area(l.area_requirement) for l in od)

        # Data quality metrics — Python
        area_blank      = sum(1 for l in od if not l.area_requirement or l.area_requirement in ('', '0'))
        status_blank    = sum(1 for l in od if not l.status)
        lead_stage_blank = sum(1 for l in od if not l.lead_stage)
        industry_blank  = sum(1 for l in od if not l.industry_type)
        reason_blank    = sum(
            1 for l in od
            if (not l.reason) and any(x in (l.status or '').lower() for x in ('cold', 'closed', 'junk'))
        )

        # Status breakdown — Python
        hot_d_o       = _status_group(od, 'hot')
        warm_d_o      = _status_group(od, 'warm')
        cold_d_o      = _status_group(od, 'cold')
        converted_d_o = _status_group(od, 'converted')
        closed_d_o    = _status_group(od, 'closed')
        junk_d_o      = _status_group(od, 'junk')

        assigned_pct = (owner_count / total_leads * 100) if total_leads > 0 else 0
        sqft_pct = (owner_sqft / total_sqft * 100) if total_sqft > 0 else 0

        team_performance.append({
            'name': owner_name,
            'total_leads': owner_count,
            'assigned_pct': assigned_pct,
            'total_sqft': owner_sqft,
            'sqft_pct': sqft_pct,
            'hot_count': len(hot_d_o),
            'hot_sqft': sum(get_effective_area(l.area_requirement) for l in hot_d_o),
            'warm_count': len(warm_d_o),
            'warm_sqft': sum(get_effective_area(l.area_requirement) for l in warm_d_o),
            'cold_count': len(cold_d_o),
            'cold_sqft': sum(get_effective_area(l.area_requirement) for l in cold_d_o),
            'converted_count': len(converted_d_o),
            'converted_sqft': sum(get_effective_area(l.area_requirement) for l in converted_d_o),
            'closed_count': len(closed_d_o),
            'closed_sqft': sum(get_effective_area(l.area_requirement) for l in closed_d_o),
            'junk_count': len(junk_d_o),
            'junk_sqft': sum(get_effective_area(l.area_requirement) for l in junk_d_o),
            'area_blank': area_blank,
            'status_blank': status_blank,
            'lead_stage_blank': lead_stage_blank,
            'industry_blank': industry_blank,
            'reason_blank': reason_blank,
        })
    
    # Lead stage breakdown by owner (redesigned structure)
    # stages already fetched via DB aggregate above

    # Get all distinct owners for columns — from materialised data
    owner_names = []
    for owner in owners:
        owner_names.append(owner['owner'] if owner['owner'] else 'Unassigned')

    # Build per-(stage, owner) index from materialised data
    _stage_owner_idx = defaultdict(lambda: defaultdict(list))
    for _l in leads_data:
        if _l.lead_stage:
            _owner_key = _l.owner if _l.owner else 'Unassigned'
            _stage_owner_idx[_l.lead_stage][_owner_key].append(_l)

    # Build stage_by_owner: {stage: {owner: {count, sqft}, TOTAL: {count, sqft}}}
    stage_by_owner = {}
    for stage in stages:
        if not stage['lead_stage']:
            continue

        stage_name = stage['lead_stage']
        stage_by_owner[stage_name] = {}

        total_stage_count = 0
        total_stage_sqft = 0

        for owner_name in owner_names:
            od_s = _stage_owner_idx[stage_name].get(owner_name, [])
            owner_stage_count = len(od_s)
            owner_stage_sqft = sum(get_effective_area(l.area_requirement) for l in od_s)

            stage_by_owner[stage_name][owner_name] = {
                'count': owner_stage_count,
                'sqft': owner_stage_sqft
            }

            total_stage_count += owner_stage_count
            total_stage_sqft += owner_stage_sqft

        stage_by_owner[stage_name]['TOTAL'] = {
            'count': total_stage_count,
            'sqft': total_stage_sqft
        }

    # For backward compatibility, keep old format too — Python from materialised
    _stage_all_idx = defaultdict(list)
    for _l in leads_data:
        if _l.lead_stage:
            _stage_all_idx[_l.lead_stage].append(_l)

    stage_breakdown = []
    for stage in stages:
        if not stage['lead_stage']:
            continue

        sl = _stage_all_idx.get(stage['lead_stage'], [])
        stage_sqft = sum(get_effective_area(l.area_requirement) for l in sl)
        stage_pct = (stage['count'] / total_leads * 100) if total_leads > 0 else 0

        stage_breakdown.append({
            'stage': stage['lead_stage'],
            'count': stage['count'],
            'sqft': stage_sqft,
            'percentage': stage_pct
        })
    
    # Get all distinct lead sources for filter dropdown
    all_lead_sources = BiginContact.objects.filter(
        module='Contacts',
        lead_source__isnull=False
    ).exclude(
        lead_source=''
    ).values_list('lead_source', flat=True).distinct().order_by('lead_source')

    # Sales Team Area Breakdown - with status filters
    sales_team_breakdown = {}
    area_ranges_for_team = [
        ('blanks', None, None),
        ('range_0_1000', 0, 1000),
        ('range_1001_3000', 1001, 3000),
        ('range_3001_5000', 3001, 5000),
        ('range_5001_10000', 5001, 10000),
        ('range_10001_20000', 10001, 20000),
        ('range_20001_30000', 20001, 30000),
        ('range_30001_plus', 30001, 999999999),
    ]

    # Status filters to calculate for
    status_filters = {
        'all': None,  # All leads
        'hot': 'hot',
        'warm': 'warm',
        'cold': 'cold',
        'converted': 'converted',
        'closed': 'closed',
        'junk': 'junk',
    }

    for status_key, status_value in status_filters.items():
        sales_team_breakdown[status_key] = []

        for owner in owners:
            owner_key = owner['owner']
            owner_name = owner_key if owner_key else 'Unassigned'

            # Python-side filter from materialised data — no DB query
            od = leads_by_owner.get(owner_key, [])
            if status_value:
                od = [l for l in od if status_value in (l.status or '').lower()]

            row = {'name': owner_name}
            total_owner_sqft = 0
            total_owner_count = 0

            for range_key, min_area, max_area in area_ranges_for_team:
                if range_key == 'blanks':
                    # Blank/zero area - only store count, not sqft (displayed as count only)
                    range_leads = [
                        l for l in od
                        if not l.area_requirement
                        or l.area_requirement == '0'
                        or (isinstance(l.area_requirement, str) and l.area_requirement.strip() == '')
                    ]
                    range_count = len(range_leads)
                    range_sqft = 0  # Not used for blanks
                else:
                    range_leads = [l for l in od if min_area <= get_effective_area(l.area_requirement) <= max_area]
                    range_sqft = sum(get_effective_area(l.area_requirement) for l in range_leads)
                    range_count = len(range_leads)

                # Store both sqft and count
                row[f'{range_key}_sqft'] = range_sqft
                row[f'{range_key}_count'] = range_count

                # Only add to totals if not blanks (blanks already counted in 0-1000)
                if range_key != 'blanks':
                    total_owner_sqft += range_sqft
                    total_owner_count += range_count

            row['total_sqft'] = total_owner_sqft
            row['total_count'] = total_owner_count
            sales_team_breakdown[status_key].append(row)

    context = {
        'metrics': metrics,
        'area_buckets': area_buckets,
        'status_totals': status_totals,
        'status_breakdown': status_breakdown,
        'source_breakdown': source_breakdown,
        'team_performance': team_performance,
        'stage_breakdown': stage_breakdown,
        'stage_by_owner': stage_by_owner,
        'owner_names': owner_names,
        'sales_team_breakdown': sales_team_breakdown,
        'all_lead_sources': all_lead_sources,
        'filters': {
            'start_date': start_date,
            'end_date': end_date,
            'contact_type': contact_type,
            'lead_source_list': lead_source_list,
        }
    }
    
    return render(request, 'bigin/bigin_dashboard.html', context)


def fetch_notes_ajax(request, contact_id):
    """
    AJAX endpoint to fetch/cache notes for a contact.
    Returns JSON with notes content.
    """
    try:
        contact = BiginContact.objects.get(bigin_id=contact_id, module='Contacts')
        
        # Check if we need fresh notes
        if contact.needs_notes_refresh:
            # Fetch from API
            notes_content = fetch_contact_notes(contact_id)
            
            # Update cache
            contact.notes = notes_content
            contact.notes_fetched_at = timezone.now()
            contact.save(update_fields=['notes', 'notes_fetched_at'])
            
            cached = False
        else:
            notes_content = contact.notes or "[No Notes Found]"
            cached = True
        
        return JsonResponse({
            'success': True,
            'notes': notes_content,
            'cached': cached
        })
    
    except BiginContact.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Contact not found'
        }, status=404)


@login_required
def contact_detail(request, bigin_id):
    """
    Display detailed information for a single contact.
    """
    try:
        contact = BiginContact.objects.get(bigin_id=bigin_id, module='Contacts')

        # Enrich contact data
        contact.locations_list = []
        if contact.locations:
            try:
                import json
                if contact.locations.startswith('['):
                    locations_data = json.loads(contact.locations)
                    contact.locations_list = [loc.strip() for loc in locations_data if loc and loc.strip()]
                else:
                    contact.locations_list = [loc.strip() for loc in contact.locations.split(',') if loc.strip()]
            except (json.JSONDecodeError, TypeError):
                cleaned = contact.locations.replace('[', '').replace(']', '').replace("'", "").replace('"', '')
                contact.locations_list = [loc.strip() for loc in cleaned.split(',') if loc.strip()]

        # Clean status
        contact.status_list = []
        if contact.status:
            contact.status_list = [s.strip() for s in contact.status.split(',') if s.strip()]

        # Check for conversion date from Pipelines
        from integrations.bigin.models import BiginRecord
        contact.conversion_date = None
        if contact.bigin_id:
            deal = BiginRecord.objects.filter(
                module='Pipelines',
                raw__Contact_Name__id=contact.bigin_id
            ).first()
            if deal and deal.raw and 'Conversion_Date' in deal.raw:
                contact.conversion_date = deal.raw['Conversion_Date']

        # Fetch notes if stale or never fetched
        if contact.needs_notes_refresh:
            try:
                notes_content = fetch_contact_notes(bigin_id)
                contact.notes = notes_content
                contact.notes_fetched_at = timezone.now()
                contact.save(update_fields=['notes', 'notes_fetched_at'])
            except Exception:
                pass

        context = {
            'contact': contact
        }

        return render(request, 'bigin/contact_detail.html', context)

    except BiginContact.DoesNotExist:
        from django.shortcuts import redirect
        from django.contrib import messages
        messages.error(request, f'Contact with ID {bigin_id} not found.')
        return redirect('bigin:bigin_leads')


@login_required
def create_contact(request):
    """
    Display form to create a new contact.
    """
    # Role check
    if request.user.role not in ['admin', 'super_user', 'crm_executive', 'sales_manager', 'digital_marketing']:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, "Access denied. You don't have permission to create contacts.")
        return redirect('bigin:bigin_leads')

    return render(request, 'bigin/create_contact.html')


@login_required
def edit_contact(request, bigin_id):
    """
    Display form to edit an existing contact.
    """
    # Role check
    if request.user.role not in ['admin', 'super_user', 'crm_executive', 'sales_manager', 'digital_marketing']:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, "Access denied. You don't have permission to edit contacts.")
        return redirect('bigin:bigin_leads')

    try:
        contact = BiginContact.objects.get(bigin_id=bigin_id, module='Contacts')

        # Enrich contact data
        contact.locations_list = []
        if contact.locations:
            try:
                import json
                if contact.locations.startswith('['):
                    locations_data = json.loads(contact.locations)
                    contact.locations_list = [loc.strip() for loc in locations_data if loc and loc.strip()]
                else:
                    contact.locations_list = [loc.strip() for loc in contact.locations.split(',') if loc.strip()]
            except (json.JSONDecodeError, TypeError):
                cleaned = contact.locations.replace('[', '').replace(']', '').replace("'", "").replace('"', '')
                contact.locations_list = [loc.strip() for loc in cleaned.split(',') if loc.strip()]

        context = {
            'contact': contact
        }

        return render(request, 'bigin/edit_contact.html', context)

    except BiginContact.DoesNotExist:
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.error(request, f'Contact with ID {bigin_id} not found.')
        return redirect('bigin:bigin_leads')

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def settings(request):
    """
    Settings page for Bigin integration - manage tokens, sync, and connection.
    Admin/Director only.
    """
    from django.contrib import messages

    # Check if user is admin or director
    if request.user.role not in ['admin', 'director']:
        messages.error(request, "Access denied. Admin or Director access required.")
        return redirect('accounts:dashboard')

    # Get active token
    token = BiginAuthToken.objects.order_by('-created_at').first()
    is_connected = token is not None and not token.is_expired()

    # Get sync status from SyncLog
    from integrations.models import SyncLog
    running_sync = SyncLog.objects.filter(
        integration='bigin', log_kind='batch', status='running'
    ).order_by('-started_at').first()

    is_syncing = running_sync is not None
    sync_progress = running_sync.overall_progress_percent if running_sync else 0
    sync_id = running_sync.id if running_sync else None

    # Get last completed sync
    last_completed = SyncLog.objects.filter(
        integration='bigin', log_kind='batch', status='completed'
    ).order_by('-completed_at').first()

    # Get record counts
    from integrations.bigin.models import BiginRecord
    contacts_count = BiginRecord.objects.filter(module='Contacts').count()
    deals_count = BiginRecord.objects.filter(module='Pipelines').count()

    context = {
        'token': token,
        'is_connected': is_connected,
        'is_syncing': is_syncing,
        'sync_progress': sync_progress,
        'sync_id': sync_id,
        'last_completed_sync': last_completed,
        'contacts_count': contacts_count,
        'deals_count': deals_count,
        'client_id': settings.ZOHO_CLIENT_ID if hasattr(settings, 'ZOHO_CLIENT_ID') else None,
        'auth_url': settings.ZOHO_AUTH_URL if hasattr(settings, 'ZOHO_AUTH_URL') else None,
    }

    return render(request, 'bigin/settings.html', context)


@login_required
def sync_audit(request):
    """
    Sync audit dashboard for monitoring all integration syncs.
    Admin only.
    """
    # Check if user is admin
    if not request.user.is_superuser:
        return HttpResponse("Access denied. Admin only.", status=403)

    # Initial context - summary stats will be loaded via AJAX
    context = {
        'syncs_today': 0,
        'running_syncs': 0,
        'success_rate': 100,
        'records_today': 0,
        'last_sync_type': 'None',
        'last_sync_time': 'Never',
    }

    return render(request, 'dashboards/admin/sync_audit.html', context)


@login_required
def api_sync_logs(request, batch_id):
    """
    API endpoint to fetch detailed operation logs for a specific sync batch.

    Args:
        batch_id: SyncLog batch ID

    Returns:
        JSON with operation-level logs
    """
    from integrations.models import SyncLog

    try:
        # Get the batch log
        batch_log = SyncLog.objects.get(pk=batch_id, integration='bigin', log_kind='batch')

        # Get all operation logs for this batch
        operation_logs = SyncLog.objects.filter(
            batch=batch_log,
            log_kind='operation'
        ).order_by('started_at')

        # Format logs for frontend
        logs = []
        for op_log in operation_logs:
            logs.append({
                'id': op_log.id,
                'timestamp': timezone.localtime(op_log.started_at).strftime('%H:%M:%S'),
                'level': op_log.level,
                'operation': op_log.operation,
                'message': op_log.message or '',
                'duration_ms': op_log.duration_ms
            })

        return JsonResponse({
            'logs': logs,
            'batch_status': batch_log.status,
            'batch_started': batch_log.started_at.isoformat(),
            'batch_completed': batch_log.completed_at.isoformat() if batch_log.completed_at else None
        })

    except SyncLog.DoesNotExist:
        return JsonResponse({'error': 'Sync log not found'}, status=404)
    except Exception as e:
        logger.error(f"Failed to fetch sync logs: {e}")
        return JsonResponse({'error': str(e)}, status=500)