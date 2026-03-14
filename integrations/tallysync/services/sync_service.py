from datetime import datetime, timedelta, date
from django.utils import timezone
from django.db import transaction
from typing import List, Dict, Optional
import re
import logging
import time

logger = logging.getLogger(__name__)

_BILLING_MONTH_MAP = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                      'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}

def _parse_billing_month_date(billing_month: str):
    """Convert 'NOV25' / 'JAN26' → date(2025,11,1). Returns None if unparseable."""
    if not billing_month or len(billing_month) < 5:
        return None
    mon = billing_month[:3].upper()
    yr_str = billing_month[3:]
    if not yr_str.isdigit():
        return None
    yr = int(yr_str)
    yr = 2000 + yr if yr < 100 else yr
    m = _BILLING_MONTH_MAP.get(mon)
    return date(yr, m, 1) if m else None

# How often to check for stop requests (every N records)
STOP_CHECK_INTERVAL = 50

from integrations.tallysync.models import (
    TallyCompany, TallyGroup, TallyLedger,
    TallyCostCentre, TallyVoucher,
)
from integrations.models import SyncLog
from integrations.tallysync.services.tally_connector_new import TallyConnector, TallyConnectionError


def _log_operation(batch_log, level, operation, message='', sub_type='', duration_ms=None):
    """
    Helper function for operation-level logging

    Args:
        batch_log: Parent SyncLog batch instance
        level: Log level (INFO, SUCCESS, WARNING, ERROR, CRITICAL)
        operation: Operation name
        message: Optional message
        sub_type: Optional sub-type (e.g., company name, ledger name)
        duration_ms: Optional duration in milliseconds
    """
    SyncLog.log(
        integration='tallysync',
        sync_type=batch_log.sync_type,
        level=level,
        operation=operation,
        message=message,
        sub_type=sub_type,
        duration_ms=duration_ms,
        batch=batch_log,
    )


