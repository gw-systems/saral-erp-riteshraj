"""
Gmail API Utilities for Lead Fetcher
Functions for fetching and parsing Gmail messages
"""

import base64
import logging
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
import time

logger = logging.getLogger(__name__)


def fetch_messages_list(service, query: str, max_results: int = 500, page_token: Optional[str] = None) -> Dict:
    """
    Fetch list of message IDs matching query

    Args:
        service: Gmail API service
        query: Gmail search query
        max_results: Maximum messages to fetch (up to 500)
        page_token: Page token for pagination

    Returns:
        dict with 'messages' list and optional 'nextPageToken'
    """
    try:
        kwargs = {
            'userId': 'me',
            'q': query,
            'maxResults': min(max_results, 500)
        }

        if page_token:
            kwargs['pageToken'] = page_token

        result = service.users().messages().list(**kwargs).execute()

        logger.debug(f"Fetched {len(result.get('messages', []))} message IDs for query: {query[:100]}")

        return result

    except Exception as e:
        logger.error(f"Failed to fetch messages list: {e}")
        raise


def fetch_message(service, message_id: str, format: str = 'full') -> Optional[Dict]:
    """
    Fetch single message by ID

    Args:
        service: Gmail API service
        message_id: Gmail message ID
        format: 'full', 'metadata', 'minimal', or 'raw'

    Returns:
        dict with message data or None on error
    """
    try:
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format=format
        ).execute()

        return message

    except Exception as e:
        logger.error(f"Failed to fetch message {message_id}: {e}")
        return None


def get_header_value(headers: List[Dict], name: str) -> str:
    """
    Extract header value from Gmail message headers

    Args:
        headers: List of header dicts from Gmail API
        name: Header name (case-insensitive)

    Returns:
        Header value or empty string
    """
    for header in headers:
        if header['name'].lower() == name.lower():
            return header['value']
    return ''


def decode_body(data: str) -> str:
    """
    Decode base64url-encoded email body

    Args:
        data: Base64url-encoded string

    Returns:
        Decoded UTF-8 string
    """
    try:
        # Gmail uses base64url encoding (URL-safe base64)
        decoded_bytes = base64.urlsafe_b64decode(data)
        return decoded_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        logger.warning(f"Failed to decode body: {e}")
        return ''


def extract_body_text(payload: Dict) -> str:
    """
    Extract plain text body from Gmail message payload

    Args:
        payload: Message payload from Gmail API

    Returns:
        Plain text body (prefers text/plain, falls back to text/html)
    """
    body_text = ''

    # Single-part message
    if 'body' in payload and payload['body'].get('data'):
        body_text = decode_body(payload['body']['data'])

    # Multi-part message
    elif 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')

            # Prefer text/plain
            if mime_type == 'text/plain' and part.get('body', {}).get('data'):
                body_text = decode_body(part['body']['data'])
                break  # Stop at first text/plain

            # Fall back to text/html
            elif mime_type == 'text/html' and not body_text:
                if part.get('body', {}).get('data'):
                    body_text = decode_body(part['body']['data'])

            # Recursively check nested parts
            elif 'parts' in part:
                nested_text = extract_body_text(part)
                if nested_text and not body_text:
                    body_text = nested_text

    # Strip HTML tags if we got HTML content
    if body_text and '<html' in body_text.lower():
        import re
        body_text = re.sub(r'<[^>]+>', '', body_text)  # Remove HTML tags
        body_text = re.sub(r'\s+', ' ', body_text).strip()  # Clean whitespace

    return body_text


def extract_html_body(payload: Dict) -> str:
    """
    Extract HTML body from Gmail message payload (for UTM parsing)

    Args:
        payload: Message payload from Gmail API

    Returns:
        HTML body content (raw HTML, not stripped)
    """
    # Single-part message (HTML)
    if payload.get('mimeType') == 'text/html' and payload.get('body', {}).get('data'):
        return decode_body(payload['body']['data'])

    # Multi-part message
    if 'parts' in payload:
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')

            # Find text/html part
            if mime_type == 'text/html' and part.get('body', {}).get('data'):
                return decode_body(part['body']['data'])

            # Recursively check nested parts
            elif 'parts' in part:
                html = extract_html_body(part)
                if html:
                    return html

    return ''


