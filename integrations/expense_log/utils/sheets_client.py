"""
Google Sheets API client for reading expense data.
Handles authentication, API calls, and data parsing.
"""
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

from .sheets_auth import SheetsOAuthManager
from .encryption import ExpenseLogEncryption

logger = logging.getLogger(__name__)


class SheetsAPIClient:
    """Wrapper for Google Sheets API operations"""

    def __init__(self, token_model):
        """
        Initialize with GoogleSheetsToken model instance.

        Args:
            token_model: integrations.expense_log.models.GoogleSheetsToken instance
        """
        self.token_model = token_model
        self.service = None

    def _get_service(self):
        """
        Build Google Sheets API service with authenticated credentials.

        Returns:
            googleapiclient.discovery.Resource
        """
        if self.service:
            return self.service

        try:
            # Decrypt token
            decrypted_token = self.token_model.get_decrypted_token()

            # Refresh if needed
            refreshed_token = SheetsOAuthManager.refresh_token_if_needed(decrypted_token)

            # Update DB if token was refreshed
            if refreshed_token != decrypted_token:
                encrypted_token = ExpenseLogEncryption.encrypt(refreshed_token)
                self.token_model.encrypted_token = encrypted_token
                self.token_model.save(update_fields=['encrypted_token', 'updated_at'])

            # Get credentials
            credentials = SheetsOAuthManager.get_credentials_from_token(refreshed_token)

            # Build service
            self.service = build('sheets', 'v4', credentials=credentials)
            return self.service

        except Exception as e:
            logger.error(f"Failed to build Sheets API service: {e}")
            raise

    def get_sheet_data(self, range_name=None):
        """
        Read data from Google Sheet.

        Args:
            range_name: Optional A1 notation range (e.g., 'Sheet1!A1:Z1000')
                       If None, uses token's sheet_name with auto-detection

        Returns:
            list: List of rows, where each row is a list of cell values
        """
        try:
            service = self._get_service()

            # Build range
            if not range_name:
                range_name = self.token_model.sheet_name

            # Read sheet
            result = service.spreadsheets().values().get(
                spreadsheetId=self.token_model.sheet_id,
                range=range_name,
                valueRenderOption='UNFORMATTED_VALUE',  # Get raw values
                dateTimeRenderOption='SERIAL_NUMBER'     # Get dates as numbers
            ).execute()

            values = result.get('values', [])
            logger.info(f"Read {len(values)} rows from sheet {self.token_model.sheet_id}")
            return values

        except HttpError as e:
            logger.error(f"Google Sheets API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to read sheet data: {e}")
            raise

    def get_sheet_metadata(self):
        """
        Get sheet metadata (title, tab names, etc.).

        Returns:
            dict: Sheet metadata
        """
        try:
            service = self._get_service()

            result = service.spreadsheets().get(
                spreadsheetId=self.token_model.sheet_id
            ).execute()

            return {
                'title': result.get('properties', {}).get('title', ''),
                'sheets': [
                    {
                        'title': sheet.get('properties', {}).get('title', ''),
                        'sheet_id': sheet.get('properties', {}).get('sheetId', 0),
                        'index': sheet.get('properties', {}).get('index', 0)
                    }
                    for sheet in result.get('sheets', [])
                ]
            }

        except HttpError as e:
            logger.error(f"Failed to get sheet metadata: {e}")
            raise

    def test_connection(self):
        """
        Test if connection to sheet is working.

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            metadata = self.get_sheet_metadata()
            return (True, f"Connected to '{metadata['title']}'")
        except Exception as e:
            return (False, str(e))

    @staticmethod
    def parse_rows_to_expenses(rows, header_row_index=0):
        """
        Parse raw sheet rows into expense dictionaries.

        Handles duplicate column names by tracking which section they belong to
        (Transport, Operation, Stationary, Other).

        Args:
            rows: List of rows from get_sheet_data()
            header_row_index: Index of header row (default: 0)

        Returns:
            list: List of expense dictionaries with column names as keys
        """
        if not rows or len(rows) <= header_row_index:
            return []

        headers = rows[header_row_index]
        data_rows = rows[header_row_index + 1:]

        # Track which section we're in to handle duplicate column names
        # Section markers: Transport, Operation, Stationary, Other
        current_section = None
        section_occurrence = {}  # Track how many times we've seen each column name
        unique_headers = []

        for header in headers:
            header_str = str(header).strip()

            # Detect section changes
            if header_str in ['Transport', 'Operation', 'Stationary', 'Other']:
                current_section = header_str

            # Handle duplicate column names
            if header_str in section_occurrence:
                section_occurrence[header_str] += 1
                # Append section suffix for duplicates
                if current_section:
                    unique_header = f"{header_str}_{current_section}"
                else:
                    unique_header = f"{header_str}_{section_occurrence[header_str]}"
            else:
                section_occurrence[header_str] = 1
                unique_header = header_str

            unique_headers.append(unique_header)

        expenses = []
        for row in data_rows:
            # Pad row if shorter than headers
            padded_row = row + [''] * (len(unique_headers) - len(row))

            # Create expense dict with unique headers
            expense = {
                unique_headers[i]: padded_row[i] if i < len(padded_row) else ''
                for i in range(len(unique_headers))
            }
            expenses.append(expense)

        return expenses
