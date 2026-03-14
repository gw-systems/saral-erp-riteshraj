"""
Google Ads Sync Engine
Syncs campaign data, performance metrics, search terms, and device performance
"""

import logging
import time
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta
from decimal import Decimal
from .models import (
    GoogleAdsToken,
    Campaign,
    CampaignPerformance,
    DevicePerformance,
    SearchTerm,
)
from .utils.encryption import GoogleAdsEncryption
from .utils.google_ads_client import GoogleAdsAPIClient
from integrations.models import SyncLog
from integrations.sync_logger import SyncLogHandler

logger = logging.getLogger(__name__)


class GoogleAdsSync:
    """
    Sync engine for Google Ads data
    """

    def __init__(self, token_id, batch_log_id=None, scheduled_job_id=None):
        """
        Initialize sync engine

        Args:
            token_id: ID of GoogleAdsToken to sync
            batch_log_id: Optional pre-created batch log ID (if None, creates new one)
        """
        self.token = GoogleAdsToken.objects.get(id=token_id)
        self.token_data = GoogleAdsEncryption.decrypt(self.token.encrypted_token)
        self.client = GoogleAdsAPIClient(self.token.customer_id, self.token_data)
        self._sync_type = 'google_ads'

        if batch_log_id:
            # Reuse existing batch log created by view
            self._batch_log = SyncLog.objects.get(id=batch_log_id)
        else:
            # Create new batch log with stale sync cleanup
            STALE_THRESHOLD_MINUTES = 10
            with transaction.atomic():
                existing_sync = SyncLog.objects.select_for_update().filter(
                    integration='google_ads',
                    log_kind='batch',
                    status='running'
                ).order_by('-started_at').first()

                if existing_sync:
                    stale_cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
                    if existing_sync.last_updated < stale_cutoff:
                        logger.warning(f"[Google Ads Sync] Stale sync {existing_sync.id} detected, marking as stopped")
                        existing_sync.status = 'stopped'
                        existing_sync.error_message = 'Marked as stopped due to staleness (no updates for 10 minutes)'
                        existing_sync.save(update_fields=['status', 'error_message', 'last_updated'])
                    else:
                        raise RuntimeError(f"Another sync is already running (started {existing_sync.started_at})")

                # Create new batch log
                self._batch_log = SyncLog.objects.create(
                    integration='google_ads',
                    sync_type='google_ads',
                    log_kind='batch',
                    status='running',
                    triggered_by_user=self.token.account_name,
                    scheduled_job_id=scheduled_job_id,
                )

    def log(self, level, message, details=None):
        """
        Log sync operation

        Args:
            level: Log level (INFO, WARNING, ERROR)
            message: Log message
            details: Optional dict with additional details
        """
        batch_log = getattr(self, '_batch_log', None)
        if batch_log is None:
            logger.warning(f"[Google Ads] log() called but _batch_log is None! Operation: {message}")
            return  # Skip logging if no batch context

        SyncLog.log(
            integration='google_ads',
            sync_type=getattr(self, '_sync_type', 'google_ads'),
            level=level,
            operation=message,
            details=details or {},
            batch=batch_log,
        )
        logger.debug(f"[Google Ads Sync] [{level}] {message}")

    def sync_campaigns(self):
        """
        Sync campaigns from Google Ads API

        Returns:
            dict: Statistics about the sync
        """
        self.log('INFO', f"Starting campaign sync for {self.token.account_name}")

        try:
            fetch_start = time.time()
            campaigns_data = self.client.get_campaigns()
            fetch_ms = int((time.time() - fetch_start) * 1000)
            self.log('INFO', f"Fetched {len(campaigns_data)} campaigns from API ({fetch_ms}ms)")

            created_count = 0
            updated_count = 0
            error_count = 0

            with transaction.atomic():
                for campaign_data in campaigns_data:
                    try:
                        campaign, created = Campaign.objects.update_or_create(
                            token=self.token,
                            campaign_id=campaign_data['campaign_id'],
                            defaults={
                                'campaign_name': campaign_data['campaign_name'],
                                'campaign_status': campaign_data['campaign_status'],
                                'daily_budget': campaign_data.get('daily_budget'),
                                'monthly_budget': campaign_data.get('monthly_budget'),
                                'budget_delivery_method': campaign_data.get('budget_delivery_method'),
                                'budget_amount': campaign_data.get('budget_amount'),
                                'budget_type': campaign_data.get('budget_type'),
                                'bidding_strategy': campaign_data.get('bidding_strategy'),
                                'bidding_strategy_type': campaign_data.get('bidding_strategy_type')
                            }
                        )
                        if created:
                            created_count += 1
                        else:
                            updated_count += 1
                    except Exception as e:
                        error_count += 1
                        self.log('ERROR',
                                 f"Failed to save campaign {campaign_data.get('campaign_id')} "
                                 f"'{campaign_data.get('campaign_name')}': {str(e)}")

            stats = {
                'created': created_count,
                'updated': updated_count,
                'total': len(campaigns_data),
                'errors': error_count,
            }

            self.log('INFO', f"Campaign sync completed: {created_count} created, "
                     f"{updated_count} updated, {error_count} errors out of {len(campaigns_data)} total")
            return stats

        except Exception as e:
            self.log('ERROR', f"Campaign sync failed: {str(e)}", {'error': str(e)})
            raise

    def sync_campaign_performance(self, start_date, end_date):
        """
        Sync campaign performance metrics

        Args:
            start_date: Start date (YYYY-MM-DD or date object)
            end_date: End date (YYYY-MM-DD or date object)

        Returns:
            dict: Statistics about the sync
        """
        # Convert dates to strings if needed
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()

        start_date_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else start_date
        end_date_str = end_date.strftime('%Y-%m-%d') if hasattr(end_date, 'strftime') else end_date

        self.log('INFO', f"Starting performance sync for {start_date_str} to {end_date_str}")

        try:
            fetch_start = time.time()
            performance_data = self.client.get_campaign_performance(start_date_str, end_date_str)
            fetch_ms = int((time.time() - fetch_start) * 1000)
            self.log('INFO', f"Fetched {len(performance_data)} performance records from API ({fetch_ms}ms)")

            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0

            # Build a campaign ID to Campaign object mapping
            campaigns = {c.campaign_id: c for c in Campaign.objects.filter(token=self.token)}
            self.log('INFO', f"Loaded {len(campaigns)} campaigns for performance mapping")

            with transaction.atomic():
                for perf_data in performance_data:
                    try:
                        campaign_id = perf_data['campaign_id']
                        campaign = campaigns.get(campaign_id)

                        if not campaign:
                            skipped_count += 1
                            self.log('WARNING', f"Campaign {campaign_id} not found in DB, skipping performance record")
                            continue

                        # Parse date
                        date = datetime.strptime(perf_data['date'], '%Y-%m-%d').date()

                        # Calculate budget utilization
                        budget_utilization = None
                        if campaign.daily_budget and campaign.daily_budget > 0:
                            budget_utilization = Decimal(str(perf_data['cost'])) / campaign.daily_budget

                        performance, created = CampaignPerformance.objects.update_or_create(
                            campaign=campaign,
                            date=date,
                            defaults={
                                'impressions': perf_data['impressions'],
                                'clicks': perf_data['clicks'],
                                'cost': Decimal(str(perf_data['cost'])),
                                'conversions': Decimal(str(perf_data['conversions'])),
                                'conversion_value': Decimal(str(perf_data['conversion_value'])),
                                'impression_share': Decimal(str(perf_data['impression_share'])) if perf_data.get('impression_share') is not None else None,
                                'ctr': Decimal(str(perf_data['ctr'])),
                                'avg_cpc': Decimal(str(perf_data['avg_cpc'])),
                                'avg_cpm': Decimal(str(perf_data['avg_cpm'])),
                                'conversion_rate': Decimal(str(perf_data['conversion_rate'])),
                                'cost_per_conversion': Decimal(str(perf_data['cost_per_conversion'])),
                                'budget_utilization': budget_utilization,
                                'raw_data': perf_data
                            }
                        )

                        if created:
                            created_count += 1
                        else:
                            updated_count += 1
                    except Exception as e:
                        error_count += 1
                        self.log('ERROR',
                                 f"Failed to save performance record for campaign {perf_data.get('campaign_id')} "
                                 f"date {perf_data.get('date')}: {str(e)}")

            stats = {
                'created': created_count,
                'updated': updated_count,
                'total': len(performance_data),
                'skipped': skipped_count,
                'errors': error_count,
            }

            self.log('INFO', f"Performance sync completed: {created_count} created, "
                     f"{updated_count} updated, {skipped_count} skipped, {error_count} errors "
                     f"out of {len(performance_data)} total")
            return stats

        except Exception as e:
            self.log('ERROR', f"Performance sync failed: {str(e)}", {'error': str(e)})
            raise

    def sync_device_performance(self, start_date, end_date):
        """
        Sync device breakdown performance

        Args:
            start_date: Start date (YYYY-MM-DD or date object)
            end_date: End date (YYYY-MM-DD or date object)

        Returns:
            dict: Statistics about the sync
        """
        # Convert dates to strings if needed
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        if isinstance(end_date, datetime):
            end_date = end_date.date()

        start_date_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else start_date
        end_date_str = end_date.strftime('%Y-%m-%d') if hasattr(end_date, 'strftime') else end_date

        self.log('INFO', f"Starting device performance sync for {start_date_str} to {end_date_str}")

        try:
            fetch_start = time.time()
            device_data = self.client.get_device_performance(start_date_str, end_date_str)
            fetch_ms = int((time.time() - fetch_start) * 1000)
            self.log('INFO', f"Fetched {len(device_data)} device performance records from API ({fetch_ms}ms)")

            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0

            # Build a campaign ID to Campaign object mapping
            campaigns = {c.campaign_id: c for c in Campaign.objects.filter(token=self.token)}

            with transaction.atomic():
                for dev_data in device_data:
                    try:
                        campaign_id = dev_data['campaign_id']
                        campaign = campaigns.get(campaign_id)

                        if not campaign:
                            skipped_count += 1
                            self.log('WARNING', f"Campaign {campaign_id} not found, skipping device performance record")
                            continue

                        # Parse date
                        date = datetime.strptime(dev_data['date'], '%Y-%m-%d').date()

                        device_perf, created = DevicePerformance.objects.update_or_create(
                            campaign=campaign,
                            date=date,
                            device=dev_data['device'],
                            defaults={
                                'impressions': dev_data['impressions'],
                                'clicks': dev_data['clicks'],
                                'cost': Decimal(str(dev_data['cost'])),
                                'conversions': Decimal(str(dev_data['conversions'])),
                                'ctr': Decimal(str(dev_data['ctr'])),
                                'avg_cpc': Decimal(str(dev_data['avg_cpc'])),
                                'conversion_rate': Decimal(str(dev_data['conversion_rate'])),
                                'raw_data': dev_data
                            }
                        )

                        if created:
                            created_count += 1
                        else:
                            updated_count += 1
                    except Exception as e:
                        error_count += 1
                        self.log('ERROR',
                                 f"Failed to save device performance for campaign {dev_data.get('campaign_id')} "
                                 f"device {dev_data.get('device')} date {dev_data.get('date')}: {str(e)}")

            stats = {
                'created': created_count,
                'updated': updated_count,
                'total': len(device_data),
                'skipped': skipped_count,
                'errors': error_count,
            }

            self.log('INFO', f"Device performance sync completed: {created_count} created, "
                     f"{updated_count} updated, {skipped_count} skipped, {error_count} errors "
                     f"out of {len(device_data)} total")
            return stats

        except Exception as e:
            self.log('ERROR', f"Device performance sync failed: {str(e)}", {'error': str(e)})
            raise

    def sync_search_terms(self, year, month):
        """
        Sync search terms for a specific month

        Args:
            year: Year (e.g., 2024)
            month: Month (1-12)

        Returns:
            dict: Statistics about the sync
        """
        # Calculate date range for the month
        start_date = datetime(year, month, 1).date()
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)

        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        self.log('INFO', f"Starting search terms sync for {year}-{month:02d} ({start_date_str} to {end_date_str})")

        try:
            fetch_start = time.time()
            search_terms_data = self.client.get_search_terms(start_date_str, end_date_str)
            fetch_ms = int((time.time() - fetch_start) * 1000)
            self.log('INFO', f"Fetched {len(search_terms_data)} search term records from API ({fetch_ms}ms)")

            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0

            # Build a campaign ID to Campaign object mapping
            campaigns = {c.campaign_id: c for c in Campaign.objects.filter(token=self.token)}

            with transaction.atomic():
                for st_data in search_terms_data:
                    try:
                        campaign_id = st_data['campaign_id']
                        campaign = campaigns.get(campaign_id)

                        if not campaign:
                            skipped_count += 1
                            self.log('WARNING', f"Campaign {campaign_id} not found, skipping search term record")
                            continue

                        search_term, created = SearchTerm.objects.update_or_create(
                            campaign=campaign,
                            year=year,
                            month=month,
                            search_term=st_data['search_term'],
                            ad_group_id=st_data.get('ad_group_id'),
                            defaults={
                                'status': st_data.get('status'),
                                'ad_group_name': st_data.get('ad_group_name'),
                                'keyword_id': st_data.get('keyword_id'),
                                'keyword_text': st_data.get('keyword_text'),
                                'match_type': st_data.get('match_type'),
                                'impressions': st_data['impressions'],
                                'clicks': st_data['clicks'],
                                'cost': Decimal(str(st_data['cost'])),
                                'conversions': Decimal(str(st_data['conversions'])),
                                'conversion_value': Decimal(str(st_data['conversion_value'])),
                                'ctr': Decimal(str(st_data['ctr'])),
                                'avg_cpc': Decimal(str(st_data['avg_cpc'])),
                                'conversion_rate': Decimal(str(st_data['conversion_rate'])),
                                'cost_per_conversion': Decimal(str(st_data['cost_per_conversion'])),
                                'raw_data': st_data
                            }
                        )

                        if created:
                            created_count += 1
                        else:
                            updated_count += 1
                    except Exception as e:
                        error_count += 1
                        self.log('ERROR',
                                 f"Failed to save search term '{st_data.get('search_term', 'unknown')}' "
                                 f"campaign {st_data.get('campaign_id')}: {str(e)}")

            stats = {
                'created': created_count,
                'updated': updated_count,
                'total': len(search_terms_data),
                'skipped': skipped_count,
                'errors': error_count,
            }

            self.log('INFO', f"Search terms sync completed for {year}-{month:02d}: "
                     f"{created_count} created, {updated_count} updated, "
                     f"{skipped_count} skipped, {error_count} errors out of {len(search_terms_data)} total")
            return stats

        except Exception as e:
            self.log('ERROR', f"Search terms sync failed: {str(e)}", {'error': str(e)})
            raise

    def sync_all(self, sync_yesterday=True, sync_current_month_search_terms=True):
        """
        Run full sync: campaigns, yesterday's performance, and current month search terms

        Args:
            sync_yesterday: Whether to sync yesterday's data (default: True)
            sync_current_month_search_terms: Whether to sync current month search terms (default: True)

        Returns:
            dict: Combined statistics
        """
        self.log('INFO', f"Starting full sync for {self.token.account_name}")

        all_stats = {}

        _sync_log_handler = SyncLogHandler(self._batch_log, integration='google_ads', sync_type='google_ads',
                                           loggers=['integrations.google_ads'])
        _sync_log_handler._attach()
        try:
            # 1. Sync campaigns
            self._batch_log.refresh_from_db(fields=['stop_requested'])
            if self._batch_log.stop_requested:
                self._batch_log.status = 'stopped'
                self._batch_log.completed_at = timezone.now()
                self._batch_log.duration_seconds = int((timezone.now() - self._batch_log.started_at).total_seconds())
                self._batch_log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                return all_stats
            all_stats['campaigns'] = self.sync_campaigns()

            # 2. Sync yesterday's performance data
            if sync_yesterday:
                self._batch_log.refresh_from_db(fields=['stop_requested'])
                if self._batch_log.stop_requested:
                    self._batch_log.status = 'stopped'
                    self._batch_log.completed_at = timezone.now()
                    self._batch_log.duration_seconds = int((timezone.now() - self._batch_log.started_at).total_seconds())
                    self._batch_log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                    return all_stats
                yesterday = (timezone.now() - timedelta(days=1)).date()
                all_stats['performance'] = self.sync_campaign_performance(yesterday, yesterday)
                all_stats['device_performance'] = self.sync_device_performance(yesterday, yesterday)

            # 3. Sync current month search terms
            if sync_current_month_search_terms:
                self._batch_log.refresh_from_db(fields=['stop_requested'])
                if self._batch_log.stop_requested:
                    self._batch_log.status = 'stopped'
                    self._batch_log.completed_at = timezone.now()
                    self._batch_log.duration_seconds = int((timezone.now() - self._batch_log.started_at).total_seconds())
                    self._batch_log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                    return all_stats
                now = timezone.now()
                all_stats['search_terms'] = self.sync_search_terms(now.year, now.month)

            # Update last sync timestamp
            self.token.last_synced_at = timezone.now()
            self.token.save()

            self.log('INFO', f"Full sync completed: {all_stats}")

            # Calculate aggregate stats
            total_created = sum(stats.get('created', 0) for stats in all_stats.values() if isinstance(stats, dict))
            total_updated = sum(stats.get('updated', 0) for stats in all_stats.values() if isinstance(stats, dict))
            total_synced = sum(stats.get('total', 0) for stats in all_stats.values() if isinstance(stats, dict))

            # Finalize batch log
            self._batch_log.status = 'completed'
            self._batch_log.completed_at = timezone.now()
            self._batch_log.overall_progress_percent = 100
            self._batch_log.records_created = total_created
            self._batch_log.records_updated = total_updated
            self._batch_log.total_records_synced = total_synced
            self._batch_log.module_results = all_stats
            self._batch_log.api_calls_count = self._batch_log.operations.count()
            self._batch_log.save(update_fields=['status', 'completed_at', 'overall_progress_percent', 'records_created', 'records_updated', 'total_records_synced', 'module_results', 'api_calls_count', 'last_updated'])

            return all_stats

        except Exception as e:
            self.log('ERROR', f"Full sync failed: {str(e)}", {'error': str(e)})
            self._batch_log.status = 'failed'
            self._batch_log.error_message = str(e)
            self._batch_log.completed_at = timezone.now()
            self._batch_log.save(update_fields=['status', 'error_message', 'completed_at', 'last_updated'])
            raise

        finally:
            _sync_log_handler._detach()

    def sync_historical_data(self, start_date, progress_tracker=None):
        """
        Sync historical data from a specific start date to yesterday

        Args:
            start_date: Start date (YYYY-MM-DD or date object)
            progress_tracker: Optional SyncProgressTracker instance for real-time updates

        Returns:
            dict: Statistics about the sync
        """
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

        yesterday = (timezone.now() - timedelta(days=1)).date()

        self.log('INFO', f"Starting historical sync from {start_date} to {yesterday}")
        if progress_tracker:
            progress_tracker.update(message=f"🔐 Starting historical sync from {start_date}", progress_percentage=5)

        all_stats = {}

        _sync_log_handler = SyncLogHandler(self._batch_log, integration='google_ads', sync_type='google_ads',
                                           loggers=['integrations.google_ads'])
        _sync_log_handler._attach()
        try:
            # 1. Sync campaigns first
            if progress_tracker:
                progress_tracker.update(message="📡 Fetching campaign list...", progress_percentage=10)
            all_stats['campaigns'] = self.sync_campaigns()
            if progress_tracker:
                progress_tracker.update(
                    message=f"✅ Synced {all_stats['campaigns']['total']} campaigns",
                    progress_percentage=20,
                    campaigns=all_stats['campaigns']['total']
                )

            # 2. Sync performance data (in chunks to avoid API limits)
            if progress_tracker:
                progress_tracker.update(message="📈 Fetching campaign performance data...", progress_percentage=30)
            all_stats['performance'] = self.sync_campaign_performance(start_date, yesterday)
            if progress_tracker:
                progress_tracker.update(
                    message=f"✅ Synced {all_stats['performance']['total']} performance records",
                    progress_percentage=45,
                    performance=all_stats['performance']['total']
                )

            if progress_tracker:
                progress_tracker.update(message="📱 Fetching device performance data...", progress_percentage=50)
            all_stats['device_performance'] = self.sync_device_performance(start_date, yesterday)
            if progress_tracker:
                progress_tracker.update(
                    message=f"✅ Synced {all_stats['device_performance']['total']} device records",
                    progress_percentage=60,
                    device_performance=all_stats['device_performance']['total']
                )

            # 3. Sync search terms for each month in the date range
            current_date = start_date
            search_terms_stats = {'created': 0, 'updated': 0, 'total': 0}

            # Calculate total months for progress tracking
            total_months = ((yesterday.year - start_date.year) * 12 + yesterday.month - start_date.month) + 1
            month_count = 0

            while current_date <= yesterday:
                # Check for stop request each month
                self._batch_log.refresh_from_db(fields=['stop_requested'])
                if self._batch_log.stop_requested:
                    self._batch_log.status = 'stopped'
                    self._batch_log.completed_at = timezone.now()
                    self._batch_log.duration_seconds = int((timezone.now() - self._batch_log.started_at).total_seconds())
                    self._batch_log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                    return all_stats

                year = current_date.year
                month = current_date.month
                month_count += 1

                if progress_tracker:
                    month_progress = 60 + int((month_count / total_months) * 35)  # 60-95%
                    progress_tracker.update(
                        message=f"🔍 Syncing search terms for {year}-{month:02d} ({month_count}/{total_months})...",
                        progress_percentage=month_progress
                    )

                stats = self.sync_search_terms(year, month)
                search_terms_stats['created'] += stats['created']
                search_terms_stats['updated'] += stats['updated']
                search_terms_stats['total'] += stats['total']

                # Save checkpoint after each month for resumability
                if self._batch_log:
                    self._batch_log.extra_data = self._batch_log.extra_data or {}
                    self._batch_log.extra_data['last_completed_month'] = f'{year}-{month:02d}'
                    self._batch_log.save(update_fields=['extra_data', 'last_updated'])

                if progress_tracker:
                    progress_tracker.update(search_terms=search_terms_stats['total'])

                # Move to next month
                if month == 12:
                    current_date = datetime(year + 1, 1, 1).date()
                else:
                    current_date = datetime(year, month + 1, 1).date()

            all_stats['search_terms'] = search_terms_stats

            # Update last sync timestamp
            self.token.last_synced_at = timezone.now()
            self.token.save()

            self.log('INFO', f"Historical sync completed: {all_stats}")
            if progress_tracker:
                progress_tracker.update(message="💾 Finalizing sync...", progress_percentage=100)

            # Calculate aggregate stats
            total_created = sum(stats.get('created', 0) for stats in all_stats.values() if isinstance(stats, dict))
            total_updated = sum(stats.get('updated', 0) for stats in all_stats.values() if isinstance(stats, dict))
            total_synced = sum(stats.get('total', 0) for stats in all_stats.values() if isinstance(stats, dict))

            # Finalize batch log
            self._batch_log.status = 'completed'
            self._batch_log.completed_at = timezone.now()
            self._batch_log.overall_progress_percent = 100
            self._batch_log.records_created = total_created
            self._batch_log.records_updated = total_updated
            self._batch_log.total_records_synced = total_synced
            self._batch_log.module_results = all_stats
            self._batch_log.api_calls_count = self._batch_log.operations.count()
            self._batch_log.save(update_fields=['status', 'completed_at', 'overall_progress_percent', 'records_created', 'records_updated', 'total_records_synced', 'module_results', 'api_calls_count', 'last_updated'])

            return all_stats

        except Exception as e:
            self.log('ERROR', f"Historical sync failed: {str(e)}", {'error': str(e)})
            self._batch_log.status = 'failed'
            self._batch_log.error_message = str(e)
            self._batch_log.completed_at = timezone.now()
            self._batch_log.save(update_fields=['status', 'error_message', 'completed_at', 'last_updated'])
            if progress_tracker:
                progress_tracker.complete(
                    success=False,
                    message=f"❌ Sync failed: {str(e)}"
                )
            raise

        finally:
            _sync_log_handler._detach()
