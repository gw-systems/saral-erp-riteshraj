"""
Expense Log sync engine - syncs data from Google Sheets to ERP.
Handles incremental and full sync operations with progress tracking.
"""
from django.core.cache import cache
from django.utils import timezone as django_timezone
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import logging
import time

from .models import GoogleSheetsToken, ExpenseRecord, UserNameMapping
from .utils.sheets_client import SheetsAPIClient
from integrations.models import SyncLog

logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 86400  # 24 hours
PROGRESS_UPDATE_INTERVAL = 5  # Update progress every 5 records
STOP_CHECK_INTERVAL = 10  # Check for stop request every 10 records


class ExpenseLogSyncEngine:
    """Handles syncing expense data from Google Sheets"""

    def __init__(self, token_id, sync_type='incremental', batch_log=None, triggered_by_user=None, scheduled_job_id=None):
        """
        Initialize sync engine.

        Args:
            token_id: GoogleSheetsToken primary key
            sync_type: 'incremental' or 'full'
            batch_log: Existing SyncLog batch object (optional)
            triggered_by_user: Username of user who triggered the sync (optional)
        """
        self.token_id = token_id
        self.sync_type = sync_type
        self.token = GoogleSheetsToken.objects.get(pk=token_id)
        self.client = SheetsAPIClient(self.token)
        self.cache_key = f'expense_log_sync_progress_{token_id}'
        self.triggered_by_user = triggered_by_user

        # Stats
        self.stats = {
            'total_rows': 0,
            'processed': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None,
        }

        # Progress tracking
        self.activity_log = []
        self.status = 'running'

        # Unified SyncLog batch tracking
        if batch_log:
            self.batch_log = batch_log
        else:
            # Create new batch log
            sync_type_value = 'expense_log_full' if sync_type == 'full' else 'expense_log_incremental'
            self.batch_log = SyncLog.objects.create(
                integration='expense_log',
                sync_type=sync_type_value,
                log_kind='batch',
                status='running',
                triggered_by_user=triggered_by_user or f'Token {token_id}',
                overall_progress_percent=0,
                scheduled_job_id=scheduled_job_id,
            )

    def _cleanup_stale_syncs(self):
        """
        Mark stale sync logs as stopped (running > 10 minutes).
        Prevents race conditions where crashed syncs block new ones.
        """
        from django.db import transaction

        stale_threshold = django_timezone.now() - timedelta(minutes=10)
        sync_type_value = 'expense_log_full' if self.sync_type == 'full' else 'expense_log_incremental'

        with transaction.atomic():
            stale_syncs = SyncLog.objects.select_for_update(skip_locked=True).filter(
                integration='expense_log',
                sync_type=sync_type_value,
                status='running',
                started_at__lt=stale_threshold
            )

            count = stale_syncs.count()
            if count > 0:
                logger.warning(f"[ExpenseLog] Found {count} stale sync(s) for token {self.token_id}, marking as stopped")
                stale_syncs.update(
                    status='stopped',
                    completed_at=django_timezone.now(),
                    error_message='Sync exceeded 10-minute threshold (likely crashed)'
                )

    def sync(self):
        """
        Main sync method. Reads sheet data and creates/updates ExpenseRecord entries.

        Returns:
            dict: Sync statistics
        """
        # Cleanup stale syncs first (prevent race conditions)
        self._cleanup_stale_syncs()

        self.stats['start_time'] = django_timezone.now()
        self._update_progress(0, "Starting sync...")
        self._log_server(f'Starting {self.sync_type} sync for Google Sheets token {self.token_id}', 'INFO')

        # Log sync start
        self._log_operation('INFO', 'Sync Start', f'Starting {self.sync_type} sync for token {self.token_id}')

        try:
            # Step 1: Connect to Google Sheets
            self._log_activity("Connecting to Google Sheets...")
            self._log_server('Connecting to Google Sheets API...', 'INFO')
            self._log_operation('INFO', 'Connect', 'Establishing connection to Google Sheets API')
            self._update_batch_progress(5, 'Connecting to Google Sheets')

            start_time = django_timezone.now()
            rows = self.client.get_sheet_data()
            duration_ms = int((django_timezone.now() - start_time).total_seconds() * 1000)

            self._log_server(f'✅ Connected to Google Sheets successfully ({duration_ms}ms)', 'SUCCESS')
            self._log_operation('SUCCESS', 'Connect', f'Connected to Google Sheets successfully', duration_ms=duration_ms)

            if not rows:
                self._log_activity("No data found in sheet")
                self._log_server('Sheet is empty or contains no valid data', 'WARNING')
                self._log_operation('INFO', 'No Data', 'Sheet is empty or contains no valid data')
                self._update_progress(100, "Completed - no data found")
                self._finalize_batch('completed', 'No data found in sheet')
                return self.stats

            # Step 2: Parse rows
            self._log_activity("Parsing expense data...")
            self._log_server(f'Parsing {len(rows)} rows from sheet...', 'INFO')
            self._log_operation('INFO', 'Parse', f'Parsing {len(rows)} rows from sheet')
            self._update_batch_progress(10, 'Parsing sheet data')

            start_time = django_timezone.now()
            expenses = SheetsAPIClient.parse_rows_to_expenses(rows)
            duration_ms = int((django_timezone.now() - start_time).total_seconds() * 1000)

            self.stats['total_rows'] = len(expenses)
            self._log_activity(f"Found {len(expenses)} expense records in sheet")
            self._log_server(f'Parsed {len(expenses)} expense records ({duration_ms}ms)', 'SUCCESS')
            self._log_operation('SUCCESS', 'Parse', f'Parsed {len(expenses)} expense records',
                              duration_ms=duration_ms, details={'total_rows': len(expenses)})

            # Step 3: Process each expense
            self._update_batch_progress(15, 'Processing expense records')
            self._log_server(f'Starting to process {len(expenses)} expense records...', 'INFO')
            self._log_operation('INFO', 'Process Start', f'Starting to process {len(expenses)} expense records')

            for idx, expense_data in enumerate(expenses, 1):
                try:
                    # Check for stop request every STOP_CHECK_INTERVAL records
                    if idx % STOP_CHECK_INTERVAL == 0:
                        self.batch_log.refresh_from_db(fields=['stop_requested'])
                        if self.batch_log.stop_requested:
                            logger.info(f"[ExpenseLog] Sync {self.batch_log.id} stopped by user request at record {idx}/{len(expenses)}")
                            self._log_server(f'⏹️ Sync stopped by user at record {idx}/{len(expenses)}', 'WARNING')
                            self._log_operation('WARNING', 'Sync Stopped', f'Sync stopped by user at record {idx}/{len(expenses)}')
                            self.status = 'stopped'
                            self._finalize_batch('stopped', f'Stopped by user after processing {idx-1} records')
                            return self.stats

                    self._process_expense(expense_data)
                    self.stats['processed'] += 1

                    # Update progress periodically
                    if idx % PROGRESS_UPDATE_INTERVAL == 0:
                        progress = int((idx / len(expenses)) * 100)
                        overall_progress = 15 + int(progress * 0.7)  # 15-85% range
                        self._update_progress(
                            progress,
                            f"Processing record {idx}/{len(expenses)}..."
                        )
                        self._update_batch_progress(
                            overall_progress,
                            f'Processing records: {idx}/{len(expenses)}'
                        )

                        # Log milestones
                        if idx in [100, 500, 1000, 5000, 10000] or (idx % 1000 == 0 and idx > 0):
                            milestone_msg = f'Processed {idx} records - {self.stats["created"]} created, {self.stats["updated"]} updated'
                            self._log_server(milestone_msg, 'INFO')
                            self._log_operation('INFO', 'Milestone', milestone_msg)

                except Exception as e:
                    self.stats['errors'] += 1
                    error_msg = f"Error processing expense at row {idx}: {str(e)[:100]}"
                    logger.error(error_msg)
                    self._log_activity(error_msg)
                    self._log_server(f'❌ Error at row {idx}: {str(e)[:100]}', 'ERROR')
                    self._log_operation('ERROR', 'Process Error',
                                      f'Failed to process expense at row {idx}: {str(e)}',
                                      details={'row_index': idx, 'error': str(e)})

            # Step 4: Complete sync
            self.stats['end_time'] = django_timezone.now()
            self.status = 'completed'

            completion_msg = (
                f"Sync completed: {self.stats['created']} created, "
                f"{self.stats['updated']} updated, {self.stats['errors']} errors"
            )

            self._update_progress(100, "Sync completed successfully")
            self._log_activity(completion_msg)
            self._log_server(f'✅ {completion_msg}', 'SUCCESS')
            self._log_operation('SUCCESS', 'Sync Complete', completion_msg,
                              details={
                                  'total_rows': self.stats['total_rows'],
                                  'created': self.stats['created'],
                                  'updated': self.stats['updated'],
                                  'skipped': self.stats['skipped'],
                                  'errors': self.stats['errors']
                              })

            self._finalize_batch('completed', completion_msg)

        except Exception as e:
            self.status = 'failed'
            self.stats['end_time'] = django_timezone.now()
            error_msg = f"Sync failed: {str(e)}"
            self._log_activity(error_msg)
            self._log_server(f'🔥 Sync failed: {str(e)}', 'CRITICAL')
            logger.error(error_msg, exc_info=True)
            self._update_progress(0, error_msg)

            self._log_operation('ERROR', 'Sync Failed', error_msg,
                              details={'error_type': type(e).__name__, 'error': str(e)})
            self._finalize_batch('failed', error_msg)
            raise

        return self.stats

    def _process_expense(self, expense_data):
        """
        Create or update ExpenseRecord from parsed sheet row.

        Args:
            expense_data: dict with column names as keys
        """
        # Extract unique expense number (required)
        uen = expense_data.get('Unique Expense Number', '').strip()
        if not uen:
            self.stats['skipped'] += 1
            return  # Skip rows without UEN

        # Parse timestamp
        timestamp = self._parse_timestamp(expense_data.get('Timestamp', ''))
        if not timestamp:
            self.stats['skipped'] += 1
            return  # Skip rows without valid timestamp

        # Get or create expense record
        expense, created = ExpenseRecord.objects.update_or_create(
            unique_expense_number=uen,
            defaults={
                'token': self.token,
                'timestamp': timestamp,
                'submitted_by': expense_data.get('Submitted By', ''),
                'email_address': expense_data.get('Email Address', ''),
                'client_name': expense_data.get('Client Name', ''),
                'client': expense_data.get('Client', ''),
                'service_month': expense_data.get('Service Month', ''),
                'nature_of_expense': expense_data.get('Nature of Expense', ''),
                'amount': self._parse_amount(expense_data.get('Amount', '')),
                'payment_method': expense_data.get('Payment Method', ''),
                'expenses_borne_by': expense_data.get('Expenses Borne By', ''),
                'remark': expense_data.get('Remark', ''),
                'approval_status': expense_data.get('Approval Status', 'Pending'),

                # Transport fields (using section-specific column names from updated parser)
                'transport': expense_data.get('Transport', ''),
                'transport_type': expense_data.get('Select your Transport Type', ''),
                'transporter_name': expense_data.get('Transporter Name', ''),
                'from_address': expense_data.get('From Address', ''),
                'to_address': expense_data.get('To Address', ''),
                'vehicle_no': expense_data.get('Vehicle No.', ''),
                'invoice_no': expense_data.get('Invoice No', ''),
                'charges_at_gw': self._parse_amount(expense_data.get('Charges@GW', '')),
                'charges_at_client': self._parse_amount(expense_data.get('Charges@Client', '')),
                'unloading_box_expense': self._parse_amount(expense_data.get('Unloading Box Expense', '')),
                'box_count': self._parse_int(expense_data.get('Box Count', '')),
                'warai_charges': self._parse_amount(expense_data.get('Warai Charges', '')),
                'labour_charges': self._parse_amount(expense_data.get('Labour Charges', '')),
                'pod_hard_copy': expense_data.get('POD Hard Copy', ''),
                'expense_paid_by_transport': expense_data.get('Expense Paid By_Transport', expense_data.get('Expense Paid By', '')),
                'mention_other_transport': expense_data.get('Mention Other OR Remarks_Transport', expense_data.get('Mention Other OR Remarks', '')),
                'payment_summary_invoice': expense_data.get('Payment Summary (Invoice)', ''),
                'transport_bill': expense_data.get('Transport Bill', ''),
                'upload_invoice_transport_2': expense_data.get('Upload Invoice 2_Transport', expense_data.get('Upload Invoice 2', '')),

                # Operation fields (using section-suffixed names from parser)
                'operation': expense_data.get('Operation', ''),
                'operation_expense_type': expense_data.get('Select your Operational Expense Type', ''),
                'operation_expense_amount': self._parse_amount(expense_data.get('Expense Amount_Operation', expense_data.get('Expense Amount', ''))),
                'expense_paid_by_operation': expense_data.get('Expense Paid By_Operation', ''),
                'mention_other_operation': expense_data.get('Mention Other OR Remarks_Operation', ''),
                'upload_invoice_operation_1': expense_data.get('Upload Invoice 1_Operation', ''),
                'upload_invoice_operation_2': expense_data.get('Upload Invoice 2_Operation', ''),

                # Stationary fields (using section-suffixed names from parser)
                'stationary': expense_data.get('Stationary', ''),
                'stationary_expense_type': expense_data.get('Select your Stationary Expense Type', ''),
                'stationary_expense_amount': self._parse_amount(expense_data.get('Expense Amount_Stationary', '')),
                'expense_paid_by_stationary': expense_data.get('Expense Paid By_Stationary', ''),
                'mention_other_stationary': expense_data.get('Mention Other OR Remarks_Stationary', ''),
                'upload_invoice_stationary_1': expense_data.get('Upload Invoice 1_Stationary', ''),
                'upload_invoice_stationary_2': expense_data.get('Upload Invoice 2_Stationary', ''),

                # Other expense fields (using section-suffixed names from parser)
                'other': expense_data.get('Other', ''),
                'other_expense_type': expense_data.get('Select your Other Expense Type', ''),
                'other_expense_amount': self._parse_amount(expense_data.get('Expense Amount_Other', '')),
                'expense_paid_by_other': expense_data.get('Expense Paid By_Other', ''),
                'mention_other_remarks': expense_data.get('Mention Other OR Remarks_Other', ''),
                'upload_invoice_other_1': expense_data.get('Upload Invoice 1_Other', ''),
                'upload_invoice_other_2': expense_data.get('Upload Invoice 2_Other', ''),

                # Additional fields
                'entered_in_tally': self._parse_boolean(expense_data.get('Entered in Tally', False)),

                'raw_data': expense_data,  # Store full row as JSON for disambiguation
            }
        )

        if created:
            self.stats['created'] += 1
        else:
            self.stats['updated'] += 1

    def _parse_timestamp(self, value):
        """
        Parse timestamp from various formats and convert to local timezone.

        Args:
            value: String or number from sheet

        Returns:
            datetime or None
        """
        if not value:
            return None

        try:
            # Try ISO format first
            if isinstance(value, str):
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                # Make timezone-aware if naive (assume UTC from Google Sheets)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                # Convert to local timezone (Asia/Kolkata)
                from django.utils import timezone as django_tz
                return dt.astimezone(django_tz.get_current_timezone())

            # Try serial number (Google Sheets date format)
            if isinstance(value, (int, float)):
                # Excel/Sheets epoch: Jan 1, 1900 (but off by 2 days)
                # Google Sheets timestamps are in UTC
                base_date = datetime(1899, 12, 30, tzinfo=timezone.utc)
                dt_utc = base_date + timedelta(days=value)
                # Convert to local timezone (Asia/Kolkata)
                from django.utils import timezone as django_tz
                return dt_utc.astimezone(django_tz.get_current_timezone())

        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{value}': {e}")

        return None

    def _parse_amount(self, value):
        """
        Parse amount from string or number.

        Args:
            value: Amount value from sheet

        Returns:
            Decimal or None
        """
        if not value:
            return None

        try:
            # Remove currency symbols and commas
            if isinstance(value, str):
                value = value.replace('₹', '').replace(',', '').strip()
                if not value:  # Empty after stripping
                    return None

            return Decimal(str(value))
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Failed to parse amount '{value}': {e}")
            return None

    def _parse_int(self, value):
        """
        Parse integer from string or number.

        Args:
            value: Integer value from sheet

        Returns:
            int or None
        """
        if not value:
            return None

        try:
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    return None
            return int(float(value))  # Convert via float to handle "10.0" strings
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse integer '{value}': {e}")
            return None

    def _parse_boolean(self, value):
        """
        Parse boolean from various formats.

        Args:
            value: Boolean value from sheet (Yes/No, True/False, 1/0, checkbox)

        Returns:
            bool
        """
        if isinstance(value, bool):
            return value

        if not value:
            return False

        if isinstance(value, str):
            value_lower = value.strip().lower()
            return value_lower in ['yes', 'true', '1', 'checked', 'y', 't']

        if isinstance(value, (int, float)):
            return bool(value)

        return False

    def _update_progress(self, percentage, message):
        """
        Update sync progress in cache.

        Args:
            percentage: int (0-100)
            message: str status message
        """
        # Get existing progress to preserve server_logs
        existing = cache.get(self.cache_key) or {}
        server_logs = existing.get('server_logs', [])

        progress_data = {
            'status': self.status,
            'progress_percentage': percentage,
            'message': message,
            'stats': self.stats,
            'activity_log': self.activity_log[-20:],  # Last 20 entries
            'server_logs': server_logs,  # Preserve server logs
            'updated_at': django_timezone.now().isoformat(),
        }
        cache.set(self.cache_key, progress_data, CACHE_TIMEOUT)

    def _log_activity(self, message):
        """
        Add entry to activity log.

        Args:
            message: str log message
        """
        entry = {
            'timestamp': django_timezone.now().isoformat(),
            'message': message
        }
        self.activity_log.append(entry)
        logger.info(f"[ExpenseLog Sync {self.token_id}] {message}")

    def _log_server(self, message, level='INFO'):
        """
        Add server log entry visible in UI (similar to tracker.log()).

        Args:
            message: str log message
            level: str log level (DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL)
        """
        # Get current progress
        progress = cache.get(self.cache_key) or {}

        # Prepare timestamp and icon
        timestamp = django_timezone.localtime(django_timezone.now()).strftime('%H:%M:%S')
        level_icon = {
            'DEBUG': '🔍',
            'INFO': 'ℹ️',
            'SUCCESS': '✅',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🔥'
        }.get(level, 'ℹ️')

        log_entry = f'[{timestamp}] {level_icon} {message}'

        # Initialize or append to server_logs
        if 'server_logs' not in progress:
            progress['server_logs'] = []
        progress['server_logs'].append(log_entry)

        # Keep only last 100 entries
        progress['server_logs'] = progress['server_logs'][-100:]

        # Update cache
        cache.set(self.cache_key, progress, CACHE_TIMEOUT)

        # Also log to console
        logger.log(getattr(logging, level, logging.INFO), f"[ExpenseLog] {message}")

    def _log_operation(self, level, operation, message, duration_ms=None, details=None):
        """
        Create an operation-level log entry in unified SyncLog.

        Args:
            level: Log level (DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL)
            operation: Operation name (e.g., 'Connect', 'Parse', 'Process')
            message: Log message
            duration_ms: Operation duration in milliseconds (optional)
            details: Additional details as dict (optional)
        """
        SyncLog.log(
            integration='expense_log',
            sync_type=self.batch_log.sync_type,
            level=level,
            operation=operation,
            message=message,
            details=details or {},
            duration_ms=duration_ms,
            batch=self.batch_log
        )

    def _update_batch_progress(self, percentage, message):
        """
        Update the batch log progress.

        Args:
            percentage: int (0-100)
            message: str status message
        """
        self.batch_log.overall_progress_percent = percentage
        self.batch_log.message = message
        self.batch_log.save(update_fields=['overall_progress_percent', 'message', 'last_updated'])

    def _finalize_batch(self, status, message):
        """
        Finalize the batch log with final status and statistics.

        Args:
            status: Final status ('completed', 'failed', 'stopped', 'partial')
            message: Final message
        """
        self.batch_log.status = status
        self.batch_log.completed_at = django_timezone.now()
        self.batch_log.duration_seconds = int(
            (self.batch_log.completed_at - self.batch_log.started_at).total_seconds()
        )
        self.batch_log.message = message
        self.batch_log.overall_progress_percent = 100 if status == 'completed' else self.batch_log.overall_progress_percent

        # Update record counts
        self.batch_log.total_records_synced = self.stats['processed']
        self.batch_log.records_created = self.stats['created']
        self.batch_log.records_updated = self.stats['updated']
        self.batch_log.errors_count = self.stats['errors']

        # Store detailed results in module_results
        self.batch_log.module_results = {
            'expense_log': {
                'total_rows': self.stats['total_rows'],
                'processed': self.stats['processed'],
                'created': self.stats['created'],
                'updated': self.stats['updated'],
                'skipped': self.stats['skipped'],
                'errors': self.stats['errors'],
            }
        }

        self.batch_log.api_calls_count = self.batch_log.operations.count()
        self.batch_log.save()
        logger.info(f"[ExpenseLog] Batch {self.batch_log.id} finalized with status: {status}")

    @classmethod
    def get_progress(cls, token_id):
        """
        Retrieve sync progress from cache.
        Includes recent operation-level logs from SyncLog.

        Args:
            token_id: GoogleSheetsToken primary key

        Returns:
            dict or None
        """
        from integrations.models import SyncLog
        import logging

        logger = logging.getLogger(__name__)
        cache_key = f'expense_log_sync_progress_{token_id}'
        progress = cache.get(cache_key)

        if not progress:
            return None

        # Enhance with recent operation logs from SyncLog (last 50 entries)
        try:
            # Find active batch log
            batch_log = SyncLog.objects.filter(
                integration='expense_log',
                sync_type__in=['expense_log_full', 'expense_log_incremental'],
                log_kind='batch',
                status__in=['running', 'stopping']
            ).order_by('-started_at').first()

            if batch_log:
                # Get recent operation logs for this batch
                operation_logs = SyncLog.objects.filter(
                    batch=batch_log,
                    log_kind='operation'
                ).order_by('-started_at')[:50]

                # Format as activity log entries
                activity_log = []
                for op_log in reversed(operation_logs):  # Oldest first
                    timestamp = django_timezone.localtime(op_log.started_at).strftime('%H:%M:%S')
                    level_icon = {
                        'DEBUG': '🔍',
                        'INFO': 'ℹ️',
                        'SUCCESS': '✅',
                        'WARNING': '⚠️',
                        'ERROR': '❌',
                        'CRITICAL': '🔥'
                    }.get(op_log.level, '')

                    message = f"{level_icon} {op_log.operation}"
                    if op_log.message:
                        message += f": {op_log.message}"

                    activity_log.append(f"[{timestamp}] {message}")

                # Replace the basic log with detailed operation logs
                if activity_log:
                    progress['activity_log'] = activity_log

                # Add stop_requested status
                progress['stop_requested'] = batch_log.stop_requested
                progress['status'] = batch_log.status

        except Exception as e:
            logger.error(f"Failed to fetch SyncLog entries: {e}")

        # Add UI control states
        status = progress.get('status', 'running')
        progress['can_start'] = status not in ['running', 'stopping']
        progress['can_stop'] = status == 'running'

        # Ensure server_logs exist (fallback to activity_log if not present)
        if 'server_logs' not in progress or not progress['server_logs']:
            if 'activity_log' in progress:
                progress['server_logs'] = progress['activity_log']
            else:
                progress['server_logs'] = []

        return progress

    @classmethod
    def clear_progress(cls, token_id):
        """
        Clear sync progress from cache.

        Args:
            token_id: GoogleSheetsToken primary key
        """
        cache_key = f'expense_log_sync_progress_{token_id}'
        cache.delete(cache_key)

    @classmethod
    def get_running_sync(cls):
        """
        Check if there's already a running sync.

        Returns:
            SyncLog instance or None
        """
        return SyncLog.objects.filter(
            integration='expense_log',
            log_kind='batch',
            status='running'
        ).first()

    @classmethod
    def get_recent_syncs(cls, limit=50):
        """
        Get recent batch sync logs.

        Args:
            limit: Maximum number of logs to retrieve

        Returns:
            QuerySet of SyncLog instances
        """
        return SyncLog.objects.filter(
            integration='expense_log',
            log_kind='batch'
        ).order_by('-started_at')[:limit]
