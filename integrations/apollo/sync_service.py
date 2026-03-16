import logging
import time
from datetime import date, datetime, timedelta, timezone as dt_timezone

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from integrations.models import SyncLog

from .models import ApolloCampaign, ApolloMessage, ApolloSyncState

logger = logging.getLogger(__name__)


class ApolloCallLimitReached(Exception):
    """Raised when the sync reaches the configured per-run API budget."""


class ApolloSyncEngine:
    def __init__(
        self,
        sync_type='incremental',
        batch_log=None,
        batch_log_id=None,
        triggered_by_user=None,
        scheduled_job_id=None,
        start_date=None,
        end_date=None,
        reset_checkpoint=False,
    ):
        self.sync_type = sync_type
        self.triggered_by_user = triggered_by_user
        self.start_date = self._coerce_date(start_date)
        self.end_date = self._coerce_date(end_date)
        self.reset_checkpoint = reset_checkpoint
        self.api_key = getattr(settings, 'APOLLO_API_KEY', '')
        self.base_url = getattr(settings, 'APOLLO_BASE_URL', 'https://api.apollo.io/api/v1').rstrip('/')
        self.request_timeout = getattr(settings, 'APOLLO_REQUEST_TIMEOUT', 30)
        self.activity_delay_ms = getattr(settings, 'APOLLO_ACTIVITY_DELAY_MS', 100)
        self.incremental_lookback_days = getattr(settings, 'APOLLO_INCREMENTAL_LOOKBACK_DAYS', 30)
        self.call_limit = getattr(settings, 'APOLLO_CALL_LIMIT', 350)
        self.sync_state = ApolloSyncState.load('historical') if sync_type == 'full' else None

        if not self.api_key:
            raise ValueError('APOLLO_API_KEY is not configured')

        if batch_log is not None:
            self.batch_log = batch_log
        elif batch_log_id is not None:
            self.batch_log = SyncLog.objects.get(pk=batch_log_id, integration='apollo', log_kind='batch')
        else:
            self.batch_log = SyncLog.objects.create(
                integration='apollo',
                sync_type='apollo_full' if sync_type == 'full' else 'apollo_incremental',
                log_kind='batch',
                status='running',
                triggered_by_user=triggered_by_user or 'system',
                overall_progress_percent=0,
                scheduled_job_id=scheduled_job_id,
            )

        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Accept': 'application/json',
        })
        self.stats = {
            'campaigns_seen': 0,
            'campaigns_processed': 0,
            'messages_seen': 0,
            'messages_processed': 0,
            'created': 0,
            'updated': 0,
            'errors': 0,
            'api_calls': 0,
        }
        if self.sync_state:
            self._initialize_or_resume_state()

    def sync(self):
        started_at = timezone.now()
        self._log_operation('INFO', 'Sync Start', f'Starting Apollo {self.sync_type} sync')
        self._update_batch(
            status='running',
            overall_progress_percent=1,
            current_module='Loading campaigns',
            current_module_progress=0,
            current_module_total=0,
        )
        if self.sync_state:
            self._mark_state_run_start(started_at)
        try:
            if self.sync_state:
                result = self._sync_historical_with_checkpoints(started_at)
            else:
                result = self._sync_date_filtered(started_at)
            if self.sync_state:
                self._mark_state_run_complete('')
            return result
        except ApolloCallLimitReached:
            if self.sync_state:
                message = (
                    f'Apollo sync paused at checkpoint '
                    f'{self.sync_state.c_year}-{(self.sync_state.c_month or 0) + 1:02d}, '
                    f'campaign {self.sync_state.c_camp_idx}, page {self.sync_state.c_page}'
                )
                self._mark_state_run_complete('')
            else:
                message = (
                    'Apollo sync paused after reaching the configured API call limit. '
                    'Re-run the sync to continue upserting remaining records.'
                )
            self._finalize('partial', message, started_at)
            return self.stats
        except Exception as exc:
            self.stats['errors'] += 1
            self._log_operation(
                'ERROR',
                'Sync Failed',
                str(exc),
                details={'error_type': type(exc).__name__},
            )
            if self.sync_state:
                self._mark_state_run_complete(str(exc))
            self._finalize('failed', f'Apollo sync failed: {exc}', started_at)
            raise

    def _sync_date_filtered(self, started_at):
        campaigns = self._get_campaigns()
        self.stats['campaigns_seen'] = len(campaigns)
        self._update_batch(
            current_module='Campaign discovery',
            current_module_progress=len(campaigns),
            current_module_total=len(campaigns),
            overall_progress_percent=5 if campaigns else 100,
        )

        if not campaigns:
            self._finalize('completed', 'No Apollo campaigns matched the selected range', started_at)
            return self.stats

        for index, campaign in enumerate(campaigns, start=1):
            self._assert_not_stopped()
            campaign_name = campaign.get('name') or f"Campaign {campaign.get('id')}"
            self._update_batch(
                current_module=campaign_name,
                current_module_progress=index,
                current_module_total=len(campaigns),
                overall_progress_percent=min(95, int(((index - 1) / len(campaigns)) * 100)),
            )
            processed_count = self._sync_campaign(campaign, campaign_index=index - 1, start_page=1)
            self.stats['campaigns_processed'] += 1
            self._log_operation(
                'INFO',
                'Campaign Sync',
                f"Processed {campaign_name}",
                details={'campaign_id': campaign.get('id'), 'messages_processed': processed_count},
            )

        self._finalize(
            'completed',
            (
                f"Apollo sync completed: {self.stats['messages_processed']} messages processed, "
                f"{self.stats['created']} created, {self.stats['updated']} updated"
            ),
            started_at,
        )
        return self.stats

    def _sync_historical_with_checkpoints(self, started_at):
        if self.sync_state.is_complete:
            self._finalize('completed', 'Apollo historical sync already complete', started_at)
            return self.stats

        total_months = self._months_inclusive(
            self.sync_state.start_year,
            self.sync_state.start_month,
            self.sync_state.end_year,
            self.sync_state.end_month,
        )

        while not self.sync_state.is_complete:
            self._assert_not_stopped()
            if self._is_past_end(self.sync_state.c_year, self.sync_state.c_month):
                self._set_sync_complete()
                break

            campaigns = self._get_campaigns_for_month(self.sync_state.c_year, self.sync_state.c_month)
            self.stats['campaigns_seen'] += len(campaigns)
            month_label = self._format_month(self.sync_state.c_year, self.sync_state.c_month)
            self._update_batch(
                current_module=f'{month_label} campaigns',
                current_module_progress=min(self.sync_state.c_camp_idx, len(campaigns)),
                current_module_total=len(campaigns),
                overall_progress_percent=self._historical_progress_percent(total_months),
            )

            if not campaigns or self.sync_state.c_camp_idx >= len(campaigns):
                self._advance_to_previous_month()
                continue

            for index in range(self.sync_state.c_camp_idx, len(campaigns)):
                self._assert_not_stopped()
                campaign = campaigns[index]
                start_page = self.sync_state.c_page if index == self.sync_state.c_camp_idx else 1
                campaign_name = campaign.get('name') or f"Campaign {campaign.get('id')}"
                self._update_batch(
                    current_module=f'{month_label}: {campaign_name}',
                    current_module_progress=index + 1,
                    current_module_total=len(campaigns),
                    overall_progress_percent=self._historical_progress_percent(total_months),
                )
                processed_count = self._sync_campaign(
                    campaign,
                    campaign_index=index,
                    start_page=start_page,
                )
                self.stats['campaigns_processed'] += 1
                self.sync_state.c_camp_idx = index + 1
                self.sync_state.c_page = 1
                self._save_state()
                self._log_operation(
                    'INFO',
                    'Campaign Sync',
                    f"Processed {campaign_name}",
                    details={'campaign_id': campaign.get('id'), 'messages_processed': processed_count},
                )

            self._advance_to_previous_month()

        completion_message = (
            f"Apollo sync completed: {self.stats['messages_processed']} messages processed, "
            f"{self.stats['created']} created, {self.stats['updated']} updated"
        )
        self._finalize('completed', completion_message, started_at)
        return self.stats

    def _get_campaigns(self):
        page = 1
        campaigns = []
        while True:
            payload = self._request(
                'emailer_campaigns/search',
                params={'per_page': 100, 'page': page},
            )
            current_page = payload.get('emailer_campaigns') or []
            for campaign in current_page:
                created_at = self._parse_dt(campaign.get('created_at'))
                candidate = created_at.date() if created_at else None
                if self._date_matches(candidate):
                    campaigns.append(campaign)

            if not self._has_next_page(payload, current_page, page, 100):
                break
            page += 1
        return campaigns

    def _get_campaigns_for_month(self, year, month):
        page = 1
        campaigns = []
        while True:
            self._ensure_call_budget(year=year, month=month, campaign_index=self.sync_state.c_camp_idx, page=self.sync_state.c_page)
            payload = self._request(
                'emailer_campaigns/search',
                params={'per_page': 100, 'page': page},
            )
            current_page = payload.get('emailer_campaigns') or []
            for campaign in current_page:
                created_at = self._parse_dt(campaign.get('created_at'))
                if created_at and created_at.year == year and (created_at.month - 1) == month:
                    campaigns.append(campaign)

            if not self._has_next_page(payload, current_page, page, 100):
                break
            page += 1

        campaigns.sort(key=lambda item: item.get('created_at') or '', reverse=True)
        return campaigns

    def _sync_campaign(self, campaign, campaign_index, start_page=1):
        db_campaign, _ = ApolloCampaign.objects.update_or_create(
            apollo_id=str(campaign.get('id')),
            defaults={
                'name': campaign.get('name', '') or '',
                'created_at_remote': self._parse_dt(campaign.get('created_at')),
                'updated_at_remote': self._parse_dt(campaign.get('updated_at')),
                'raw_data': campaign,
            },
        )

        page = start_page
        processed = 0
        while True:
            if self.sync_state:
                self.sync_state.c_camp_idx = campaign_index
                self.sync_state.c_page = page
                self._save_state()

            self._ensure_call_budget(
                year=self.sync_state.c_year if self.sync_state else None,
                month=self.sync_state.c_month if self.sync_state else None,
                campaign_index=campaign_index,
                page=page,
            )
            payload = self._request(
                'emailer_messages/search',
                params={
                    'emailer_campaign_ids[]': campaign.get('id'),
                    'per_page': 100,
                    'page': page,
                },
            )
            messages = payload.get('emailer_messages') or []
            self.stats['messages_seen'] += len(messages)

            for message in messages:
                self._assert_not_stopped()
                sent_at = self._parse_dt(
                    message.get('completed_at')
                    or message.get('sent_at')
                    or message.get('updated_at')
                    or message.get('created_at')
                )
                candidate = sent_at.date() if sent_at else None
                if not self._date_matches(candidate):
                    continue

                activity_data = self._fetch_activity_data(
                    message,
                    campaign_index=campaign_index,
                    page=page,
                )
                created = self._upsert_message(db_campaign, campaign, message, activity_data)
                self.stats['messages_processed'] += 1
                processed += 1
                if created:
                    self.stats['created'] += 1
                else:
                    self.stats['updated'] += 1

                if processed % 10 == 0:
                    self._update_batch(
                        overall_progress_percent=self._historical_progress_percent()
                        if self.sync_state else min(95, self.batch_log.overall_progress_percent + 1),
                        total_records_synced=self.stats['messages_processed'],
                        records_created=self.stats['created'],
                        records_updated=self.stats['updated'],
                        records_failed=self.stats['errors'],
                        api_calls_count=self.stats['api_calls'],
                    )

            if not self._has_next_page(payload, messages, page, 100):
                break
            page += 1
        return processed

    def _fetch_activity_data(self, message, campaign_index=None, page=None):
        message_id = message.get('id')
        if not message_id:
            return {}
        if self.activity_delay_ms:
            time.sleep(self.activity_delay_ms / 1000)
        try:
            self._ensure_call_budget(
                year=self.sync_state.c_year if self.sync_state else None,
                month=self.sync_state.c_month if self.sync_state else None,
                campaign_index=campaign_index,
                page=page,
            )
            return self._request(f'emailer_messages/{message_id}/activities')
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
            if status_code and status_code < 500:
                self._log_operation(
                    'INFO',
                    'Activity Unavailable',
                    f'Activity data unavailable for message {message_id}; falling back to base payload',
                    details={'message_id': message_id, 'status_code': status_code},
                )
                return {}
            self.stats['errors'] += 1
            self._log_operation(
                'WARNING',
                'Activity Fetch Failed',
                f'Could not fetch activity for message {message_id}',
                details={'message_id': message_id, 'error': str(exc)},
            )
            return {}
        except requests.RequestException as exc:
            self.stats['errors'] += 1
            self._log_operation(
                'WARNING',
                'Activity Fetch Failed',
                f'Could not fetch activity for message {message_id}',
                details={'message_id': message_id, 'error': str(exc)},
            )
            return {}

    def _upsert_message(self, db_campaign, raw_campaign, message, activity_data):
        emailer_message = activity_data.get('emailer_message') or {}
        contact = emailer_message.get('contact') or {}
        num_opens, num_clicks = self._extract_engagement(activity_data)
        last_opened_at = self._extract_last_opened_at(activity_data)
        replied = bool(
            activity_data.get('replied')
            or emailer_message.get('replied')
            or emailer_message.get('status') == 'replied'
            or message.get('status') == 'replied'
        )
        defaults = {
            'campaign': db_campaign,
            'recipient_email': emailer_message.get('to_email') or message.get('to_email') or '',
            'first_name': contact.get('first_name', '') or '',
            'last_name': contact.get('last_name', '') or '',
            'linkedin_url': contact.get('linkedin_url', '') or '',
            'title': contact.get('title', '') or '',
            'city': contact.get('city', '') or '',
            'subject': emailer_message.get('subject') or message.get('subject') or '',
            'num_opens': num_opens,
            'num_clicks': num_clicks,
            'replied': replied,
            'status': emailer_message.get('status') or message.get('status') or '',
            'email_status': contact.get('email_status', '') or '',
            'sent_at': self._parse_dt(
                emailer_message.get('completed_at')
                or message.get('completed_at')
                or emailer_message.get('sent_at')
                or message.get('sent_at')
            ),
            'last_opened_at': last_opened_at,
            'lead_category': self._categorize_lead(num_opens),
            'raw_message': {
                'campaign': raw_campaign,
                'message': message,
                'emailer_message': emailer_message,
            },
            'raw_activity': activity_data,
        }
        _, created = ApolloMessage.objects.update_or_create(
            apollo_id=str(message.get('id')),
            defaults=defaults,
        )
        return created

    def _extract_engagement(self, activity_data):
        num_opens = activity_data.get('num_opens') or 0
        num_clicks = activity_data.get('num_clicks') or 0
        emailer_message = activity_data.get('emailer_message') or {}
        num_opens = max(num_opens, emailer_message.get('num_opens') or 0)
        num_clicks = max(num_clicks, emailer_message.get('num_clicks') or 0)
        for activity in activity_data.get('activities') or []:
            nested = activity.get('emailer_message') or {}
            num_opens = max(num_opens, nested.get('num_opens') or 0)
            num_clicks = max(num_clicks, nested.get('num_clicks') or 0)
        return num_opens, num_clicks

    def _extract_last_opened_at(self, activity_data):
        last_opened_at = activity_data.get('last_opened_at')
        if not last_opened_at:
            activities = activity_data.get('activities') or []
            if activities:
                events = activities[0].get('emailer_message_events') or []
                if events:
                    last_opened_at = events[0].get('created_at')
        return self._parse_dt(last_opened_at)

    def _categorize_lead(self, num_opens):
        if num_opens >= 3:
            return 'WARM'
        if num_opens == 2:
            return 'Engaged'
        return 'Cold'

    def _request(self, path, params=None):
        url = f'{self.base_url}/{path.lstrip("/")}'
        response = self.session.get(url, params=params or {}, timeout=self.request_timeout)
        self.stats['api_calls'] += 1
        response.raise_for_status()
        return response.json()

    def _has_next_page(self, payload, items, page, per_page):
        pagination = payload.get('pagination') or {}
        total_pages = pagination.get('total_pages') or payload.get('total_pages') or payload.get('pages')
        if total_pages:
            try:
                return int(page) < int(total_pages)
            except (TypeError, ValueError):
                pass

        next_page = pagination.get('next_page') or payload.get('next_page')
        if next_page:
            return True

        return len(items) >= per_page

    def _coerce_date(self, value):
        if not value:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        return datetime.strptime(str(value), '%Y-%m-%d').date()

    def _parse_dt(self, value):
        if not value:
            return None
        parsed = parse_datetime(str(value))
        if parsed is None:
            try:
                parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            except ValueError:
                return None
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, dt_timezone.utc)
        return parsed

    def _date_matches(self, candidate):
        if self.sync_state:
            if candidate is None:
                return False
            start_candidate = date(self.sync_state.end_year, self.sync_state.end_month + 1, 1)
            end_candidate = date(self.sync_state.start_year, self.sync_state.start_month + 1, 1)
            candidate_month = date(candidate.year, candidate.month, 1)
            return start_candidate <= candidate_month <= end_candidate

        if self.sync_type == 'incremental' and self.start_date is None:
            latest = ApolloMessage.objects.order_by('-sent_at').values_list('sent_at', flat=True).first()
            if latest:
                self.start_date = latest.date() - timedelta(days=self.incremental_lookback_days)
            else:
                self.start_date = timezone.localdate() - timedelta(days=self.incremental_lookback_days)

        if candidate is None:
            return self.start_date is None and self.end_date is None
        if self.start_date and candidate < self.start_date:
            return False
        if self.end_date and candidate > self.end_date:
            return False
        return True

    def _initialize_or_resume_state(self):
        provided_start = self.start_date
        provided_end = self.end_date
        should_reset = (
            self.reset_checkpoint
            or self.sync_state.start_year is None
            or self.sync_state.start_month is None
            or self.sync_state.end_year is None
            or self.sync_state.end_month is None
            or self.sync_state.c_year is None
            or self.sync_state.c_month is None
            or self.sync_state.is_complete
        )
        if should_reset:
            if not provided_start or not provided_end:
                raise ValueError('start_date and end_date are required to initialize Apollo historical sync state')
            self.sync_state.start_year = provided_end.year if provided_end > provided_start else provided_start.year
            self.sync_state.start_month = (provided_end.month - 1) if provided_end > provided_start else (provided_start.month - 1)
            self.sync_state.end_year = provided_start.year if provided_end > provided_start else provided_end.year
            self.sync_state.end_month = (provided_start.month - 1) if provided_end > provided_start else (provided_end.month - 1)
            if provided_end > provided_start:
                # Normalize to "latest month first" ordering.
                self.sync_state.start_year = provided_end.year
                self.sync_state.start_month = provided_end.month - 1
                self.sync_state.end_year = provided_start.year
                self.sync_state.end_month = provided_start.month - 1
            self.sync_state.c_year = self.sync_state.start_year
            self.sync_state.c_month = self.sync_state.start_month
            self.sync_state.c_camp_idx = 0
            self.sync_state.c_page = 1
            self.sync_state.is_complete = False
            self.sync_state.last_error = ''
            self.sync_state.total_messages_synced = 0
            self._save_state()

    def _ensure_call_budget(self, year=None, month=None, campaign_index=None, page=None):
        if self.stats['api_calls'] < self.call_limit:
            return
        if self.sync_state:
            if year is not None:
                self.sync_state.c_year = year
            if month is not None:
                self.sync_state.c_month = month
            if campaign_index is not None:
                self.sync_state.c_camp_idx = campaign_index
            if page is not None:
                self.sync_state.c_page = page
            self._save_state()
        raise ApolloCallLimitReached()

    def _get_previous_month(self, year, month):
        if month == 0:
            return year - 1, 11
        return year, month - 1

    def _is_past_end(self, year, month):
        return (year, month) < (self.sync_state.end_year, self.sync_state.end_month)

    def _advance_to_previous_month(self):
        next_year, next_month = self._get_previous_month(self.sync_state.c_year, self.sync_state.c_month)
        self.sync_state.c_year = next_year
        self.sync_state.c_month = next_month
        self.sync_state.c_camp_idx = 0
        self.sync_state.c_page = 1
        if self._is_past_end(next_year, next_month):
            self._set_sync_complete()
            return
        self._save_state()

    def _set_sync_complete(self):
        self.sync_state.is_complete = True
        self.sync_state.c_camp_idx = 0
        self.sync_state.c_page = 1
        self._save_state()

    def _save_state(self):
        self.sync_state.last_checkpoint_at = timezone.now()
        self.sync_state.last_api_calls = self.stats['api_calls']
        self.sync_state.total_messages_synced = self.stats['messages_processed']
        self.sync_state.save()

    def _mark_state_run_start(self, started_at):
        self.sync_state.last_run_started_at = started_at
        self.sync_state.last_error = ''
        self.sync_state.save(update_fields=['last_run_started_at', 'last_error', 'updated_at'])

    def _mark_state_run_complete(self, error_message):
        self.sync_state.last_run_completed_at = timezone.now()
        self.sync_state.last_error = error_message or ''
        self.sync_state.last_api_calls = self.stats['api_calls']
        self.sync_state.total_messages_synced = self.stats['messages_processed']
        self.sync_state.save(
            update_fields=[
                'last_run_completed_at',
                'last_error',
                'last_api_calls',
                'total_messages_synced',
                'updated_at',
            ]
        )

    def _months_inclusive(self, start_year, start_month, end_year, end_month):
        return (start_year - end_year) * 12 + (start_month - end_month) + 1

    def _historical_progress_percent(self, total_months=None):
        if not self.sync_state:
            return self.batch_log.overall_progress_percent
        total = total_months or self._months_inclusive(
            self.sync_state.start_year,
            self.sync_state.start_month,
            self.sync_state.end_year,
            self.sync_state.end_month,
        )
        current_offset = (self.sync_state.start_year - self.sync_state.c_year) * 12 + (
            self.sync_state.start_month - self.sync_state.c_month
        )
        current_offset = max(0, min(current_offset, max(total - 1, 0)))
        return min(99, int((current_offset / max(total, 1)) * 100))

    def _format_month(self, year, month):
        return date(year, month + 1, 1).strftime('%B %Y')

    def _assert_not_stopped(self):
        self.batch_log.refresh_from_db(fields=['stop_requested'])
        if self.batch_log.stop_requested:
            raise RuntimeError('Apollo sync stopped by user request')

    def _update_batch(self, **fields):
        if not fields:
            return
        for key, value in fields.items():
            setattr(self.batch_log, key, value)
        self.batch_log.save(update_fields=list(fields.keys()) + ['last_updated'])

    def _log_operation(self, level, operation, message, details=None):
        SyncLog.log(
            integration='apollo',
            sync_type='apollo_full' if self.sync_type == 'full' else 'apollo_incremental',
            level=level,
            operation=operation,
            message=message,
            details=details or {},
            batch=self.batch_log,
        )

    def _finalize(self, status, message, started_at):
        finished_at = timezone.now()
        duration_seconds = int((finished_at - started_at).total_seconds())
        self._update_batch(
            status=status,
            completed_at=finished_at,
            duration_seconds=duration_seconds,
            overall_progress_percent=100 if status == 'completed' else self.batch_log.overall_progress_percent,
            total_records_synced=self.stats['messages_processed'],
            records_created=self.stats['created'],
            records_updated=self.stats['updated'],
            records_failed=self.stats['errors'],
            errors_count=self.stats['errors'],
            api_calls_count=self.stats['api_calls'],
            error_message='' if status == 'completed' else message,
        )
        self._log_operation('SUCCESS' if status == 'completed' else 'INFO', 'Sync Complete', message)
