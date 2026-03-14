"""
Quotation PDF Generator using Google Docs API
Direct PDF export from Google Docs with OAuth 2.0 authentication
"""

from googleapiclient.http import MediaIoBaseDownload
import io
import tempfile
import logging

logger = logging.getLogger(__name__)


class QuotationPdfGenerator:
    """
    Generate PDF quotations directly from Google Docs API.

    This approach:
    1. Creates a copy of the template in Google Docs
    2. Populates the copy with quotation data using batch update
    3. Exports the populated document as PDF
    4. Deletes the temporary Google Docs copy

    Uses OAuth 2.0 for authentication - no service account needed.
    """

    def __init__(self, quotation, user=None):
        """
        Initialize PDF generator for a quotation.

        Args:
            quotation: Quotation model instance
            user: Django User model instance (for OAuth token)
        """
        self.quotation = quotation
        self.user = user
        from projects.models_quotation_settings import QuotationSettings
        self.settings = QuotationSettings.get_settings()

    def get_token_data(self):
        """
        Get OAuth token data for the user.

        Returns:
            dict: Token data

        Raises:
            FileNotFoundError: If no token found for user
            ValueError: If token data invalid
        """
        if not self.user:
            raise ValueError("User required for OAuth authentication")

        from projects.models_quotation_settings import QuotationToken

        # Get active token for user
        token = QuotationToken.objects.filter(
            user=self.user,
            is_active=True
        ).first()

        if not token:
            raise FileNotFoundError(
                "No Google OAuth token found. Please authorize access first."
            )

        # Decrypt token data using shared helper
        try:
            from projects.utils.google_auth import decrypt_token_data
            return decrypt_token_data(token.encrypted_token_data)
        except ValueError as e:
            logger.error(f"Failed to decrypt token data: {e}")
            raise

    def generate_pdf(self):
        """
        Generate PDF quotation directly from Google Docs.

        Returns:
            str: Path to generated PDF file (temp file)

        Raises:
            ValueError: If template not configured
            RuntimeError: If generation fails
        """
        if not self.settings.google_docs_template_id:
            raise ValueError(
                "Google Docs template not configured. "
                "Please set template URL in Quotation Settings."
            )

        try:
            # Get OAuth token
            token_data = self.get_token_data()

            # Build API services
            from projects.utils.google_auth import get_drive_service, get_docs_service
            drive_service = get_drive_service(token_data)
            docs_service = get_docs_service(token_data)

            if not drive_service or not docs_service:
                raise RuntimeError("Failed to create Google API services")

            # Step 1: Create a copy of the template
            logger.info(f"Creating copy of template {self.settings.google_docs_template_id}")
            copy_title = f"Quotation_{self.quotation.quotation_number}_temp"

            file_metadata = {
                'name': copy_title,
                'mimeType': 'application/vnd.google-apps.document'
            }

            copied_file = drive_service.files().copy(
                fileId=self.settings.google_docs_template_id,
                body=file_metadata
            ).execute()

            temp_doc_id = copied_file['id']
            logger.info(f"Template copied to document ID: {temp_doc_id}")

            # Step 2: Populate the copy with quotation data
            self._populate_google_doc(docs_service, temp_doc_id)

            # Step 3: Export as PDF
            logger.info(f"Exporting document {temp_doc_id} as PDF")
            request = drive_service.files().export_media(
                fileId=temp_doc_id,
                mimeType='application/pdf'
            )

            # Download PDF to temp file
            file_handle = io.BytesIO()
            downloader = MediaIoBaseDownload(file_handle, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.info(f"PDF download progress: {int(status.progress() * 100)}%")

            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False)
            pdf_path = temp_file.name

            with open(pdf_path, 'wb') as f:
                f.write(file_handle.getvalue())

            logger.info(f"PDF generated successfully: {pdf_path}")

            # Step 4: Delete the temporary Google Docs copy
            try:
                drive_service.files().delete(fileId=temp_doc_id).execute()
                logger.info(f"Temporary document {temp_doc_id} deleted")
            except Exception as e:
                logger.warning(f"Failed to delete temp document {temp_doc_id}: {e}")

            return pdf_path

        except Exception as e:
            logger.error(f"Failed to generate PDF from Google Docs: {e}")
            raise RuntimeError(f"PDF generation failed: {e}")

    def _populate_google_doc(self, docs_service, document_id):
        """
        Populate Google Doc with quotation data using batch update.

        Args:
            docs_service: Google Docs API service
            document_id: ID of the document to populate
        """
        # Build replacement map
        replacements = self._build_replacement_map()

        # Create batch update requests
        requests = []

        for placeholder, value in replacements.items():
            requests.append({
                'replaceAllText': {
                    'containsText': {
                        'text': placeholder,
                        'matchCase': False
                    },
                    'replaceText': str(value)
                }
            })

        # Execute batch update
        if requests:
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            logger.info(f"Populated {len(requests)} placeholders in document")

    def _build_replacement_map(self):
        """
        Build map of placeholders to quotation data.

        Returns:
            dict: Placeholder -> value mapping
        """
        from datetime import date

        quotation = self.quotation

        # Format dates
        date_str = quotation.date.strftime('%d %B %Y') if isinstance(quotation.date, date) else str(quotation.date)
        validity_str = quotation.validity_date.strftime('%d %B %Y') if hasattr(quotation, 'validity_date') else ''

        # Get default T&C from settings if not customized (use self.settings set in __init__)
        settings = self.settings

        payment_terms = quotation.payment_terms or settings.default_payment_terms
        sla_terms = quotation.sla_terms or settings.default_sla_terms
        contract_terms = quotation.contract_terms or settings.default_contract_terms
        liability_terms = quotation.liability_terms or settings.default_liability_terms

        # Basic replacements
        replacements = {
            # Header/Branding
            '{{COMPANY_TAGLINE}}': quotation.company_tagline or '',

            # Quotation details
            '{{QUOTATION_NUMBER}}': quotation.quotation_number,
            '{{DATE}}': date_str,
            '{{VALIDITY_DATE}}': validity_str,
            '{{VALIDITY_PERIOD}}': f"{quotation.validity_period} Days",

            # Client details
            '{{CLIENT_NAME}}': quotation.client_name or '',
            '{{CLIENT_COMPANY}}': quotation.client_company or '',
            '{{CLIENT_EMAIL}}': quotation.client_email or '',
            '{{CLIENT_PHONE}}': quotation.client_phone or '',
            '{{CLIENT_ADDRESS}}': quotation.client_address or '',  # Deprecated
            '{{BILLING_ADDRESS}}': quotation.billing_address or '',
            '{{SHIPPING_ADDRESS}}': quotation.shipping_address or quotation.billing_address or '',
            '{{CLIENT_GST}}': quotation.client_gst_number or 'N/A',

            # Point of contact
            '{{POINT_OF_CONTACT}}': quotation.point_of_contact or '',
            '{{POC_PHONE}}': quotation.poc_phone or '',
            '{{POC_FULL}}': f"{quotation.point_of_contact} [{quotation.poc_phone}]" if quotation.point_of_contact and quotation.poc_phone else quotation.point_of_contact or '',

            # Pricing
            '{{GST_RATE}}': f"{quotation.gst_rate}%",
            '{{SUBTOTAL}}': f"₹{quotation.subtotal:,.2f}",
            '{{GST_AMOUNT}}': f"₹{quotation.gst_amount:,.2f}",
            '{{GRAND_TOTAL}}': f"₹{quotation.grand_total:,.2f}",

            # Terms & Conditions
            '{{PAYMENT_TERMS}}': payment_terms,
            '{{SLA_TERMS}}': sla_terms,
            '{{CONTRACT_TERMS}}': contract_terms,
            '{{LIABILITY_TERMS}}': liability_terms,

            # Signature
            '{{SIGNATORY_GODAMWALE}}': quotation.for_godamwale_signatory or '',
        }

        # Add operational scope placeholders (product names + billable area)
        products = list(quotation.products.all().order_by('order'))
        for idx, product in enumerate(products, 1):
            op_label = dict(product.OPERATION_TYPE_CHOICES).get(
                product.type_of_operation, product.type_of_operation
            )
            replacements[f'{{{{PRODUCT_{idx}_NAME}}}}'] = product.product_name
            replacements[f'{{{{PRODUCT_{idx}_OPERATION}}}}'] = op_label
            replacements[f'{{{{PRODUCT_{idx}_BUSINESS}}}}'] = product.type_of_business
        billable = quotation.billable_storage_area_sqft
        if billable is not None:
            replacements['{{BILLABLE_AREA}}'] = f'{int(billable):,} sq.ft'

        # Add location-specific placeholders
        locations = quotation.locations.all().order_by('order')
        for idx, location in enumerate(locations, 1):
            replacements[f'{{{{LOCATION_{idx}_NAME}}}}'] = location.location_name
            replacements[f'{{{{LOCATION_{idx}_SUBTOTAL}}}}'] = f"₹{location.subtotal:,.2f}"
            replacements[f'{{{{LOCATION_{idx}_GST}}}}'] = f"₹{location.gst_amount:,.2f}"
            replacements[f'{{{{LOCATION_{idx}_TOTAL}}}}'] = f"₹{location.grand_total:,.2f}"

            # Add items for this location
            items = location.items.all().order_by('order')
            for item_idx, item in enumerate(items, 1):
                prefix = f'LOCATION_{idx}_ITEM_{item_idx}'
                desc = item.custom_description if item.custom_description else item.get_item_description_display()

                replacements[f'{{{{{prefix}_DESCRIPTION}}}}'] = desc
                replacements[f'{{{{{prefix}_UNIT_COST}}}}'] = item.display_unit_cost
                replacements[f'{{{{{prefix}_QUANTITY}}}}'] = item.display_quantity
                replacements[f'{{{{{prefix}_TOTAL}}}}'] = item.display_total

                if item.storage_unit_type:
                    replacements[f'{{{{{prefix}_UNIT_TYPE}}}}'] = item.get_storage_unit_type_display()

        return replacements

    def generate_docx(self):
        """
        Generate DOCX quotation (for backward compatibility).

        This method creates a DOCX by:
        1. Creating a copy of the template
        2. Populating it with data
        3. Exporting as DOCX
        4. Deleting the temp copy

        Returns:
            str: Path to generated DOCX file
        """
        if not self.settings.google_docs_template_id:
            raise ValueError(
                "Google Docs template not configured. "
                "Please set template URL in Quotation Settings."
            )

        try:
            # Get OAuth token
            token_data = self.get_token_data()

            # Build API services
            from projects.utils.google_auth import get_drive_service, get_docs_service
            drive_service = get_drive_service(token_data)
            docs_service = get_docs_service(token_data)

            if not drive_service or not docs_service:
                raise RuntimeError("Failed to create Google API services")

            # Create a copy of the template
            copy_title = f"Quotation_{self.quotation.quotation_number}_temp"
            file_metadata = {
                'name': copy_title,
                'mimeType': 'application/vnd.google-apps.document'
            }

            copied_file = drive_service.files().copy(
                fileId=self.settings.google_docs_template_id,
                body=file_metadata
            ).execute()

            temp_doc_id = copied_file['id']

            # Populate with data
            self._populate_google_doc(docs_service, temp_doc_id)

            # Export as DOCX
            request = drive_service.files().export_media(
                fileId=temp_doc_id,
                mimeType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

            file_handle = io.BytesIO()
            downloader = MediaIoBaseDownload(file_handle, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Save to temp file
            temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.docx', delete=False)
            docx_path = temp_file.name

            with open(docx_path, 'wb') as f:
                f.write(file_handle.getvalue())

            # Delete temp document
            try:
                drive_service.files().delete(fileId=temp_doc_id).execute()
            except Exception as e:
                logger.warning(f"Failed to delete temp document: {e}")

            logger.info(f"DOCX generated successfully: {docx_path}")
            return docx_path

        except Exception as e:
            logger.error(f"Failed to generate DOCX from Google Docs: {e}")
            raise RuntimeError(f"DOCX generation failed: {e}")