class TallySyncService:
    """Service to sync data from Tally to Django database"""

    def __init__(self):
        self.connector = TallyConnector()
    
    def test_connection(self) -> Dict:
        """Test Tally connection with detailed diagnostics"""
        return self.connector.test_connection()
    
    def sync_companies(self, triggered_by_user=None) -> Dict:
        """Sync all companies from Tally

        Args:
            triggered_by_user: Username of user who triggered the sync
        """
        logger.info("Starting company sync from Tally")
        start_time = timezone.now()

        # Create batch log with stale sync cleanup
        STALE_THRESHOLD_MINUTES = 10
        with transaction.atomic():
            existing_sync = SyncLog.objects.select_for_update().filter(
                integration='tallysync',
                sync_type='tally_companies',
                log_kind='batch',
                status='running'
            ).order_by('-started_at').first()

            if existing_sync:
                stale_cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
                if existing_sync.last_updated < stale_cutoff:
                    logger.warning(f"[TallySync] Stale sync {existing_sync.id} detected, marking as stopped")
                    existing_sync.status = 'stopped'
                    existing_sync.error_message = 'Marked as stopped due to staleness (no updates for 10 minutes)'
                    existing_sync.save(update_fields=['status', 'error_message', 'last_updated'])
                else:
                    raise RuntimeError(f"Another sync is already running (started {existing_sync.started_at})")

            # Create new batch log
            log = SyncLog.objects.create(
                integration='tallysync', sync_type='tally_companies', log_kind='batch',
                status='running', triggered_by_user=triggered_by_user
            )

        # Log sync start
        _log_operation(log, 'INFO', 'sync_start', 'Starting Tally companies sync')

        from integrations.sync_logger import SyncLogHandler
        _sync_log_handler = SyncLogHandler(log, integration='tallysync', sync_type='tally_companies',
                                           loggers=['integrations.tallysync'])
        _sync_log_handler._attach()
        with transaction.atomic():
            try:
                # Log API connection attempt
                api_start = time.time()
                _log_operation(log, 'INFO', 'tally_api_connect', 'Connecting to Tally server')

                companies_data = self.connector.fetch_companies()
                api_duration_ms = int((time.time() - api_start) * 1000)

                # Log successful data fetch
                _log_operation(
                    log, 'INFO', 'data_fetch_complete',
                    f'Fetched {len(companies_data)} companies from Tally',
                    duration_ms=api_duration_ms
                )
                logger.info(f"Fetched {len(companies_data)} companies from Tally")

                created = 0
                updated = 0

                for company_data in companies_data:
                    log.refresh_from_db(fields=['stop_requested'])
                    if log.stop_requested:
                        log.status = 'stopped'
                        log.completed_at = timezone.now()
                        log.duration_seconds = int((timezone.now() - start_time).total_seconds())
                        log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                        _log_operation(log, 'WARNING', 'sync_stopped', f'Sync stopped after processing {created + updated} companies')
                        return {'status': 'stopped', 'created': created, 'updated': updated}

                    company, was_created = TallyCompany.objects.update_or_create(
                        name=company_data['name'],
                        defaults={
                            'last_synced': timezone.now(),
                            'is_active': True
                        }
                    )

                    if was_created:
                        created += 1
                        logger.debug(f"Created company: {company_data['name']}")
                        _log_operation(log, 'INFO', 'company_created', f'Created company', sub_type=company_data['name'])
                    else:
                        updated += 1
                        logger.debug(f"Updated company: {company_data['name']}")

                log.status = 'completed'
                log.total_records_synced = len(companies_data)
                log.records_created = created
                log.records_updated = updated
                log.completed_at = timezone.now()
                log.save()

                duration = (timezone.now() - start_time).total_seconds()
                duration_ms = int(duration * 1000)
                logger.info(f"Company sync completed successfully in {duration:.2f}s: {created} created, {updated} updated")

                # Log sync completion
                _log_operation(
                    log, 'SUCCESS', 'sync_complete',
                    f'Completed: {created} created, {updated} updated out of {len(companies_data)} total',
                    duration_ms=duration_ms
                )

                return {
                    'status': 'success',
                    'processed': len(companies_data),
                    'created': created,
                    'updated': updated
                }

            except Exception as e:
                log.status = 'failed'
                log.error_message = str(e)
                log.completed_at = timezone.now()
                log.save()

                duration = (timezone.now() - start_time).total_seconds()
                logger.error(f"Company sync failed after {duration:.2f}s: {str(e)}", exc_info=True)

                # Log error
                _log_operation(log, 'ERROR', 'sync_failed', f'Sync failed: {str(e)}')

                return {
                    'status': 'failed',
                    'error': str(e)
                }
            finally:
                _sync_log_handler._detach()

    @transaction.atomic
    def sync_groups(self, company: TallyCompany, triggered_by_user=None) -> Dict:
        """Sync groups for a company

        ATOMIC: Wrapped in transaction to ensure database consistency.

        Args:
            company: TallyCompany instance
            triggered_by_user: Username of user who triggered the sync
        """
        start_time = timezone.now()

        log = SyncLog.objects.create(
            integration='tallysync', sync_type='tally_ledgers', log_kind='batch',
            status='running', sub_type=company.name, triggered_by_user=triggered_by_user
        )

        # Log sync start
        _log_operation(log, 'INFO', 'sync_start', f'Starting groups sync', sub_type=company.name)

        try:
            # Log API call
            api_start = time.time()
            groups_data = self.connector.fetch_groups(company.name)
            api_duration_ms = int((time.time() - api_start) * 1000)

            # Log data fetch complete
            _log_operation(
                log, 'INFO', 'data_fetch_complete',
                f'Fetched {len(groups_data)} groups',
                sub_type=company.name,
                duration_ms=api_duration_ms
            )

            created = 0
            updated = 0

            for group_data in groups_data:
                group, was_created = TallyGroup.objects.update_or_create(
                    company=company,
                    name=group_data['name'],
                    defaults={
                        'last_synced': timezone.now()
                    }
                )

                if was_created:
                    created += 1
                else:
                    updated += 1

            company.last_synced = timezone.now()
            company.save()

            log.status = 'completed'
            log.total_records_synced = len(groups_data)
            log.records_created = created
            log.records_updated = updated
            log.completed_at = timezone.now()
            log.save()

            duration = (timezone.now() - start_time).total_seconds()
            duration_ms = int(duration * 1000)

            # Log completion
            _log_operation(
                log, 'SUCCESS', 'sync_complete',
                f'Completed: {created} created, {updated} updated',
                sub_type=company.name,
                duration_ms=duration_ms
            )

            return {
                'status': 'success',
                'processed': len(groups_data),
                'created': created,
                'updated': updated
            }

        except Exception as e:
            log.status = 'failed'
            log.error_message = str(e)
            log.completed_at = timezone.now()
            log.save()

            # Log error
            _log_operation(log, 'ERROR', 'sync_failed', f'Failed: {str(e)}', sub_type=company.name)

            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def sync_ledgers(self, company: TallyCompany, triggered_by_user=None) -> Dict:
        """Sync ledgers for a company

        Args:
            company: TallyCompany instance
            triggered_by_user: Username of user who triggered the sync
        """
        start_time = timezone.now()

        # Create batch log with stale sync cleanup
        STALE_THRESHOLD_MINUTES = 10
        with transaction.atomic():
            existing_sync = SyncLog.objects.select_for_update().filter(
                integration='tallysync',
                sync_type='tally_ledgers',
                log_kind='batch',
                status='running',
                sub_type=company.name
            ).order_by('-started_at').first()

            if existing_sync:
                stale_cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
                if existing_sync.last_updated < stale_cutoff:
                    logger.warning(f"[TallySync] Stale sync {existing_sync.id} detected for {company.name}, marking as stopped")
                    existing_sync.status = 'stopped'
                    existing_sync.error_message = 'Marked as stopped due to staleness (no updates for 10 minutes)'
                    existing_sync.save(update_fields=['status', 'error_message', 'last_updated'])
                else:
                    raise RuntimeError(f"Another sync is already running for {company.name} (started {existing_sync.started_at})")

            # Create new batch log
            log = SyncLog.objects.create(
                integration='tallysync', sync_type='tally_ledgers', log_kind='batch',
                status='running', sub_type=company.name, triggered_by_user=triggered_by_user
            )

        # Log sync start
        _log_operation(log, 'INFO', 'sync_start', f'Starting ledgers sync', sub_type=company.name)

        from integrations.sync_logger import SyncLogHandler
        _sync_log_handler = SyncLogHandler(log, integration='tallysync', sync_type='tally_ledgers',
                                           loggers=['integrations.tallysync'])
        _sync_log_handler._attach()
        try:
            # Log API call
            api_start = time.time()
            _log_operation(log, 'INFO', 'tally_api_connect', f'Fetching ledgers for {company.name} from Tally', sub_type=company.name)
            ledgers_data = self.connector.fetch_ledgers(company.name)
            api_duration_ms = int((time.time() - api_start) * 1000)

            # Log data fetch complete
            _log_operation(
                log, 'INFO', 'data_fetch_complete',
                f'Fetched {len(ledgers_data)} ledgers in {api_duration_ms}ms',
                sub_type=company.name,
                duration_ms=api_duration_ms
            )

            created = 0
            updated = 0
            error_count = 0

            for idx, ledger_data in enumerate(ledgers_data, 1):
                if idx % STOP_CHECK_INTERVAL == 0:
                    log.refresh_from_db(fields=['stop_requested'])
                    if log.stop_requested:
                        log.status = 'stopped'
                        log.completed_at = timezone.now()
                        log.duration_seconds = int((timezone.now() - start_time).total_seconds())
                        log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                        _log_operation(log, 'WARNING', 'sync_stopped',
                                       f'Stopped after processing {idx} ledgers ({created} created, {updated} updated)',
                                       sub_type=company.name)
                        return {'status': 'stopped', 'created': created, 'updated': updated}

                try:
                    ledger, was_created = TallyLedger.objects.update_or_create(
                        company=company,
                        name=ledger_data['name'],
                        defaults={
                            'parent': ledger_data.get('parent', ''),
                            'guid': ledger_data.get('guid', ''),
                            'last_synced': timezone.now()
                        }
                    )

                    if was_created:
                        created += 1
                    else:
                        updated += 1
                except Exception as e:
                    error_count += 1
                    logger.error(f"[TallySync] Failed to save ledger '{ledger_data.get('name')}': {e}")
                    _log_operation(log, 'ERROR', 'ledger_save_error',
                                   f"Failed to save ledger '{ledger_data.get('name')}': {e}",
                                   sub_type=company.name)

                # Log processing milestones (use elif so only one fires per record)
                if idx % 1000 == 0:
                    _log_operation(log, 'INFO', 'processing_milestone',
                                   f'Processed {idx} ledgers ({created} created, {updated} updated, {error_count} errors)',
                                   sub_type=company.name)
                elif idx % 500 == 0:
                    _log_operation(log, 'INFO', 'processing_milestone',
                                   f'Processed {idx} ledgers ({created} created, {updated} updated)',
                                   sub_type=company.name)
                elif idx % 100 == 0:
                    _log_operation(log, 'INFO', 'processing_milestone',
                                   f'Processed {idx} ledgers', sub_type=company.name)

            company.last_synced = timezone.now()
            company.save()

            log.status = 'completed' if error_count == 0 else 'partial'
            log.total_records_synced = len(ledgers_data)
            log.records_created = created
            log.records_updated = updated
            log.completed_at = timezone.now()
            log.duration_seconds = int((timezone.now() - start_time).total_seconds())
            log.errors_count = error_count
            log.save()

            duration_ms = int((timezone.now() - start_time).total_seconds() * 1000)
            _log_operation(
                log, 'SUCCESS' if error_count == 0 else 'WARNING', 'sync_complete',
                f'Completed: {created} created, {updated} updated, {error_count} errors out of {len(ledgers_data)} total',
                sub_type=company.name,
                duration_ms=duration_ms
            )

            return {
                'status': 'success' if error_count == 0 else 'partial',
                'processed': len(ledgers_data),
                'created': created,
                'updated': updated,
                'errors': error_count,
            }

        except Exception as e:
            log.status = 'failed'
            log.error_message = str(e)
            log.completed_at = timezone.now()
            log.duration_seconds = int((timezone.now() - start_time).total_seconds())
            log.errors_count = 1
            log.save()

            logger.error(f"[TallySync] sync_ledgers failed for {company.name}: {e}", exc_info=True)
            _log_operation(log, 'ERROR', 'sync_failed', f'Failed: {str(e)}', sub_type=company.name)

            return {
                'status': 'failed',
                'error': str(e)
            }
        finally:
            _sync_log_handler._detach()

    def sync_cost_centres(self, company: TallyCompany, triggered_by_user=None) -> Dict:
        """Sync cost centres for a company

        Args:
            company: TallyCompany instance
            triggered_by_user: Username of user who triggered the sync
        """
        start_time = timezone.now()

        # Create batch log with stale sync cleanup
        STALE_THRESHOLD_MINUTES = 10
        with transaction.atomic():
            existing_sync = SyncLog.objects.select_for_update().filter(
                integration='tallysync',
                sync_type='tally_companies',
                log_kind='batch',
                status='running',
                sub_type=company.name
            ).order_by('-started_at').first()

            if existing_sync:
                stale_cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
                if existing_sync.last_updated < stale_cutoff:
                    logger.warning(f"[TallySync] Stale sync {existing_sync.id} detected for {company.name}, marking as stopped")
                    existing_sync.status = 'stopped'
                    existing_sync.error_message = 'Marked as stopped due to staleness (no updates for 10 minutes)'
                    existing_sync.save(update_fields=['status', 'error_message', 'last_updated'])
                else:
                    raise RuntimeError(f"Another sync is already running for {company.name} (started {existing_sync.started_at})")

            # Create new batch log
            log = SyncLog.objects.create(
                integration='tallysync', sync_type='tally_companies', log_kind='batch',
                status='running', sub_type=company.name, triggered_by_user=triggered_by_user
            )

        # Log sync start
        _log_operation(log, 'INFO', 'sync_start', f'Starting cost centres sync', sub_type=company.name)

        try:
            logger.debug(f"Fetching cost centres for {company.name}")

            # Log API call
            api_start = time.time()
            _log_operation(log, 'INFO', 'tally_api_connect',
                           f'Fetching cost centres for {company.name} from Tally', sub_type=company.name)
            cost_centres_data = self.connector.fetch_cost_centres(company.name)
            api_duration_ms = int((time.time() - api_start) * 1000)

            logger.debug(f"Received {len(cost_centres_data)} cost centres")

            # Log data fetch complete
            _log_operation(
                log, 'INFO', 'data_fetch_complete',
                f'Fetched {len(cost_centres_data)} cost centres in {api_duration_ms}ms',
                sub_type=company.name,
                duration_ms=api_duration_ms
            )

            created = 0
            updated = 0
            error_count = 0

            for idx, cc_data in enumerate(cost_centres_data, 1):
                if idx % STOP_CHECK_INTERVAL == 0:
                    log.refresh_from_db(fields=['stop_requested'])
                    if log.stop_requested:
                        log.status = 'stopped'
                        log.completed_at = timezone.now()
                        log.duration_seconds = int((timezone.now() - start_time).total_seconds())
                        log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                        _log_operation(log, 'WARNING', 'sync_stopped',
                                       f'Stopped after processing {idx} cost centres ({created} created, {updated} updated)',
                                       sub_type=company.name)
                        return {'status': 'stopped', 'created': created, 'updated': updated}

                name = cc_data['name']
                code = self._extract_cost_centre_code(name)
                client_name = self._extract_client_name(name)

                try:
                    cc, was_created = TallyCostCentre.objects.update_or_create(
                        company=company,
                        code=code,
                        defaults={
                            'name': name,
                            'client_name': client_name,
                            'last_synced': timezone.now()
                        }
                    )

                    if was_created:
                        created += 1
                    else:
                        updated += 1
                except Exception as e:
                    error_count += 1
                    logger.error(f"[TallySync] Failed to save cost centre '{name}': {e}")
                    _log_operation(log, 'ERROR', 'cost_centre_save_error',
                                   f"Failed to save cost centre '{name}': {e}", sub_type=company.name)

                # Log processing milestones (elif so only one fires per idx)
                if idx % 1000 == 0:
                    _log_operation(log, 'INFO', 'processing_milestone',
                                   f'Processed {idx} cost centres ({created} created, {updated} updated, {error_count} errors)',
                                   sub_type=company.name)
                elif idx % 500 == 0:
                    _log_operation(log, 'INFO', 'processing_milestone',
                                   f'Processed {idx} cost centres ({created} created, {updated} updated)',
                                   sub_type=company.name)
                elif idx % 100 == 0:
                    _log_operation(log, 'INFO', 'processing_milestone',
                                   f'Processed {idx} cost centres', sub_type=company.name)

            company.last_synced = timezone.now()
            company.save()

            log.status = 'completed' if error_count == 0 else 'partial'
            log.total_records_synced = len(cost_centres_data)
            log.records_created = created
            log.records_updated = updated
            log.completed_at = timezone.now()
            log.duration_seconds = int((timezone.now() - start_time).total_seconds())
            log.errors_count = error_count
            log.save()

            duration_ms = int((timezone.now() - start_time).total_seconds() * 1000)
            _log_operation(
                log, 'SUCCESS' if error_count == 0 else 'WARNING', 'sync_complete',
                f'Completed: {created} created, {updated} updated, {error_count} errors out of {len(cost_centres_data)} total',
                sub_type=company.name,
                duration_ms=duration_ms
            )

            return {
                'status': 'success' if error_count == 0 else 'partial',
                'processed': len(cost_centres_data),
                'created': created,
                'updated': updated,
                'errors': error_count,
            }

        except Exception as e:
            log.status = 'failed'
            log.error_message = str(e)
            log.completed_at = timezone.now()
            log.duration_seconds = int((timezone.now() - start_time).total_seconds())
            log.errors_count = 1
            log.save()

            logger.error(f"[TallySync] sync_cost_centres failed for {company.name}: {e}", exc_info=True)
            _log_operation(log, 'ERROR', 'sync_failed', f'Failed: {str(e)}', sub_type=company.name)

            return {
                'status': 'failed',
                'error': str(e)
            }

    def sync_all_master_data(self, triggered_by_user=None) -> Dict:
        """Sync all master data (companies, groups, ledgers, cost centres)

        NOTE: Each sub-sync method is already atomic. This orchestrator
        does not need its own @transaction.atomic decorator to allow
        partial success if one company fails.

        Args:
            triggered_by_user: Username of user who triggered the sync
        """
        results = {
            'companies': None,
            'groups': {},
            'ledgers': {},
            'cost_centres': {}
        }

        # Sync companies first
        results['companies'] = self.sync_companies(triggered_by_user=triggered_by_user)

        if results['companies']['status'] != 'success':
            return results

        # Sync master data for each company
        companies = TallyCompany.objects.filter(is_active=True)

        for company in companies:
            logger.info(f"Syncing master data for: {company.name}")

            results['groups'][company.name] = self.sync_groups(company, triggered_by_user=triggered_by_user)
            results['ledgers'][company.name] = self.sync_ledgers(company, triggered_by_user=triggered_by_user)
            results['cost_centres'][company.name] = self.sync_cost_centres(company, triggered_by_user=triggered_by_user)

        return results
    
    # Helper methods
    
    def _extract_cost_centre_code(self, name: str) -> str:
        """Extract code from cost centre name
        Example: 'DL007 - (Bizcrum - ...)' -> 'DL007'
        """
        match = re.match(r'^([A-Z]{2}\d{3,4})', name)
        if match:
            return match.group(1)
        return name[:10]  # Fallback
    
    def _extract_client_name(self, name: str) -> str:
        """Extract client name from cost centre
        Example: 'DL007 - (Bizcrum Infotech - SD Logistics)' -> 'Bizcrum Infotech'
        """
        match = re.search(r'\(([^-]+)', name)
        if match:
            return match.group(1).strip()
        return ''
    

    def sync_vouchers(self, company: TallyCompany, from_date: str, to_date: str, triggered_by_user=None, scheduled_job_id=None) -> Dict:
        """Sync vouchers for a company and date range
        Dates in format: YYYYMMDD (e.g., 20251101)

        Args:
            company: TallyCompany instance
            from_date: Start date in YYYYMMDD format
            to_date: End date in YYYYMMDD format
            triggered_by_user: Username of user who triggered the sync
        """
        from integrations.tallysync.models import TallyVoucherLedgerEntry, TallyVoucherCostCentreAllocation, TallyBillReference

        start_time = timezone.now()

        # Create batch log with stale sync cleanup
        STALE_THRESHOLD_MINUTES = 10
        with transaction.atomic():
            existing_sync = SyncLog.objects.select_for_update().filter(
                integration='tallysync',
                sync_type='tally_vouchers',
                log_kind='batch',
                status='running',
                sub_type=company.name
            ).order_by('-started_at').first()

            if existing_sync:
                stale_cutoff = timezone.now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
                if existing_sync.last_updated < stale_cutoff:
                    logger.warning(f"[TallySync] Stale sync {existing_sync.id} detected for {company.name}, marking as stopped")
                    existing_sync.status = 'stopped'
                    existing_sync.error_message = 'Marked as stopped due to staleness (no updates for 10 minutes)'
                    existing_sync.save(update_fields=['status', 'error_message', 'last_updated'])
                else:
                    raise RuntimeError(f"Another sync is already running for {company.name} (started {existing_sync.started_at})")

            # Create new batch log
            log = SyncLog.objects.create(
                integration='tallysync', sync_type='tally_vouchers', log_kind='batch',
                status='running', sub_type=company.name, triggered_by_user=triggered_by_user,
                scheduled_job_id=scheduled_job_id,
            )

        # Log sync start
        _log_operation(
            log, 'INFO', 'sync_start',
            f'Starting vouchers sync for date range {from_date} to {to_date}',
            sub_type=company.name
        )

        from integrations.sync_logger import SyncLogHandler
        _sync_log_handler = SyncLogHandler(log, integration='tallysync', sync_type='tally_vouchers',
                                           loggers=['integrations.tallysync'])
        _sync_log_handler._attach()
        try:
            # Fetch vouchers — batch by year if range > 3 months to avoid Tally response truncation
            api_start = time.time()
            fd = datetime.strptime(from_date, '%Y%m%d').date()
            td = datetime.strptime(to_date, '%Y%m%d').date()
            date_span_days = (td - fd).days

            if date_span_days > 30:
                # Split into monthly batches to stay within Tally's response size limit
                import calendar
                batches = []
                batch_start = fd
                while batch_start <= td:
                    last_day = calendar.monthrange(batch_start.year, batch_start.month)[1]
                    batch_end = min(batch_start.replace(day=last_day), td)
                    batches.append((batch_start.strftime('%Y%m%d'), batch_end.strftime('%Y%m%d')))
                    if batch_start.month == 12:
                        batch_start = batch_start.replace(year=batch_start.year + 1, month=1, day=1)
                    else:
                        batch_start = batch_start.replace(month=batch_start.month + 1, day=1)

                _log_operation(log, 'INFO', 'tally_api_connect',
                               f'Fetching vouchers for {company.name} in {len(batches)} monthly batches '
                               f'({from_date} to {to_date})',
                               sub_type=company.name)
                vouchers_data = []
                for i, (batch_from, batch_to) in enumerate(batches, 1):
                    batch_label = f"{batch_from[:4]}-{batch_from[4:6]}"
                    log.current_module = f'{company.name}: fetching {batch_label} ({i}/{len(batches)})'
                    log.save(update_fields=['current_module', 'last_updated'])
                    _log_operation(log, 'INFO', 'tally_api_batch',
                                   f'Fetching batch {i}/{len(batches)}: {batch_label}...',
                                   sub_type=company.name)
                    # Brief pause between batches — prevents connection resets on cloud Tally servers
                    if i > 1:
                        time.sleep(2)
                    batch_start_t = time.time()
                    batch_vouchers = self.connector.fetch_vouchers(company.name, batch_from, batch_to)
                    batch_ms = int((time.time() - batch_start_t) * 1000)
                    _log_operation(log, 'INFO', 'tally_api_batch',
                                   f'Batch {batch_label}: {len(batch_vouchers)} vouchers in {batch_ms}ms',
                                   sub_type=company.name)
                    vouchers_data.extend(batch_vouchers)
            else:
                _log_operation(log, 'INFO', 'tally_api_connect',
                               f'Fetching vouchers for {company.name} ({from_date} to {to_date}) from Tally',
                               sub_type=company.name)
                vouchers_data = self.connector.fetch_vouchers(company.name, from_date, to_date)

            api_duration_ms = int((time.time() - api_start) * 1000)

            # Log data fetch complete
            _log_operation(
                log, 'INFO', 'data_fetch_complete',
                f'Fetched {len(vouchers_data)} vouchers from Tally in {api_duration_ms}ms',
                sub_type=company.name,
                duration_ms=api_duration_ms
            )

            created = 0
            updated = 0
            failed = 0

            # Pre-load all cost centres for this company to avoid N+1 in loop
            cost_centre_cache = {cc.name: cc for cc in TallyCostCentre.objects.filter(company=company)}

            # Pre-load existing vouchers by guid to detect unchanged vouchers
            # Key: (amount, date_str, is_cancelled) — skip ledger rebuild if unchanged
            incoming_guids = {v.get('guid') for v in vouchers_data if v.get('guid')}
            existing_vouchers = {
                v.guid: v
                for v in TallyVoucher.objects.filter(company=company, guid__in=incoming_guids)
                    .only('guid', 'amount', 'date', 'is_cancelled')
            }

            from decimal import Decimal

            for idx, voucher_data in enumerate(vouchers_data, 1):
                if idx % STOP_CHECK_INTERVAL == 0:
                    log.refresh_from_db(fields=['stop_requested'])
                    if log.stop_requested:
                        log.status = 'stopped'
                        log.completed_at = timezone.now()
                        log.duration_seconds = int((timezone.now() - start_time).total_seconds())
                        log.save(update_fields=['status', 'completed_at', 'duration_seconds', 'last_updated'])
                        _log_operation(
                            log, 'WARNING', 'sync_stopped',
                            f'Stopped after processing {idx} vouchers ({created} created, {updated} updated, {failed} failed)',
                            sub_type=company.name
                        )
                        return {'status': 'stopped', 'created': created, 'updated': updated, 'failed': failed}

                try:
                    # Parse date
                    date_str = voucher_data.get('date', '')
                    if date_str:
                        voucher_date = datetime.strptime(date_str, '%Y%m%d').date()
                    else:
                        logger.warning(f"[TallySync] Voucher {voucher_data.get('guid')} missing date, skipping")
                        _log_operation(log, 'WARNING', 'voucher_skip',
                                       f"Voucher {voucher_data.get('voucher_number', 'unknown')} missing date, skipping",
                                       sub_type=company.name)
                        failed += 1
                        continue

                    # Parse cheque_date if present
                    cheque_date_str = voucher_data.get('cheque_date', '')
                    cheque_date = None
                    if cheque_date_str:
                        try:
                            cheque_date = datetime.strptime(cheque_date_str, '%Y%m%d').date()
                        except (ValueError, TypeError):
                            pass

                    # Create/update voucher with all fetched fields
                    voucher, was_created = TallyVoucher.objects.update_or_create(
                        guid=voucher_data.get('guid'),
                        defaults={
                            'company': company,
                            'date': voucher_date,
                            'voucher_type': voucher_data.get('voucher_type', ''),
                            'voucher_number': voucher_data.get('voucher_number', ''),
                            'party_ledger_name': voucher_data.get('party_ledger_name', ''),
                            'party_name': voucher_data.get('party_name', ''),
                            'party_gstin': voucher_data.get('party_gstin', ''),
                            'party_state': voucher_data.get('party_state', ''),
                            'narration': voucher_data.get('narration', ''),
                            'reference': voucher_data.get('reference', ''),
                            'is_invoice': voucher_data.get('is_invoice', False),
                            'is_cancelled': voucher_data.get('is_cancelled', False),
                            'amount': voucher_data.get('amount', 0),
                            'eway_bill_number': voucher_data.get('eway_bill_number', ''),
                            'payment_mode': voucher_data.get('payment_mode', ''),
                            'cheque_number': voucher_data.get('cheque_number', ''),
                            'cheque_date': cheque_date,
                            'buyer_name': voucher_data.get('buyer_name', ''),
                            'buyer_gstin': voucher_data.get('buyer_gstin', ''),
                            'buyer_state': voucher_data.get('buyer_state', ''),
                            'consignee_name': voucher_data.get('consignee_name', ''),
                            'consignee_gstin': voucher_data.get('consignee_gstin', ''),
                            'raw_xml': voucher_data.get('raw_xml', ''),
                            'billing_month': voucher_data.get('billing_month', ''),
                            'billing_month_date': _parse_billing_month_date(voucher_data.get('billing_month', '')),
                            'need_to_pay': voucher_data.get('need_to_pay', ''),
                            'remark': voucher_data.get('remark', ''),
                            'credit_period': voucher_data.get('credit_period', ''),
                            'transaction_type': voucher_data.get('transaction_type', ''),
                            'utr_number': voucher_data.get('utr_number', ''),
                            'master_id': voucher_data.get('master_id'),
                            'last_synced': timezone.now()
                        }
                    )

                    # Skip ledger entry rebuild for unchanged vouchers (saves ~3 DB ops per voucher)
                    existing = existing_vouchers.get(voucher_data.get('guid'))
                    voucher_changed = (
                        was_created
                        or existing is None
                        or str(existing.amount) != str(voucher_data.get('amount', 0))
                        or existing.is_cancelled != voucher_data.get('is_cancelled', False)
                        or existing.date != voucher_date
                    )

                    if voucher_changed:
                        # Delete existing ledger entries for this voucher (to avoid duplicates on update)
                        TallyVoucherLedgerEntry.objects.filter(voucher=voucher).delete()

                        # Bulk-create ledger entries (one INSERT vs N INSERTs)
                        entries_to_create = []
                        for le_data in voucher_data.get('ledger_entries', []):
                            entries_to_create.append(TallyVoucherLedgerEntry(
                                voucher=voucher,
                                ledger_name=le_data['ledger_name'],
                                amount=Decimal(str(le_data['amount'])),
                                is_debit=le_data['is_debit'],
                                gst_class=le_data.get('gst_class', ''),
                                gst_hsn_code=le_data.get('gst_hsn_code', ''),
                                cgst_rate=Decimal(str(le_data.get('cgst_rate', 0))),
                                sgst_rate=Decimal(str(le_data.get('sgst_rate', 0))),
                                igst_rate=Decimal(str(le_data.get('igst_rate', 0))),
                                cess_rate=Decimal(str(le_data.get('cess_rate', 0))),
                                cgst_amount=Decimal(str(le_data.get('cgst_amount', 0))),
                                sgst_amount=Decimal(str(le_data.get('sgst_amount', 0))),
                                igst_amount=Decimal(str(le_data.get('igst_amount', 0))),
                                cess_amount=Decimal(str(le_data.get('cess_amount', 0))),
                                tds_nature_of_payment=le_data.get('tds_nature_of_payment', ''),
                                tds_section=le_data.get('tds_section', ''),
                                tds_amount=Decimal(str(le_data.get('tds_amount', 0))),
                            ))
                        created_entries = TallyVoucherLedgerEntry.objects.bulk_create(entries_to_create)
                        # Map by ledger_name for cost centre allocation (use in-memory, no DB query)
                        ledger_entries_map = {le.ledger_name: le for le in created_entries}

                        # Handle voucher-level cost centre — use pre-loaded cache, no N+1
                        voucher_cc_name = voucher_data.get('cost_centre_name', '')
                        if voucher_cc_name and voucher_cc_name.strip():
                            party_ledger_entry = ledger_entries_map.get(voucher_data.get('party_ledger_name', ''))
                            cost_centre = cost_centre_cache.get(voucher_cc_name)
                            if party_ledger_entry and cost_centre:
                                TallyVoucherCostCentreAllocation.objects.create(
                                    ledger_entry=party_ledger_entry,
                                    cost_centre=cost_centre,
                                    cost_centre_name=voucher_cc_name,
                                    amount=abs(party_ledger_entry.amount)
                                )

                        # Save bill references (bill-by-bill aging data)
                        bill_refs_data = voucher_data.get('bill_references', [])
                        if bill_refs_data:
                            TallyBillReference.objects.filter(
                                ledger_entry__voucher=voucher
                            ).delete()
                            bill_refs_to_create = []
                            for br in bill_refs_data:
                                le = ledger_entries_map.get(br.get('ledger_name', ''))
                                if le:
                                    bill_refs_to_create.append(TallyBillReference(
                                        ledger_entry=le,
                                        bill_name=br['bill_name'],
                                        bill_type=br.get('bill_type', ''),
                                        amount=Decimal(str(br.get('amount', 0))),
                                    ))
                            if bill_refs_to_create:
                                TallyBillReference.objects.bulk_create(bill_refs_to_create)

                    if was_created:
                        created += 1
                    else:
                        updated += 1

                    if idx % 500 == 0:
                        _log_operation(
                            log, 'INFO', 'processing_milestone',
                            f'Processed {idx} vouchers ({created} created, {updated} updated, {failed} failed)',
                            sub_type=company.name
                        )

                except Exception as e:
                    logger.error(f"Failed to process voucher {voucher_data.get('voucher_number')}: {e}", exc_info=True)
                    failed += 1
                    _log_operation(
                        log, 'ERROR', 'voucher_processing_error',
                        f"Failed to process voucher {voucher_data.get('voucher_number', 'unknown')}: {str(e)}",
                        sub_type=company.name
                    )
                    continue

            company.last_synced = timezone.now()
            company.save()

            log.status = 'completed' if failed == 0 else 'partial'
            log.total_records_synced = len(vouchers_data)
            log.records_created = created
            log.records_updated = updated
            log.records_failed = failed
            log.completed_at = timezone.now()
            log.duration_seconds = int((timezone.now() - start_time).total_seconds())
            log.errors_count = failed
            log.save()

            duration_ms = int((timezone.now() - start_time).total_seconds() * 1000)
            status_msg = f'Completed: {created} created, {updated} updated, {failed} failed out of {len(vouchers_data)} total'
            _log_operation(
                log, 'SUCCESS' if failed == 0 else 'WARNING', 'sync_complete',
                status_msg,
                sub_type=company.name,
                duration_ms=duration_ms
            )

            # Auto-verify and heal any gaps after sync completes
            verify_result = self.verify_and_heal(company, from_date, to_date, triggered_by_user=triggered_by_user)
            if verify_result.get('gap', 0) > 0:
                _log_operation(
                    log, 'WARNING', 'verify_gap_remaining',
                    f"After sync+heal: Tally={verify_result['tally_count']} DB={verify_result['db_count']} "
                    f"gap={verify_result['gap']} remaining",
                    sub_type=company.name,
                )
            elif verify_result.get('healed'):
                _log_operation(
                    log, 'SUCCESS', 'verify_healed',
                    f"Gap of {verify_result['original_gap']} vouchers was auto-healed ✓",
                    sub_type=company.name,
                )
            elif verify_result.get('tally_count', -1) >= 0:
                _log_operation(
                    log, 'INFO', 'verify_ok',
                    f"Verification ✓ Tally={verify_result['tally_count']} DB={verify_result['db_count']} "
                    f"(DB includes vouchers from all prior syncs)",
                    sub_type=company.name,
                )

            return {
                'status': 'success' if failed == 0 else 'partial',
                'processed': len(vouchers_data),
                'created': created,
                'updated': updated,
                'failed': failed,
                'verify': verify_result,
            }

        except Exception as e:
            logger.error(f"[TallySync] sync_vouchers failed for {company.name}: {e}", exc_info=True)
            log.status = 'failed'
            log.error_message = str(e)
            log.completed_at = timezone.now()
            log.duration_seconds = int((timezone.now() - start_time).total_seconds())
            log.errors_count = 1
            log.save()

            _log_operation(
                log, 'CRITICAL', 'sync_failed',
                f'Sync failed with critical error: {str(e)}',
                sub_type=company.name
            )

            return {
                'status': 'failed',
                'error': str(e)
            }
        finally:
            _sync_log_handler._detach()

    def verify_and_heal(self, company: TallyCompany, from_date: str, to_date: str,
                        triggered_by_user=None) -> Dict:
        """After a voucher sync, verify Tally count == DB count. Re-sync if gap found.

        Called automatically at the end of sync_vouchers(). Lightweight — only fetches
        voucher count (DATE field only) from Tally, not full data.

        Args:
            from_date / to_date: YYYYMMDD strings (same range just synced)
        Returns:
            dict with 'tally_count', 'db_count', 'gap', 'healed'
        """
        from datetime import datetime as dt

        fd = dt.strptime(from_date, '%Y%m%d').date()
        td = dt.strptime(to_date, '%Y%m%d').date()

        db_count = TallyVoucher.objects.filter(
            company=company, date__gte=fd, date__lte=td
        ).count()

        try:
            tally_count = self.connector.fetch_voucher_count(company.name, from_date, to_date)
        except Exception as e:
            logger.warning(f"[TallySync] verify_and_heal: count fetch failed for {company.name}: {e}")
            return {'tally_count': -1, 'db_count': db_count, 'gap': 0, 'healed': False, 'error': str(e)}

        gap = tally_count - db_count

        if gap <= 0:
            # DB >= Tally: no missing data. DB may have more from prior incremental syncs (normal).
            logger.info(f"[TallySync] verify_and_heal ✓ {company.name} {from_date}-{to_date}: "
                        f"Tally={tally_count} DB={db_count} (DB may have more from prior syncs — OK)")
            return {'tally_count': tally_count, 'db_count': db_count, 'gap': gap, 'healed': False}

        # Gap found — re-fetch vouchers directly (no verify_and_heal recursion)
        logger.warning(f"[TallySync] verify_and_heal GAP {company.name} {from_date}-{to_date}: "
                       f"Tally={tally_count} DB={db_count} missing={gap} — healing...")

        try:
            from integrations.tallysync.models import TallyVoucherLedgerEntry, TallyVoucherCostCentreAllocation, TallyBillReference
            from decimal import Decimal
            vouchers_data = self.connector.fetch_vouchers(company.name, from_date, to_date)

            # Pre-load cost centres to avoid N+1 in heal loop
            heal_cc_cache = {cc.name: cc for cc in TallyCostCentre.objects.filter(company=company)}

            healed_created = healed_updated = 0
            for voucher_data in vouchers_data:
                try:
                    date_str = voucher_data.get('date', '')
                    if not date_str:
                        continue
                    voucher_date = datetime.strptime(date_str, '%Y%m%d').date()

                    cheque_date_str = voucher_data.get('cheque_date', '')
                    cheque_date = None
                    if cheque_date_str:
                        try:
                            cheque_date = datetime.strptime(cheque_date_str, '%Y%m%d').date()
                        except (ValueError, TypeError):
                            pass

                    voucher, was_created = TallyVoucher.objects.update_or_create(
                        guid=voucher_data.get('guid'),
                        defaults={
                            'company': company, 'date': voucher_date,
                            'voucher_type': voucher_data.get('voucher_type', ''),
                            'voucher_number': voucher_data.get('voucher_number', ''),
                            'party_ledger_name': voucher_data.get('party_ledger_name', ''),
                            'party_name': voucher_data.get('party_name', ''),
                            'party_gstin': voucher_data.get('party_gstin', ''),
                            'party_state': voucher_data.get('party_state', ''),
                            'narration': voucher_data.get('narration', ''),
                            'reference': voucher_data.get('reference', ''),
                            'is_invoice': voucher_data.get('is_invoice', False),
                            'is_cancelled': voucher_data.get('is_cancelled', False),
                            'amount': voucher_data.get('amount', 0),
                            'eway_bill_number': voucher_data.get('eway_bill_number', ''),
                            'payment_mode': voucher_data.get('payment_mode', ''),
                            'cheque_number': voucher_data.get('cheque_number', ''),
                            'cheque_date': cheque_date,
                            'buyer_name': voucher_data.get('buyer_name', ''),
                            'buyer_gstin': voucher_data.get('buyer_gstin', ''),
                            'buyer_state': voucher_data.get('buyer_state', ''),
                            'consignee_name': voucher_data.get('consignee_name', ''),
                            'consignee_gstin': voucher_data.get('consignee_gstin', ''),
                            'raw_xml': voucher_data.get('raw_xml', ''),
                            'billing_month': voucher_data.get('billing_month', ''),
                            'billing_month_date': _parse_billing_month_date(voucher_data.get('billing_month', '')),
                            'need_to_pay': voucher_data.get('need_to_pay', ''),
                            'remark': voucher_data.get('remark', ''),
                            'credit_period': voucher_data.get('credit_period', ''),
                            'transaction_type': voucher_data.get('transaction_type', ''),
                            'utr_number': voucher_data.get('utr_number', ''),
                            'master_id': voucher_data.get('master_id'),
                            'last_synced': timezone.now(),
                        }
                    )

                    TallyVoucherLedgerEntry.objects.filter(voucher=voucher).delete()
                    entries_to_create = []
                    for le_data in voucher_data.get('ledger_entries', []):
                        entries_to_create.append(TallyVoucherLedgerEntry(
                            voucher=voucher,
                            ledger_name=le_data['ledger_name'],
                            amount=Decimal(str(le_data['amount'])),
                            is_debit=le_data['is_debit'],
                            gst_class=le_data.get('gst_class', ''),
                            gst_hsn_code=le_data.get('gst_hsn_code', ''),
                            cgst_rate=Decimal(str(le_data.get('cgst_rate', 0))),
                            sgst_rate=Decimal(str(le_data.get('sgst_rate', 0))),
                            igst_rate=Decimal(str(le_data.get('igst_rate', 0))),
                            cess_rate=Decimal(str(le_data.get('cess_rate', 0))),
                            cgst_amount=Decimal(str(le_data.get('cgst_amount', 0))),
                            sgst_amount=Decimal(str(le_data.get('sgst_amount', 0))),
                            igst_amount=Decimal(str(le_data.get('igst_amount', 0))),
                            cess_amount=Decimal(str(le_data.get('cess_amount', 0))),
                            tds_nature_of_payment=le_data.get('tds_nature_of_payment', ''),
                            tds_section=le_data.get('tds_section', ''),
                            tds_amount=Decimal(str(le_data.get('tds_amount', 0))),
                        ))
                    created_entries = TallyVoucherLedgerEntry.objects.bulk_create(entries_to_create)
                    ledger_entries_map = {le.ledger_name: le for le in created_entries}

                    voucher_cc_name = voucher_data.get('cost_centre_name', '')
                    if voucher_cc_name and voucher_cc_name.strip():
                        party_le = ledger_entries_map.get(voucher_data.get('party_ledger_name', ''))
                        cc = heal_cc_cache.get(voucher_cc_name)
                        if party_le and cc:
                            TallyVoucherCostCentreAllocation.objects.create(
                                ledger_entry=party_le, cost_centre=cc,
                                cost_centre_name=voucher_cc_name, amount=abs(party_le.amount)
                            )

                    # Bill references
                    bill_refs_data = voucher_data.get('bill_references', [])
                    if bill_refs_data:
                        bill_refs_to_create = []
                        for br in bill_refs_data:
                            le = ledger_entries_map.get(br.get('ledger_name', ''))
                            if le:
                                bill_refs_to_create.append(TallyBillReference(
                                    ledger_entry=le,
                                    bill_name=br['bill_name'],
                                    bill_type=br.get('bill_type', ''),
                                    amount=Decimal(str(br.get('amount', 0))),
                                ))
                        if bill_refs_to_create:
                            TallyBillReference.objects.bulk_create(bill_refs_to_create)

                    if was_created:
                        healed_created += 1
                    else:
                        healed_updated += 1
                except Exception as e:
                    logger.error(f"[TallySync] verify_and_heal: failed to save voucher "
                                 f"{voucher_data.get('voucher_number', 'unknown')}: {e}")

            db_count_after = TallyVoucher.objects.filter(
                company=company, date__gte=fd, date__lte=td
            ).count()
            remaining_gap = tally_count - db_count_after
            if remaining_gap <= 0:
                logger.info(f"[TallySync] verify_and_heal HEALED ✓ {company.name} {from_date}-{to_date}: "
                            f"gap={gap} fixed, DB now={db_count_after}")
            else:
                logger.warning(f"[TallySync] verify_and_heal PARTIAL {company.name} {from_date}-{to_date}: "
                               f"gap was {gap}, still {remaining_gap} missing after heal")
            return {
                'tally_count': tally_count, 'db_count': db_count_after,
                'gap': remaining_gap, 'healed': True,
                'original_gap': gap,
            }
        except Exception as e:
            logger.error(f"[TallySync] verify_and_heal HEAL FAILED {company.name}: {e}")
            return {'tally_count': tally_count, 'db_count': db_count, 'gap': gap, 'healed': False, 'heal_error': str(e)}

    def sync_vouchers_incremental(self, company: TallyCompany, buffer_days: int = 7,
                                   triggered_by_user=None, scheduled_job_id=None) -> Dict:
        """Incremental voucher sync: fetches from last synced voucher date minus buffer.

        Uses the latest voucher date in DB as the starting point, subtracts
        buffer_days to catch late entries/modifications, and syncs up to today.
        If no vouchers exist yet, falls back to full sync from April 2023.

        Args:
            company: TallyCompany instance
            buffer_days: Days to overlap for catching modifications (default: 7)
            triggered_by_user: Username of user who triggered the sync
            scheduled_job_id: ID of the scheduled job
        """
        latest_voucher = TallyVoucher.objects.filter(
            company=company
        ).order_by('-date').values_list('date', flat=True).first()

        today = timezone.now().date()

        if latest_voucher:
            from_date = latest_voucher - timedelta(days=buffer_days)
        else:
            from_date = datetime(2023, 4, 1).date()

        from_str = from_date.strftime('%Y%m%d')
        to_str = today.strftime('%Y%m%d')

        logger.info(f"[TallySync] Incremental sync for {company.name}: {from_date} to {today}")
        return self.sync_vouchers(
            company, from_str, to_str,
            triggered_by_user=triggered_by_user,
            scheduled_job_id=scheduled_job_id,
        )

