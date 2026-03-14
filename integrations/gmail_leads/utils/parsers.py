"""
Email Body Parsers for Lead Forms
Extracts structured data from CONTACT_US and SAAS_INVENTORY emails
"""

import re
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ContactUsParser:
    """
    Parser for CONTACT_US form emails
    Example format:
        From: Name
        Email ID: email@example.com
        Number: 1234567890
        Tell us more: Message text...
    """

    @staticmethod
    def parse(body_text: str, message_id: str) -> Dict[str, str]:
        """
        Extract form fields from Contact Us email body

        Args:
            body_text: Plain text email body
            message_id: Gmail message ID (for logging)

        Returns:
            dict with keys: form_name, form_email, form_phone, message_preview
        """
        result = {
            'form_name': '',
            'form_email': '',
            'form_phone': '',
            'form_company_name': '',
            'form_address': '',
            'gclid': '',
            'message_preview': body_text[:500] if body_text else ''  # First 500 chars
        }

        if not body_text:
            return result

        try:
            # Extract Name and Email from From: field
            # Format 1: "From: Name <email@example.com>"
            # Format 2: "From: Name" (with separate "Email:" field)
            from_match = re.search(r'From:\s*(.+?)(?:\n|$)', body_text, re.IGNORECASE)
            if from_match:
                from_text = from_match.group(1).strip()
                # Check if email is in angle brackets
                email_in_from = re.search(r'<([^\s@]+@[^\s@]+\.[^\s@]+)>', from_text)
                if email_in_from:
                    result['form_email'] = email_in_from.group(1).strip()
                    # Extract name (before the <email>)
                    name_part = re.sub(r'\s*<[^>]+>$', '', from_text).strip()
                    result['form_name'] = name_part
                else:
                    result['form_name'] = from_text

            # Extract Email from separate Email: field (if not already extracted from From:)
            if not result['form_email']:
                email_match = re.search(r'Email(?:\s+ID)?:\s*([^\s@]+@[^\s@]+\.[^\s@]+)', body_text, re.IGNORECASE)
                if email_match:
                    result['form_email'] = email_match.group(1).strip()

            # Extract Phone Number
            phone_match = re.search(r'(?:Number|Phone):\s*([0-9\s\+\-\(\)]+)', body_text, re.IGNORECASE)
            if phone_match:
                # Clean phone number (remove spaces, keep digits and +)
                phone = re.sub(r'[^\d\+]', '', phone_match.group(1))
                result['form_phone'] = phone

            # Extract Company Name (if present)
            company_match = re.search(r'Company(?:\s+Name)?:\s*(.+?)(?:\n|$)', body_text, re.IGNORECASE)
            if company_match:
                result['form_company_name'] = company_match.group(1).strip()

            # Extract Address (if present)
            address_match = re.search(r'Address:\s*(.+?)(?:\n|$)', body_text, re.IGNORECASE)
            if address_match:
                result['form_address'] = address_match.group(1).strip()

            # Extract GCLID (Google Click Identifier)
            # Format: "GCLID: Cj0KCQiAnJHMBhDAARIsABr7b87..."
            gclid_match = re.search(r'GCLID:\s*([A-Za-z0-9_-]+)', body_text, re.IGNORECASE)
            if gclid_match:
                result['gclid'] = gclid_match.group(1).strip()

            # Log success
            if result['form_email']:
                logger.debug(
                    f"ContactUs ID {message_id} - Name: {result['form_name']}, "
                    f"Email: {result['form_email']}, Phone: {result['form_phone']}"
                )
            else:
                logger.warning(
                    f"ContactUs ID {message_id} - No email extracted. "
                    f"Body preview: {body_text[:200]}"
                )

        except Exception as e:
            logger.error(f"Error parsing ContactUs email {message_id}: {e}")

        return result


class SaasInventoryParser:
    """
    Parser for SAAS_INVENTORY form emails (Inciflo leads)
    Example format:
        Name: First Last
        Email: email@example.com
        Phone: 1234567890
        Company: Company Name
        Message: Message text...
    """

    @staticmethod
    def parse(body_text: str, message_id: str) -> Dict[str, str]:
        """
        Extract form fields from SAAS Inventory email body

        Args:
            body_text: Plain text email body
            message_id: Gmail message ID (for logging)

        Returns:
            dict with keys: form_name, form_email, form_phone, message_preview
        """
        result = {
            'form_name': '',
            'form_email': '',
            'form_phone': '',
            'form_company_name': '',
            'form_address': '',
            'gclid': '',
            'message_preview': body_text[:500] if body_text else ''
        }

        if not body_text:
            return result

        try:
            # Extract Name
            name_match = re.search(r'(?:Name|Full Name):\s*(.+?)(?:\n|$)', body_text, re.IGNORECASE)
            if name_match:
                result['form_name'] = name_match.group(1).strip()
                # Remove [last-name] suffix if present
                result['form_name'] = re.sub(r'\s*\[last-name\]$', '', result['form_name'], flags=re.IGNORECASE)

            # Extract Email
            email_match = re.search(r'Email:\s*([^\s@]+@[^\s@]+\.[^\s@]+)', body_text, re.IGNORECASE)
            if email_match:
                result['form_email'] = email_match.group(1).strip()

            # Extract Phone
            phone_match = re.search(r'Phone:\s*([0-9\s\+\-\(\)]+)', body_text, re.IGNORECASE)
            if phone_match:
                phone = re.sub(r'[^\d\+]', '', phone_match.group(1))
                result['form_phone'] = phone

            # Extract Company
            company_match = re.search(r'Company:\s*(.+?)(?:\n|$)', body_text, re.IGNORECASE)
            if company_match:
                result['form_company_name'] = company_match.group(1).strip()

            # Extract GCLID (Google Click Identifier)
            gclid_match = re.search(r'GCLID:\s*([A-Za-z0-9_-]+)', body_text, re.IGNORECASE)
            if gclid_match:
                result['gclid'] = gclid_match.group(1).strip()

            # Log success
            if result['form_email']:
                logger.debug(
                    f"SaasInventory ID {message_id} - Name: {result['form_name']}, "
                    f"Email: {result['form_email']}, Company: {result['form_company_name']}"
                )
            else:
                logger.warning(
                    f"SaasInventory ID {message_id} - No email extracted. "
                    f"Body preview: {body_text[:200]}"
                )

        except Exception as e:
            logger.error(f"Error parsing SaasInventory email {message_id}: {e}")

        return result


def parse_email_body(lead_type: str, body_text: str, message_id: str) -> Dict[str, str]:
    """
    Route to appropriate parser based on lead type

    Args:
        lead_type: 'CONTACT_US' or 'SAAS_INVENTORY'
        body_text: Plain text email body
        message_id: Gmail message ID

    Returns:
        dict with extracted form fields
    """
    if lead_type == 'CONTACT_US':
        return ContactUsParser.parse(body_text, message_id)
    elif lead_type == 'SAAS_INVENTORY':
        return SaasInventoryParser.parse(body_text, message_id)
    else:
        logger.warning(f"Unknown lead type: {lead_type}")
        return {
            'form_name': '',
            'form_email': '',
            'form_phone': '',
            'form_company_name': '',
            'form_address': '',
            'message_preview': body_text[:500] if body_text else ''
        }
