"""
Adobe Sign Document Service
Handles document upload and management
"""

import requests
import logging
from django.conf import settings
from .adobe_auth import AdobeAuthService
from integrations.adobe_sign.exceptions import AdobeDocumentError

logger = logging.getLogger(__name__)


class AdobeDocumentService:
    """
    Service for Adobe Sign document operations
    Handles transient and library document uploads
    """
    BASE_URL = getattr(settings, 'ADOBE_SIGN_BASE_URL', 'https://api.in1.adobesign.com/api/rest/v6').rstrip('/')

    @staticmethod
    def upload_transient_document(file_obj, filename, mime_type='application/pdf', obo_email=None):
        """
        Upload a transient document to Adobe Sign
        Transient documents expire after 7 days and are used for one-time agreements

        Args:
            file_obj: File object or file-like object (must be opened in binary mode)
            filename: Name of the file
            mime_type: MIME type of the file (default: application/pdf)
            obo_email: Optional On-Behalf-Of email

        Returns:
            str: Transient document ID

        Raises:
            AdobeDocumentError: If upload fails
        """
        url = f"{AdobeDocumentService.BASE_URL}/transientDocuments"
        headers = AdobeAuthService.get_upload_headers(obo_email=obo_email)

        files = {
            'File': (filename, file_obj, mime_type)
        }

        try:
            logger.info(f"Uploading transient document: {filename}")
            response = requests.post(url, headers=headers, files=files, timeout=60)

            if not response.ok:
                logger.error(f"Adobe Upload Error: Status {response.status_code}, Response: {response.text}")

            response.raise_for_status()

            resp_json = response.json()
            transient_id = resp_json.get('transientDocumentId')

            if not transient_id:
                raise AdobeDocumentError(f"No transient document ID in response: {resp_json}")

            logger.info(f"Transient document uploaded successfully. ID: {transient_id}")
            return transient_id

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to upload transient document: {e}")
            raise AdobeDocumentError(f"Failed to upload document: {str(e)}")

    @staticmethod
    def convert_docx_to_pdf(docx_file_obj, filename):
        """
        Convert DOCX to PDF using Adobe Sign API
        Note: Adobe Sign automatically converts DOCX to PDF during upload

        Args:
            docx_file_obj: DOCX file object
            filename: Original filename

        Returns:
            str: Transient document ID (PDF)

        Raises:
            AdobeDocumentError: If conversion/upload fails
        """
        # Adobe Sign automatically converts DOCX to PDF
        # Just upload as transient document with correct MIME type
        return AdobeDocumentService.upload_transient_document(
            docx_file_obj,
            filename,
            mime_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
