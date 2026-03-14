"""
Sync engine for manual transport Google Sheet → ExpenseRecord.

Column mapping:
    Month               → service_month
    Operation Personnel → submitted_by
    Date                → timestamp
    Client Name         → client_name
    Client              → client (if field exists)
    Transporter Name    → transporter_name
    From                → from_address (if field exists)
    To                  → to_address (if field exists)
    Vehicle Type (MT)   → transport_type (if field exists)
    Vehicle No.         → vehicle_no (if field exists)
    Invoice No.         → invoice_no (if field exists)
    Charges@GW          → charges_at_gw
    Charges@Client      → charges_at_client
    Remark              → remark (if field exists)
    Warai Charges       → warai_charges (if field exists)
    Labour Charges      → labour_charges (if field exists)

Fixed values:
    nature_of_expense = 'Transport'
    approval_status   = 'Approved'
    unique_expense_number = 'TS-{md5hash[:12]}'
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from django.utils import timezone as django_timezone

from integrations.expense_log.models import ExpenseRecord, GoogleSheetsToken
from integrations.expense_log.utils.sheets_client import SheetsAPIClient
from .models import TransportSheetConfig

logger = logging.getLogger(__name__)

# Header (lowercase stripped) → ExpenseRecord field name
COLUMN_MAP = {
    'blank': '_skip',
    'month': 'service_month',
    'operation personnel': 'submitted_by',
    'date': '_date',
    'client name': 'client_name',
    'client': 'client',
    'transporter name': 'transporter_name',
    'from': 'from_address',
    'to': 'to_address',
    'vehicle type (mt)': 'transport_type',
    'vehicle no.': 'vehicle_no',
    'invoice no.': 'invoice_no',
    'charges@gw': 'charges_at_gw',
    'charges@client': 'charges_at_client',
    'margin %': '_skip',
    'remark': 'remark',
    'warai charges': 'warai_charges',
    'labour charges': 'labour_charges',
}

DECIMAL_FIELDS = {'charges_at_gw', 'charges_at_client', 'warai_charges', 'labour_charges'}

# Fields that must exist on ExpenseRecord — check at runtime and skip missing ones
OPTIONAL_FIELDS = {'client', 'from_address', 'to_address', 'transport_type', 'vehicle_no',
                   'invoice_no', 'remark', 'warai_charges', 'labour_charges'}


def _parse_amount(value):
    """Parse amount string like '1,815.00' or '₹1815' → Decimal or None."""
    if value is None or str(value).strip() == '':
        return None
    cleaned = str(value).replace(',', '').replace('₹', '').replace('%', '').strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_date(value):
    """Parse date string or Google Sheets serial number → timezone-aware datetime."""
    if value is None or str(value).strip() == '':
        return django_timezone.now()

    # Handle numeric (Google Sheets serial date)
    try:
        serial = float(str(value).strip())
        dt = datetime(1899, 12, 30) + timedelta(days=serial)
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass

    # String date formats
    for fmt in ('%d/%b/%Y', '%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y', '%d %b %Y'):
        try:
            dt = datetime.strptime(str(value).strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    logger.warning(f"Could not parse date: {value!r}, using now()")
    return django_timezone.now()


def _make_unique_key(client_name, date_str, vehicle_no, charges_at_gw):
    """Generate TS-{md5[:12]} deduplication key."""
    key_str = '|'.join([
        str(client_name or ''),
        str(date_str or ''),
        str(vehicle_no or ''),
        str(charges_at_gw or ''),
    ])
    md5 = hashlib.md5(key_str.encode()).hexdigest()[:12]
    return f'TS-{md5}'


# Cache of valid ExpenseRecord fields
_EXPENSE_RECORD_FIELDS = None


def _get_expense_record_fields():
    global _EXPENSE_RECORD_FIELDS
    if _EXPENSE_RECORD_FIELDS is None:
        _EXPENSE_RECORD_FIELDS = {f.name for f in ExpenseRecord._meta.get_fields()}
    return _EXPENSE_RECORD_FIELDS


class TransportSheetSyncEngine:
    """
    Reads transport sheet rows and upserts into ExpenseRecord.
    Uses the GoogleSheetsToken connected via OAuth (token_id stored in TransportSheetConfig).
    """

    def __init__(self, triggered_by_user=None):
        self.config = TransportSheetConfig.load()
        self.triggered_by_user = triggered_by_user or 'system'
        self.stats = {
            'total_rows': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
        }

    def sync(self):
        """Main sync entry point. Returns stats dict."""
        if not self.config.token_id:
            raise ValueError(
                "Transport sheet not configured. "
                "Connect the sheet via OAuth in Expense Log settings first, "
                "then set the token_id in Transport Sheet Settings."
            )

        try:
            token = GoogleSheetsToken.objects.get(pk=self.config.token_id)
        except GoogleSheetsToken.DoesNotExist:
            raise ValueError(f"GoogleSheetsToken with id={self.config.token_id} not found.")

        if not token.is_active:
            raise ValueError(f"GoogleSheetsToken {self.config.token_id} is inactive.")

        client = SheetsAPIClient(token)

        # Fetch all data from sheet — start from row 2 (row 1 is type hints, row 2 is headers)
        range_name = f"{token.sheet_name}!A2:Z10000"
        rows = client.get_sheet_data(range_name)

        if not rows or len(rows) < 2:
            logger.info("Transport sheet: no data rows found")
            self._update_config_stats()
            return self.stats

        # Parse header row (first row of range = sheet row 2)
        headers = [str(h).strip().lower() for h in rows[0]]
        data_rows = rows[1:]

        self.stats['total_rows'] = len(data_rows)
        logger.info(f"Transport sheet: {len(data_rows)} data rows, headers: {headers}")

        for i, row in enumerate(data_rows):
            try:
                self._process_row(row, headers, token)
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"Row {i + 2} error: {e}", exc_info=True)

        self._update_config_stats()
        logger.info(f"Transport sheet sync complete: {self.stats}")
        return self.stats

    def _process_row(self, row, headers, token):
        """Parse one sheet row and upsert into ExpenseRecord."""
        valid_fields = _get_expense_record_fields()

        # Build raw dict from headers
        raw = {}
        for col_idx, header in enumerate(headers):
            value = str(row[col_idx]).strip() if col_idx < len(row) else ''
            mapped = COLUMN_MAP.get(header)
            if mapped and mapped != '_skip':
                raw[mapped] = value

        # Skip completely empty rows
        if not any(v for v in raw.values()):
            self.stats['skipped'] += 1
            return

        # Skip rows missing both client_name and charges_at_gw
        if not raw.get('client_name') and not raw.get('charges_at_gw'):
            self.stats['skipped'] += 1
            return

        # Parse date
        date_raw = raw.pop('_date', '')
        timestamp = _parse_date(date_raw)
        date_str = timestamp.strftime('%Y-%m-%d')

        # Parse decimal fields
        for field in DECIMAL_FIELDS:
            if field in raw:
                raw[field] = _parse_amount(raw[field])

        # Build unique key
        uen = _make_unique_key(
            raw.get('client_name', ''),
            date_str,
            raw.get('vehicle_no', ''),
            raw.get('charges_at_gw', ''),
        )

        # Build defaults dict — only include fields that exist on ExpenseRecord
        defaults = {
            'token': token,
            'timestamp': timestamp,
            'nature_of_expense': 'Transport',
            'approval_status': 'Approved',
        }

        # Map optional fields
        field_mapping = {
            'service_month': 'service_month',
            'submitted_by': 'submitted_by',
            'client_name': 'client_name',
            'client': 'client',
            'transporter_name': 'transporter_name',
            'from_address': 'from_address',
            'to_address': 'to_address',
            'transport_type': 'transport_type',
            'vehicle_no': 'vehicle_no',
            'invoice_no': 'invoice_no',
            'charges_at_gw': 'charges_at_gw',
            'charges_at_client': 'charges_at_client',
            'remark': 'remark',
            'warai_charges': 'warai_charges',
            'labour_charges': 'labour_charges',
        }

        # Field max_length limits from ExpenseRecord
        _max_lengths = {
            'transport_type': 100,
            'vehicle_no': 100,
            'invoice_no': 100,
        }

        for raw_key, model_field in field_mapping.items():
            if model_field in valid_fields and raw_key in raw:
                val = raw[raw_key]
                limit = _max_lengths.get(model_field)
                if limit and isinstance(val, str) and len(val) > limit:
                    val = val[:limit]
                defaults[model_field] = val

        # Store source info in raw_data
        defaults['raw_data'] = {'_source': 'transport_sheet', **{k: str(v) for k, v in raw.items() if v is not None}}

        obj, created = ExpenseRecord.objects.update_or_create(
            unique_expense_number=uen,
            defaults=defaults,
        )

        if created:
            self.stats['created'] += 1
        else:
            self.stats['updated'] += 1

    def _update_config_stats(self):
        self.config.last_synced_at = django_timezone.now()
        self.config.last_sync_rows = self.stats['total_rows']
        self.config.save(update_fields=['last_synced_at', 'last_sync_rows'])
