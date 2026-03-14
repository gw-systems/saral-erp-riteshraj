"""
Parsers for Callyzer API response data
Handles parsing of call_logs JSON field
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, date, time as dt_time

logger = logging.getLogger(__name__)


def parse_call_logs(call_logs_data: Any) -> Optional[Dict]:
    """
    Parse call_logs field from API response
    Handles both JSON string and direct array/object

    Args:
        call_logs_data: Raw call_logs data (string, list, or dict)

    Returns:
        Parsed call log dictionary or None if parsing fails
    """
    if not call_logs_data or call_logs_data == '':
        return None

    try:
        parsed = call_logs_data

        # If it's a string, parse it first
        if isinstance(call_logs_data, str):
            parsed = json.loads(call_logs_data)

        # If it's an array with objects, return the first object
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed[0]  # Return first call log object

        # If it's already an object, return it
        if isinstance(parsed, dict):
            return parsed

        return None

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error parsing call_logs: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing call_logs: {e}")
        return None


def extract_call_date(call_log: Dict) -> Optional[date]:
    """
    Extract call date from parsed call_log

    Args:
        call_log: Parsed call_log dictionary

    Returns:
        date object or None
    """
    if not call_log:
        return None

    # Try different field names
    date_str = call_log.get('call_date') or call_log.get('date') or call_log.get('call_day')

    if not date_str:
        return None

    try:
        # Handle different date formats
        if isinstance(date_str, str):
            # Try common formats
            for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
        elif isinstance(date_str, date):
            return date_str
        elif isinstance(date_str, datetime):
            return date_str.date()

    except Exception as e:
        logger.error(f"Error extracting call date from {date_str}: {e}")

    return None


def extract_call_time(call_log: Dict) -> Optional[dt_time]:
    """
    Extract call time from parsed call_log

    Args:
        call_log: Parsed call_log dictionary

    Returns:
        time object or None
    """
    if not call_log:
        return None

    # Try different field names
    time_str = call_log.get('call_time') or call_log.get('time')

    if not time_str:
        return None

    try:
        # Handle different time formats
        if isinstance(time_str, str):
            # Try common formats
            for fmt in ['%H:%M:%S', '%H:%M', '%I:%M:%S %p', '%I:%M %p']:
                try:
                    return datetime.strptime(time_str, fmt).time()
                except ValueError:
                    continue
        elif isinstance(time_str, dt_time):
            return time_str
        elif isinstance(time_str, datetime):
            return time_str.time()

    except Exception as e:
        logger.error(f"Error extracting call time from {time_str}: {e}")

    return None


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert value to integer

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        Integer value or default
    """
    if value is None or value == '':
        return default

    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        Float value or default
    """
    if value is None or value == '':
        return default

    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_str(value: Any, default: str = '') -> str:
    """
    Safely convert value to string

    Args:
        value: Value to convert
        default: Default value if None

    Returns:
        String value or default
    """
    if value is None:
        return default

    return str(value)
