"""
Callyzer API Client
HTTP client for interacting with Callyzer API v2.1
"""

import requests
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CallyzerAPIClient:
    """
    Callyzer API client with rate limiting and retry logic
    """

    BASE_URL = 'https://api1.callyzer.co/api/v2.1'
    MAX_RETRIES = 3
    RETRY_DELAY = 3  # seconds
    TIMEOUT = 30  # seconds

    def __init__(self, api_key: str):
        """
        Initialize API client with authentication

        Args:
            api_key: Callyzer API Bearer token
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def _make_request(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict]:
        """
        Make POST request to Callyzer API with retry logic

        Args:
            endpoint: API endpoint path (e.g., 'call-log/summary')
            payload: Request payload dictionary

        Returns:
            API response dictionary or None if failed
        """
        url = f"{self.BASE_URL}/{endpoint}"
        attempt = 0
        delay = self.RETRY_DELAY

        while attempt < self.MAX_RETRIES:
            attempt += 1
            logger.debug(f"[Callyzer API] POST {endpoint} (Attempt {attempt}/{self.MAX_RETRIES})")

            try:
                response = self.session.post(
                    url,
                    json=payload,
                    timeout=self.TIMEOUT
                )

                # Check response code
                if response.status_code == 200:
                    logger.debug(f"[Callyzer API] Success: {endpoint}")
                    return response.json()

                elif response.status_code == 403:
                    logger.error(f"[Callyzer API] 403 Forbidden - Invalid or expired API token")
                    logger.error(f"Response: {response.text}")
                    return None

                elif response.status_code == 429:
                    logger.warning(f"[Callyzer API] Rate limit hit (429). Waiting {delay}s...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff

                else:
                    logger.error(f"[Callyzer API] Error {response.status_code}: {response.text}")
                    if attempt >= self.MAX_RETRIES:
                        return None
                    time.sleep(delay)

            except requests.exceptions.Timeout:
                logger.error(f"[Callyzer API] Request timeout for {endpoint}")
                if attempt >= self.MAX_RETRIES:
                    return None
                time.sleep(delay)

            except requests.exceptions.RequestException as e:
                logger.error(f"[Callyzer API] Request exception: {e}")
                if attempt >= self.MAX_RETRIES:
                    return None
                time.sleep(delay)

        logger.error(f"[Callyzer API] Failed after {self.MAX_RETRIES} attempts: {endpoint}")
        return None

    def get_call_summary(self, call_from: int, call_to: int) -> Optional[Dict]:
        """
        Fetch overall call summary

        Args:
            call_from: Start timestamp (Unix epoch)
            call_to: End timestamp (Unix epoch)

        Returns:
            Summary data or None
        """
        payload = {"call_from": call_from, "call_to": call_to}
        response = self._make_request('call-log/summary', payload)

        if response and 'result' in response:
            return response['result']
        return None

    def get_employee_summary(self, call_from: int, call_to: int,
                            page_no: int = 1, page_size: int = 100) -> List[Dict]:
        """
        Fetch employee summary with pagination

        Args:
            call_from: Start timestamp
            call_to: End timestamp
            page_no: Page number (1-indexed)
            page_size: Records per page

        Returns:
            List of employee records
        """
        payload = {
            "call_from": call_from,
            "call_to": call_to,
            "page_no": page_no,
            "page_size": page_size
        }

        response = self._make_request('call-log/employee-summary', payload)

        if response and 'result' in response:
            return response['result']
        return []

    def get_call_analysis(self, call_from: int, call_to: int) -> Optional[Dict]:
        """
        Fetch call analysis data

        Args:
            call_from: Start timestamp
            call_to: End timestamp

        Returns:
            Analysis data or None
        """
        payload = {"call_from": call_from, "call_to": call_to}
        response = self._make_request('call-log/analysis', payload)

        if response and 'result' in response:
            return response['result']
        return None

    def get_never_attended(self, call_from: int, call_to: int,
                          page_no: int = 1, page_size: int = 100) -> List[Dict]:
        """
        Fetch never attended calls with pagination

        Args:
            call_from: Start timestamp
            call_to: End timestamp
            page_no: Page number
            page_size: Records per page

        Returns:
            List of never attended call records
        """
        payload = {
            "call_from": call_from,
            "call_to": call_to,
            "page_no": page_no,
            "page_size": page_size
        }

        response = self._make_request('call-log/never-attended', payload)

        if response and 'result' in response:
            return response['result']
        return []

    def get_not_picked_up(self, call_from: int, call_to: int,
                         page_no: int = 1, page_size: int = 100) -> List[Dict]:
        """
        Fetch not picked up by client calls with pagination

        Args:
            call_from: Start timestamp
            call_to: End timestamp
            page_no: Page number
            page_size: Records per page

        Returns:
            List of not picked up call records
        """
        payload = {
            "call_from": call_from,
            "call_to": call_to,
            "page_no": page_no,
            "page_size": page_size
        }

        response = self._make_request('call-log/not-pickup-by-client', payload)

        if response and 'result' in response:
            return response['result']
        return []

    def get_unique_clients(self, call_from: int, call_to: int,
                          page_no: int = 1, page_size: int = 100) -> List[Dict]:
        """
        Fetch unique clients with pagination

        Args:
            call_from: Start timestamp
            call_to: End timestamp
            page_no: Page number
            page_size: Records per page

        Returns:
            List of unique client records
        """
        payload = {
            "call_from": call_from,
            "call_to": call_to,
            "page_no": page_no,
            "page_size": page_size
        }

        response = self._make_request('call-log/unique-clients', payload)

        if response and 'result' in response:
            return response['result']
        return []

    def get_hourly_analytics(self, call_from: int, call_to: int,
                            working_hour_from: str = '09:00',
                            working_hour_to: str = '20:00') -> List[Dict]:
        """
        Fetch hourly analytics

        Args:
            call_from: Start timestamp
            call_to: End timestamp
            working_hour_from: Working hours start (HH:MM)
            working_hour_to: Working hours end (HH:MM)

        Returns:
            List of hourly analytics
        """
        payload = {
            "call_from": call_from,
            "call_to": call_to,
            "working_hour_from": working_hour_from,
            "working_hour_to": working_hour_to
        }

        response = self._make_request('call-log/hourly-analytics', payload)

        if response and 'result' in response:
            data = response['result']
            # Handle both array and dict with 'data' key
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'data' in data:
                return data['data']
        return []

    def get_daily_analytics(self, call_from: int, call_to: int,
                           working_hour_from: str = '09:00',
                           working_hour_to: str = '20:00') -> List[Dict]:
        """
        Fetch daily analytics

        Args:
            call_from: Start timestamp
            call_to: End timestamp
            working_hour_from: Working hours start (HH:MM)
            working_hour_to: Working hours end (HH:MM)

        Returns:
            List of daily analytics
        """
        payload = {
            "call_from": call_from,
            "call_to": call_to,
            "working_hour_from": working_hour_from,
            "working_hour_to": working_hour_to
        }

        response = self._make_request('call-log/daywise-analytics', payload)

        if response and 'result' in response:
            data = response['result']
            # Handle both array and dict with 'data' key
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'data' in data:
                return data['data']
        return []

    def get_call_history(self, call_from: int, call_to: int,
                        page_no: int = 1, page_size: int = 100) -> List[Dict]:
        """
        Fetch call history with pagination

        Args:
            call_from: Start timestamp
            call_to: End timestamp
            page_no: Page number
            page_size: Records per page

        Returns:
            List of call history records
        """
        payload = {
            "call_from": call_from,
            "call_to": call_to,
            "page_no": page_no,
            "page_size": page_size
        }

        response = self._make_request('call-log/history', payload)

        if response and 'result' in response:
            return response['result']
        return []

    def fetch_all_paginated(self, endpoint_method, call_from: int, call_to: int,
                           page_size: int = 100, progress_callback=None, **kwargs) -> List[Dict]:
        """
        Fetch all pages from a paginated endpoint

        Args:
            endpoint_method: API method to call (e.g., self.get_employee_summary)
            call_from: Start timestamp
            call_to: End timestamp
            page_size: Records per page
            progress_callback: Optional callable(page_no, total_records) called after each page
            **kwargs: Additional arguments for the endpoint

        Returns:
            Combined list of all records from all pages
        """
        all_records = []
        page_no = 1
        has_more = True

        while has_more:
            logger.debug(f"Fetching page {page_no} (page_size={page_size})")

            records = endpoint_method(
                call_from=call_from,
                call_to=call_to,
                page_no=page_no,
                page_size=page_size,
                **kwargs
            )

            if records:
                all_records.extend(records)
                logger.debug(f"Page {page_no}: {len(records)} records. Total so far: {len(all_records)}")

                if progress_callback:
                    try:
                        progress_callback(page_no, len(all_records))
                    except Exception:
                        pass

                # Check if we got a full page (more pages likely exist)
                if len(records) < page_size:
                    has_more = False
                else:
                    page_no += 1
                    time.sleep(2)  # Rate limiting between pages
            else:
                has_more = False

        logger.info(f"Fetched total {len(all_records)} records across {page_no} pages")
        return all_records

    def test_connection(self, call_from: int, call_to: int) -> bool:
        """
        Test API connection and token validity

        Args:
            call_from: Start timestamp
            call_to: End timestamp

        Returns:
            True if connection successful, False otherwise
        """
        logger.info("[Callyzer API] Testing connection...")
        response = self.get_call_summary(call_from, call_to)

        if response is not None:
            logger.info("[Callyzer API] ✓ Connection successful")
            return True
        else:
            logger.error("[Callyzer API] ✗ Connection failed")
            return False


def get_unix_timestamp_range(days_back: int = 150) -> tuple:
    """
    Get Unix timestamp range for the last N days

    Args:
        days_back: Number of days to go back from today

    Returns:
        Tuple of (call_from, call_to) Unix timestamps
    """
    now = datetime.now()
    to_date = datetime(now.year, now.month, now.day, 23, 59, 59)
    from_date = to_date - timedelta(days=days_back)
    from_date = datetime(from_date.year, from_date.month, from_date.day, 0, 0, 0)

    call_from = int(from_date.timestamp())
    call_to = int(to_date.timestamp())

    return call_from, call_to
