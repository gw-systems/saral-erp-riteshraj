"""
Stale Lead Checker for Bigin Contacts.
Fires alerts to CRM team for leads with no real CRM activity within 45 minutes of creation.

Rules:
- Only checks leads created TODAY
- Vivek Tiwari's automated touches do NOT count as real CRM activity
  (detected via raw['Modified_By']['name'])
- Deduplicates via Django cache — each lead alerts only once per 4 hours
"""
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
import logging

from .models import BiginRecord
from accounts.models import User
from accounts.notifications import create_notification

logger = logging.getLogger(__name__)

ALERT_WINDOW_MINUTES = 45
VIVEK_NAME = 'Vivek Tiwari'
DEDUP_CACHE_TTL = 4 * 60 * 60  # 4 hours — prevents re-alerting for same lead


def check_stale_leads():
    """
    Find leads created today with no real CRM activity in 45 minutes.
    Sends one-time alert (deduplicated via cache) to all crm_executive users.

    Returns:
        dict with keys: checked, alerted, skipped_dedup
    """
    now = timezone.now()
    today = now.date()
    alert_cutoff = now - timedelta(minutes=ALERT_WINDOW_MINUTES)

    # Leads created today and old enough that 45-minute window has elapsed
    candidates = BiginRecord.objects.filter(
        module='Contacts',
        created_time__date=today,
        created_time__lte=alert_cutoff,
    ).only('bigin_id', 'full_name', 'mobile', 'owner', 'created_time',
           'last_activity_time', 'raw')

    crm_team = list(User.objects.filter(role='crm_executive', is_active=True))
    if not crm_team:
        logger.warning("[StaleLeadChecker] No active crm_executive users found — skipping.")
        return {'checked': 0, 'alerted': 0, 'skipped_dedup': 0}

    checked = 0
    alerted = 0
    skipped_dedup = 0

    for lead in candidates:
        checked += 1
        cache_key = f'stale_lead_alert_{lead.bigin_id}'

        # Dedup: skip if we already alerted for this lead recently
        if cache.get(cache_key):
            skipped_dedup += 1
            continue

        # If a real CRM person has already acted on this lead, no alert needed
        if _has_real_crm_activity(lead):
            continue

        # Build the lead URL for the notification action button
        search_term = lead.mobile or lead.full_name or ''
        lead_url = f'/integrations/bigin/leads/?search={search_term}'

        created_local = timezone.localtime(lead.created_time).strftime('%H:%M')

        for user in crm_team:
            create_notification(
                recipient=user,
                title=f'No CRM activity on new lead: {lead.full_name}',
                message=(
                    f'Lead "{lead.full_name}" (assigned to: {lead.owner or "Unassigned"}) '
                    f'was created at {created_local} today and has had no CRM activity '
                    f'in the last {ALERT_WINDOW_MINUTES} minutes.'
                ),
                notification_type='system_alert',
                priority='high',
                severity='warning',
                category='alert',
                action_url=lead_url,
                action_label='View Lead',
                metadata={
                    'bigin_id': lead.bigin_id,
                    'lead_name': lead.full_name,
                    'owner': lead.owner,
                    'created_time': lead.created_time.isoformat(),
                },
                group_key=f'stale_lead_{lead.bigin_id}',
            )

        # Mark as alerted so the next scheduler run doesn't re-fire
        cache.set(cache_key, True, DEDUP_CACHE_TTL)
        alerted += 1
        logger.info(
            f"[StaleLeadChecker] Alert sent for lead {lead.bigin_id} "
            f"({lead.full_name}, created {created_local}, owner: {lead.owner})"
        )

    logger.info(
        f"[StaleLeadChecker] Done: {checked} checked, "
        f"{alerted} alerted, {skipped_dedup} already-alerted (skipped)"
    )
    return {'checked': checked, 'alerted': alerted, 'skipped_dedup': skipped_dedup}


def _has_real_crm_activity(lead):
    """
    Returns True if a real CRM team member (not Vivek Tiwari automation) has
    performed activity on the lead after its creation.

    Decision logic:
    - No last_activity_time at all → False (no one touched it)
    - last_activity_time exists but Modified_By == Vivek Tiwari → False (automation only)
    - last_activity_time exists and Modified_By is anyone else → True (real CRM activity)
    """
    if not lead.last_activity_time:
        return False

    # Read who last modified the record from the raw Bigin JSON
    modified_by_name = ''
    if lead.raw and isinstance(lead.raw, dict):
        mb = lead.raw.get('Modified_By')
        if isinstance(mb, dict):
            modified_by_name = mb.get('name', '')

    if modified_by_name == VIVEK_NAME:
        return False  # Automated touch — doesn't count

    return True  # A real CRM person acted on this lead