def parse_gmail_message(message: Dict, lead_type: str) -> Dict:
    """
    Parse Gmail API message into structured data

    Args:
        message: Gmail API message object
        lead_type: 'CONTACT_US' or 'SAAS_INVENTORY'

    Returns:
        dict with parsed message data
    """
    headers = message['payload']['headers']

    # Extract basic headers
    from_header = get_header_value(headers, 'From')
    to_header = get_header_value(headers, 'To')
    subject = get_header_value(headers, 'Subject')
    date_header = get_header_value(headers, 'Date')
    reply_to = get_header_value(headers, 'Reply-To')

    # Parse From header (format: "Name <email@example.com>")
    from_name, from_email = parse_email_address(from_header)

    # Parse Reply-To header
    reply_to_name, reply_to_email = parse_email_address(reply_to) if reply_to else ('', '')

    # Parse date
    try:
        date_obj = parsedate_to_datetime(date_header)
    except Exception as e:
        logger.warning(f"Failed to parse date '{date_header}': {e}")
        from datetime import datetime
        date_obj = datetime.now()

    # Extract body text (plain text for display)
    body_text = extract_body_text(message['payload'])

    # Extract HTML body for UTM parameter parsing
    html_body = extract_html_body(message['payload'])

    # Extract UTM parameters from HTML (preferred) or plain text
    utm_params = extract_utm_params(subject, html_body if html_body else body_text)

    return {
        'message_id': message['id'],
        'from_name': from_name,
        'from_email': from_email,
        'reply_to_name': reply_to_name,
        'reply_to_email': reply_to_email,
        'to_addresses': to_header,
        'subject': subject,
        'date': date_obj.date(),
        'time': date_obj.time(),
        'datetime': date_obj,
        'body_text': body_text,
        'full_message_body': html_body if html_body else body_text,  # Store full HTML or text
        'internal_date': message.get('internalDate'),
        **utm_params
    }


def parse_email_address(email_string: str) -> tuple:
    """
    Parse email address from "Name <email@example.com>" format

    Args:
        email_string: Email address string

    Returns:
        tuple: (name, email)
    """
    import re

    if not email_string:
        return ('', '')

    # Try to match "Name <email@example.com>"
    match = re.match(r'(.+?)\s*<([^>]+)>', email_string)
    if match:
        name = match.group(1).strip().strip('"')
        email = match.group(2).strip()
        return (name, email)

    # If no brackets, assume it's just an email
    email_match = re.search(r'([^\s@]+@[^\s@]+\.[^\s@]+)', email_string)
    if email_match:
        return ('', email_match.group(1))

    return ('', email_string)


def extract_utm_params(subject: str, body_text: str) -> Dict[str, str]:
    """
    Extract UTM parameters from email body HTML table

    Godamwale contact form emails include UTM params in an HTML table:
    <tr><td>utm_campaign:</td><td>VALUE</td></tr>

    Args:
        subject: Email subject
        body_text: Email body (text or HTML)

    Returns:
        dict with utm_term, utm_campaign, utm_medium, utm_content
    """
    import re

    utm_params = {
        'utm_term': '',
        'utm_campaign': '',
        'utm_medium': '',
        'utm_content': ''
    }

    # Pattern 1: HTML table format (Godamwale contact form)
    # Matches: <td>utm_campaign:</td><td>VALUE</td>
    for param in ['utm_term', 'utm_campaign', 'utm_medium', 'utm_content']:
        # Look for table cell with parameter name, then capture next cell value
        pattern = rf'<td[^>]*>\s*<p>?\s*{param}:\s*</p>?\s*</td>\s*<td[^>]*>\s*<p>?\s*([^<]*?)\s*</p>?\s*</td>'
        match = re.search(pattern, body_text, re.IGNORECASE | re.DOTALL)
        if match:
            value = match.group(1).strip()
            if value:  # Only set if non-empty
                utm_params[param] = value

    # Pattern 2: URL query parameters (fallback)
    # Matches: utm_campaign=VALUE&
    for param in ['utm_term', 'utm_campaign', 'utm_medium', 'utm_content']:
        if not utm_params[param]:  # Only if not found in table
            pattern = rf'{param}=([^&\s<>]+)'
            match = re.search(pattern, body_text, re.IGNORECASE)
            if match:
                utm_params[param] = match.group(1)

    # UTM Terminator Cleaning
    # Remove next field names that bleed into UTM values
    terminators = [
        'utm_term:', 'utm_campaign:', 'utm_medium:', 'utm_content:',
        'Name:', 'Email:', 'Phone:', 'Address:', 'Company Name:', 'Message:'
    ]

    for param_key in utm_params:
        value = utm_params[param_key]
        if value:
            # Check if any terminator appears in the value
            for terminator in terminators:
                if terminator in value:
                    # Truncate at first terminator occurrence
                    utm_params[param_key] = value.split(terminator)[0].strip()
                    break

    # Organic/Direct UTM Default
    # If ALL UTM params are empty, default to "Organic/Direct"
    if not any(utm_params.values()):
        utm_params['utm_campaign'] = 'Organic/Direct'
        utm_params['utm_medium'] = 'Organic/Direct'

    return utm_params
