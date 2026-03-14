"""
Local Quotation DOCX Generator using python-docx.
Uses Godamwale-Quotation.docx as template — preserves exact formatting,
colors, header/footer, logo. Dynamic sections (scope, pricing, T&C)
are built by cloning styled prototype elements from the template.
"""

import os
import io
import copy
import tempfile
import logging
from decimal import Decimal, InvalidOperation

from docx import Document
from docx.oxml.ns import qn

logger = logging.getLogger(__name__)

REFERENCE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'Godamwale-Quotation.docx'
)


def _get_all_text(element):
    """Get all text from an XML element's w:t children."""
    return ''.join(t.text or '' for t in element.findall('.//' + qn('w:t')))


def _set_run_text(run_element, text):
    """Set text of a w:r element (first w:t child)."""
    t = run_element.find(qn('w:t'))
    if t is not None:
        t.text = text
        # Preserve spaces
        t.set(qn('xml:space'), 'preserve')


def _replace_in_element(element, old, new):
    """Replace text in all w:t children of an element."""
    for t in element.findall('.//' + qn('w:t')):
        if t.text and old in t.text:
            t.text = t.text.replace(old, new)


def _clone_element(element):
    """Deep copy an XML element."""
    return copy.deepcopy(element)


def _indian_format(value):
    """Format a number in Indian comma style: 1,19,250"""
    try:
        val = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)

    is_negative = val < 0
    val = abs(val)
    int_part = int(val)
    dec_part = val - int_part

    s = str(int_part)
    if len(s) <= 3:
        formatted = s
    else:
        last3 = s[-3:]
        remaining = s[:-3]
        groups = []
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        groups.reverse()
        formatted = ','.join(groups) + ',' + last3

    if is_negative:
        formatted = '-' + formatted
    return formatted


def _is_numeric(val):
    """Check if a string value is numeric."""
    try:
        Decimal(str(val))
        return True
    except (InvalidOperation, ValueError):
        return False


def _format_cost(unit_cost):
    """Format unit cost for table: numeric → Indian format, text → as-is."""
    if _is_numeric(unit_cost):
        val = Decimal(str(unit_cost))
        if val == int(val):
            return _indian_format(int(val))
        return str(val)
    return str(unit_cost).strip().capitalize()


def _format_qty(quantity):
    """Format quantity for table: numeric → number, text → as-is."""
    if _is_numeric(quantity):
        val = Decimal(str(quantity))
        if val == int(val):
            return str(int(val))
        return str(val)
    return str(quantity).strip().capitalize()


def _format_total(item):
    """Format total: calculable → Indian format, else '-'."""
    if item.is_calculated:
        return _indian_format(item.total)
    return '-'


class LocalQuotationDocxGenerator:
    """
    Generate DOCX quotation by cloning the reference Godamwale-Quotation.docx
    and replacing content while preserving all formatting.
    """

    def __init__(self, quotation):
        self.quotation = quotation
        from projects.models_quotation_settings import QuotationSettings
        self.settings = QuotationSettings.get_settings()

    def generate_docx(self):
        """Generate and return path to a DOCX file."""
        source = REFERENCE_PATH
        if not os.path.exists(source):
            raise FileNotFoundError(
                f"Quotation template not found at {source}. "
                "Please place Godamwale-Quotation.docx in the project root."
            )

        doc = Document(source)
        body = doc.element.body

        # Map body children by index
        children = list(body)

        # --- Extract prototype elements before modifying ---
        # IMPORTANT: These indices are tied to the structure of Godamwale-Quotation.docx.
        # If the template is updated, verify each index by printing _get_all_text(children[N]).
        #
        # Expected document layout (0-indexed body children):
        #   [0]  Heading paragraph ("GODAMWALE TRADING & LOGISTICS PVT. LTD.")
        #   [1]  Tagline paragraph ("Comprehensive Warehousing & Logistics Services")
        #   [2]  Empty/separator paragraph
        #   [3]  Client details table (name, email, address)
        #   [4]  Empty/separator paragraph
        #   [5]  Quotation summary table (date, validity, POC)
        #   [6]  "SCOPE OF SERVICE" main heading paragraph
        #   [7]  First scope service heading paragraph (e.g. "1. Warehousing Services")
        #   [8]  First scope bullet paragraph (List Paragraph style)
        #   ... (more scope entries up to ~[27])
        #   [28] "PRICING DETAILS – ..." heading paragraph
        #   [29] Pricing table (header + 8 data rows + subtotal/GST/total = 12 rows)
        #   [30] Second pricing heading (if multi-location template)
        #   [31] Second pricing table
        #   [32] "TERMS & CONDITIONS" main heading paragraph
        #   [33] "Payment Terms" sub-heading paragraph
        #   [34] First T&C bullet paragraph
        #   ... (more T&C entries up to ~[58])
        #   [59] "ACCEPTANCE" paragraph (used as insertion anchor)
        #   ...  Signature table, closing paragraphs

        # Scope heading prototype: element[7] → "1. Warehousing Services"
        proto_scope_heading = _clone_element(children[7])
        # Scope bullet prototype: element[8] → List Paragraph style bullet
        proto_scope_bullet = _clone_element(children[8])
        # Pricing section heading prototype: element[28] → "PRICING DETAILS – ..."
        proto_pricing_heading = _clone_element(children[28])
        # Pricing table prototype: element[29] → 12-row pricing table
        proto_pricing_table = _clone_element(children[29])
        # T&C main heading prototype: element[32] → "TERMS & CONDITIONS"
        proto_tc_main_heading = _clone_element(children[32])
        # T&C sub-heading prototype: element[33] → "Payment Terms"
        proto_tc_subheading = _clone_element(children[33])
        # T&C bullet prototype: element[34] → first bullet under "Payment Terms"
        proto_tc_bullet = _clone_element(children[34])

        # === STEP 1: Replace static placeholders ===
        self._replace_static_fields(children)

        # === STEP 2: Remove dynamic sections, rebuild them ===
        # Identify ranges to remove (by element reference)
        # Scope: elements [6] through [27] (heading + all scope content + empty para)
        scope_elements = children[6:28]
        # Pricing: elements [28] through [31] (2 headings + 2 tables)
        pricing_elements = children[28:32]
        # T&C: elements [32] through [58]
        tc_elements = children[32:59]

        # Remove in reverse order to preserve indices
        for elem in reversed(tc_elements + pricing_elements + scope_elements):
            body.remove(elem)

        # Find insertion point: after quotation summary table (element[5] originally)
        # After removal, children[5] is the last static element before dynamic content
        # We need to insert before ACCEPTANCE (element[59] originally = now shifted)
        # Easiest: find ACCEPTANCE paragraph
        acceptance_elem = None
        for child in body:
            if child.tag.endswith('}p'):
                text = _get_all_text(child)
                if 'ACCEPTANCE' in text:
                    acceptance_elem = child
                    break

        if acceptance_elem is None:
            raise RuntimeError("Could not find ACCEPTANCE marker in template")

        # Build dynamic sections and insert before ACCEPTANCE
        dynamic_elements = []

        # --- Scope of Service ---
        scope_elems = self._build_scope_elements(
            proto_scope_heading, proto_scope_bullet, children[6] if len(scope_elements) > 0 else None
        )
        # Use the original scope main heading
        if scope_elems:
            scope_main_heading = _clone_element(scope_elements[0])  # "SCOPE OF SERVICE..."
            dynamic_elements.append(scope_main_heading)
            dynamic_elements.extend(scope_elems)
            # Add empty para spacer
            empty_p = _clone_element(scope_elements[-1]) if scope_elements[-1].tag.endswith('}p') else None
            if empty_p:
                # Clear text
                for t in empty_p.findall('.//' + qn('w:t')):
                    t.text = ''
                dynamic_elements.append(empty_p)

        # --- Pricing Tables ---
        pricing_elems = self._build_pricing_elements(
            proto_pricing_heading, proto_pricing_table
        )
        dynamic_elements.extend(pricing_elems)

        # --- Terms & Conditions ---
        tc_elems = self._build_tc_elements(
            proto_tc_main_heading, proto_tc_subheading, proto_tc_bullet
        )
        dynamic_elements.extend(tc_elems)

        # Insert all dynamic elements before ACCEPTANCE (in order)
        for elem in dynamic_elements:
            acceptance_elem.addprevious(elem)

        # Save
        temp_file = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
        doc.save(temp_file.name)
        logger.info(f"Local DOCX generated: {temp_file.name}")
        return temp_file.name

    def generate_pdf(self, user=None):
        """
        Generate PDF by creating DOCX locally then converting via Google Drive API.

        Uploads the DOCX to Google Drive (auto-converts to Google Docs format),
        exports as PDF, downloads the result, and cleans up.
        """
        from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
        from projects.models_quotation_settings import QuotationToken
        from projects.utils.google_auth import get_drive_service

        docx_path = self.generate_docx()

        # Get OAuth token for Google Drive access
        if not user:
            raise RuntimeError(
                "User required for PDF generation. "
                "Google Drive API is used to convert DOCX to PDF."
            )

        token = QuotationToken.objects.filter(user=user, is_active=True).first()
        if not token:
            raise RuntimeError(
                "No Google OAuth token found. Please authorize Google access "
                "in Quotation Settings before generating PDFs."
            )

        # Decrypt token data using shared helper
        try:
            from projects.utils.google_auth import decrypt_token_data
            token_data = decrypt_token_data(token.encrypted_token_data)
        except ValueError as e:
            raise RuntimeError(f"Failed to decrypt OAuth token: {e}")

        drive_service = get_drive_service(token_data)
        if not drive_service:
            raise RuntimeError("Failed to create Google Drive API service")

        temp_file_id = None
        try:
            # Upload DOCX to Google Drive, converting to Google Docs format
            file_metadata = {
                'name': f'Quotation_{self.quotation.quotation_number}_temp',
                'mimeType': 'application/vnd.google-apps.document',
            }
            media = MediaFileUpload(
                docx_path,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                resumable=True,
            )
            uploaded = drive_service.files().create(
                body=file_metadata, media_body=media, fields='id'
            ).execute()
            temp_file_id = uploaded['id']
            logger.info(f"DOCX uploaded to Google Drive: {temp_file_id}")

            # Export as PDF
            request = drive_service.files().export_media(
                fileId=temp_file_id, mimeType='application/pdf'
            )
            file_handle = io.BytesIO()
            downloader = MediaIoBaseDownload(file_handle, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()

            # Save PDF locally
            pdf_path = docx_path.replace('.docx', '.pdf')
            with open(pdf_path, 'wb') as f:
                f.write(file_handle.getvalue())

            logger.info(f"PDF generated via Google Drive: {pdf_path}")
            return pdf_path

        finally:
            # Clean up: delete temp file from Google Drive
            if temp_file_id:
                try:
                    drive_service.files().delete(fileId=temp_file_id).execute()
                    logger.info(f"Temp Google Drive file {temp_file_id} deleted")
                except Exception as e:
                    logger.warning(f"Failed to delete temp Drive file: {e}")

            # Clean up local DOCX temp file
            try:
                os.unlink(docx_path)
            except OSError:
                pass

    def _replace_static_fields(self, children):
        """Replace static text in client details, quotation summary, and signature."""
        q = self.quotation

        # --- P[1]: Tagline ---
        _replace_in_element(children[1], 'Comprehensive Warehousing & Logistics Services',
                            q.company_tagline or 'Comprehensive Warehousing & Logistics Services')

        # --- Table[0] (children[3]): Client Details ---
        client_table = children[3]
        rows = client_table.findall(qn('w:tr'))

        # Row 0: Client Name | Company Name
        self._replace_non_bold_text(rows[0], 'Brajender Tiwari', q.client_name or '')
        self._replace_non_bold_text(rows[0], 'Vedang Cellular Services', q.client_company or '')

        # Row 1: Email | Contact Number
        self._replace_non_bold_text(rows[1], 'brajender.tiwari@vedangcellular.com', q.client_email or '')
        self._replace_non_bold_text(rows[1], '+91-7718898243', q.client_phone or '')

        # Row 2: Address
        address = q.billing_address or q.client_address or ''
        # The address text spans multiple runs, replace all non-bold text in row 2
        self._replace_address_text(rows[2], address)

        # --- Table[1] (children[5]): Quotation Summary ---
        summary_table = children[5]
        srows = summary_table.findall(qn('w:tr'))

        # Row 0: Date
        date_str = q.date.strftime('%d %b %Y') if q.date else ''
        self._replace_non_bold_text(srows[0], '01 Dec 2025', date_str)

        # Row 1: Validity + POC
        self._replace_non_bold_text(srows[1], '45', str(q.validity_period))
        poc_text = ''
        if q.point_of_contact:
            poc_text = q.point_of_contact
            if q.poc_phone:
                poc_text += f' [{q.poc_phone}]'
        self._replace_non_bold_text(srows[1], 'Vikas Pandey [9867022521]', poc_text)

        # --- Signature table (last table before closing) ---
        # Find the signature table - it's the table containing "For Client:"
        for child in children:
            if child.tag.endswith('}tbl'):
                text = _get_all_text(child)
                if 'For Client:' in text and 'For Go' in text:
                    sig_text = q.for_godamwale_signatory or 'Annand Aryamane [9820504595]'
                    # Replace the signatory name
                    self._replace_signatory(child, sig_text)
                    break

    def _replace_non_bold_text(self, element, old_text, new_text):
        """Find and replace non-bold text within an element."""
        for run in element.findall('.//' + qn('w:r')):
            rPr = run.find(qn('w:rPr'))
            is_bold = False
            if rPr is not None:
                b = rPr.find(qn('w:b'))
                if b is not None and b.get(qn('w:val'), 'true') != 'false':
                    is_bold = True

            t = run.find(qn('w:t'))
            if t is not None and t.text and old_text in t.text:
                t.text = t.text.replace(old_text, new_text)
                t.set(qn('xml:space'), 'preserve')
                return True

        # Fallback: try concatenated text replacement across runs
        # Collect all runs with their text
        runs = element.findall('.//' + qn('w:r'))
        full_text = ''
        run_map = []  # (run_element, start_idx, end_idx)
        for run in runs:
            t = run.find(qn('w:t'))
            if t is not None and t.text:
                start = len(full_text)
                full_text += t.text
                run_map.append((run, t, start, len(full_text)))

        if old_text in full_text:
            idx = full_text.index(old_text)
            end_idx = idx + len(old_text)

            # Find which runs contain the old text
            first_run = None
            for run, t, start, end in run_map:
                if start <= idx < end and first_run is None:
                    first_run = (run, t, start, end)
                    # Replace in first run
                    before = t.text[:idx - start]
                    after = t.text[min(end_idx - start, len(t.text)):]
                    t.text = before + new_text + after
                    t.set(qn('xml:space'), 'preserve')
                elif first_run and start < end_idx:
                    # Clear subsequent runs that were part of old text
                    overlap_end = min(end_idx - start, len(t.text))
                    t.text = t.text[overlap_end:]
                    t.set(qn('xml:space'), 'preserve')
            return True

        return False

    def _replace_address_text(self, row_element, new_address):
        """Replace the address text in the merged address row."""
        # Find all non-bold runs after "Address:" and replace
        found_label = False
        first_value_run = True
        for run in row_element.findall('.//' + qn('w:r')):
            t = run.find(qn('w:t'))
            if t is None:
                continue

            rPr = run.find(qn('w:rPr'))
            is_bold = False
            if rPr is not None:
                b = rPr.find(qn('w:b'))
                if b is not None and b.get(qn('w:val'), 'true') != 'false':
                    is_bold = True

            if is_bold and t.text and 'Address' in t.text:
                found_label = True
                continue

            if found_label and t.text is not None:
                if first_value_run:
                    t.text = ' ' + new_address
                    t.set(qn('xml:space'), 'preserve')
                    first_value_run = False
                else:
                    t.text = ''

    def _replace_signatory(self, table_element, new_signatory):
        """Replace signatory name in the signature table."""
        # The second cell contains "For Godamwale: Annand Aryamane [9820504595]"
        # We need to replace the non-bold part after "For Godamwale:"
        cells = table_element.findall('.//' + qn('w:tc'))
        if len(cells) < 2:
            return

        right_cell = cells[1]
        found_label = False
        first_value = True
        for run in right_cell.findall('.//' + qn('w:r')):
            t = run.find(qn('w:t'))
            if t is None:
                continue

            rPr = run.find(qn('w:rPr'))
            is_bold = False
            if rPr is not None:
                b = rPr.find(qn('w:b'))
                if b is not None and b.get(qn('w:val'), 'true') != 'false':
                    is_bold = True

            # Once we've seen all the bold "For Godamwale:" text, replace value runs
            if is_bold and t.text and ('Godamwale' in (t.text or '') or 'Go' in (t.text or '')):
                found_label = True
                continue
            if is_bold and found_label:
                # Still bold label runs (split across multiple runs)
                continue

            if found_label and not is_bold and t.text is not None:
                if first_value:
                    t.text = ' ' + new_signatory
                    t.set(qn('xml:space'), 'preserve')
                    first_value = False
                else:
                    t.text = ''

    def _build_scope_elements(self, proto_heading, proto_bullet, original_heading_elem):
        """Build Operational Scope of Service elements for the DOCX.

        Shows: product names + type of operation + billable storage area.
        Does NOT show: dimensions, unit conversions, or intermediate calculations.
        """
        q = self.quotation
        products = list(q.products.all().order_by('order'))

        elements = []

        if products:
            for idx, product in enumerate(products, 1):
                # Heading: "1. Product Name (Operation Type)"
                heading = _clone_element(proto_heading)
                texts = heading.findall('.//' + qn('w:t'))
                op_label = dict(product.OPERATION_TYPE_CHOICES).get(
                    product.type_of_operation, product.type_of_operation
                )
                heading_text = f'{idx}. {product.product_name} ({op_label})'
                if texts:
                    texts[0].text = heading_text
                    texts[0].set(qn('xml:space'), 'preserve')
                    for t in texts[1:]:
                        t.text = ''
                elements.append(heading)

                # Bullet: Packaging Type (if set)
                if product.packaging_type:
                    bullet = _clone_element(proto_bullet)
                    texts = bullet.findall('.//' + qn('w:t'))
                    if texts:
                        texts[0].text = f'Packaging: {product.packaging_type}'
                        texts[0].set(qn('xml:space'), 'preserve')
                        for t in texts[1:]:
                            t.text = ''
                    elements.append(bullet)

                # Bullet: Business Type
                bullet = _clone_element(proto_bullet)
                texts = bullet.findall('.//' + qn('w:t'))
                if texts:
                    texts[0].text = f'Business Type: {product.type_of_business}'
                    texts[0].set(qn('xml:space'), 'preserve')
                    for t in texts[1:]:
                        t.text = ''
                elements.append(bullet)

        # Final bullet: Billable Storage Area
        billable = q.billable_storage_area_sqft
        if billable is not None:
            bullet = _clone_element(proto_bullet)
            texts = bullet.findall('.//' + qn('w:t'))
            area_text = f'Billable / Storage Area: {int(billable):,} sq.ft'
            if texts:
                texts[0].text = area_text
                texts[0].set(qn('xml:space'), 'preserve')
                for t in texts[1:]:
                    t.text = ''
            elements.append(bullet)

        return elements

    def _build_pricing_elements(self, proto_heading, proto_table):
        """Build pricing section elements for each location."""
        q = self.quotation
        locations = q.locations.all().order_by('order')
        elements = []

        for location in locations:
            # Section heading: "PRICING DETAILS – LOCATION_NAME"
            heading = _clone_element(proto_heading)
            heading_texts = heading.findall('.//' + qn('w:t'))
            # Combine all text into first run
            if heading_texts:
                heading_texts[0].text = f'PRICING DETAILS \u2013 {location.location_name.upper()} '
                heading_texts[0].set(qn('xml:space'), 'preserve')
                for t in heading_texts[1:]:
                    t.text = ''
            elements.append(heading)

            # Clone the pricing table
            table = _clone_element(proto_table)
            table_rows = table.findall(qn('w:tr'))

            # Row 0 = header (keep as-is)
            # Rows 1-8 = data rows (template has 8 item rows)
            # Row 9 = Subtotal
            # Row 10 = GST
            # Row 11 = Grand Total

            items = list(location.items.all().order_by('order'))
            template_data_rows = table_rows[1:9]  # 8 data rows in template

            if len(items) <= len(template_data_rows):
                # Fewer items than template rows: fill items, remove extra rows
                for i, item in enumerate(items):
                    self._fill_item_row(template_data_rows[i], item)
                # Remove unused rows
                for i in range(len(items), len(template_data_rows)):
                    table.remove(template_data_rows[i])
            else:
                # More items: fill existing rows, clone extras
                for i, row in enumerate(template_data_rows):
                    if i < len(items):
                        self._fill_item_row(row, items[i])

                # Clone last data row for additional items
                last_data_row = template_data_rows[-1]
                insert_before = table_rows[9]  # Subtotal row
                for i in range(len(template_data_rows), len(items)):
                    new_row = _clone_element(last_data_row)
                    self._fill_item_row(new_row, items[i])
                    insert_before.addprevious(new_row)

            # Fill summary rows (find them fresh after possible row changes)
            all_rows = table.findall(qn('w:tr'))
            # Subtotal = 3rd from last, GST = 2nd from last, Grand Total = last
            subtotal_row = all_rows[-3]
            gst_row = all_rows[-2]
            gt_row = all_rows[-1]

            # Subtotal value (last cell)
            self._set_last_cell_text(subtotal_row, _indian_format(location.subtotal))

            # GST label + value
            gst_label = f'GST @ {q.gst_rate}%'
            self._set_merged_cells_text(gst_row, gst_label, _indian_format(location.gst_amount))

            # Grand Total value
            self._set_last_cell_text(gt_row, _indian_format(location.grand_total))

            elements.append(table)

        return elements

    def _fill_item_row(self, row_element, item):
        """Fill a pricing table data row with item data."""
        cells = row_element.findall(qn('w:tc'))
        if len(cells) < 4:
            return

        desc = item.get_item_description_display()
        if item.custom_description:
            desc = item.custom_description

        values = [
            desc,
            _format_cost(item.unit_cost),
            _format_qty(item.quantity),
            _format_total(item),
        ]

        for i, val in enumerate(values):
            cell = cells[i]
            texts = cell.findall('.//' + qn('w:t'))
            if texts:
                texts[0].text = val
                texts[0].set(qn('xml:space'), 'preserve')
                for t in texts[1:]:
                    t.text = ''
            else:
                # No existing text runs — add one
                p = cell.find(qn('w:p'))
                if p is not None:
                    r = p.makeelement(qn('w:r'), {})
                    t = r.makeelement(qn('w:t'), {})
                    t.text = val
                    t.set(qn('xml:space'), 'preserve')
                    r.append(t)
                    p.append(r)

    def _set_last_cell_text(self, row_element, text):
        """Set text of the last cell in a table row."""
        cells = row_element.findall(qn('w:tc'))
        if not cells:
            return
        last_cell = cells[-1]
        texts = last_cell.findall('.//' + qn('w:t'))
        if texts:
            texts[0].text = text
            texts[0].set(qn('xml:space'), 'preserve')
            for t in texts[1:]:
                t.text = ''

    def _set_merged_cells_text(self, row_element, label_text, value_text):
        """Set text in a merged-cell summary row (label in first cells, value in last)."""
        cells = row_element.findall(qn('w:tc'))
        if not cells:
            return

        # First cell(s) contain the label (merged)
        first_cell = cells[0]
        texts = first_cell.findall('.//' + qn('w:t'))
        if texts:
            texts[0].text = label_text
            texts[0].set(qn('xml:space'), 'preserve')
            for t in texts[1:]:
                t.text = ''

        # Last cell contains the value
        last_cell = cells[-1]
        texts = last_cell.findall('.//' + qn('w:t'))
        if texts:
            texts[0].text = value_text
            texts[0].set(qn('xml:space'), 'preserve')
            for t in texts[1:]:
                t.text = ''

    def _build_tc_elements(self, proto_main_heading, proto_subheading, proto_bullet):
        """Build Terms & Conditions elements."""
        q = self.quotation
        settings = self.settings

        payment = q.payment_terms or settings.default_payment_terms
        sla = q.sla_terms or settings.default_sla_terms
        contract = q.contract_terms or settings.default_contract_terms
        liability = q.liability_terms or settings.default_liability_terms

        sections = [
            ('Payment Terms', payment),
            ('SLA & Service Commitments', sla),
            ('Contract Tenure', contract),
            ('Liability & Compliance', liability),
        ]

        has_any = any(content for _, content in sections)
        if not has_any:
            return []

        elements = []

        # Main heading: "TERMS & CONDITIONS"
        main_h = _clone_element(proto_main_heading)
        elements.append(main_h)

        for title, content in sections:
            if not content:
                continue

            # Sub-heading
            sub_h = _clone_element(proto_subheading)
            texts = sub_h.findall('.//' + qn('w:t'))
            if texts:
                texts[0].text = title
                texts[0].set(qn('xml:space'), 'preserve')
                for t in texts[1:]:
                    t.text = ''
            elements.append(sub_h)

            # Bullet points (split content by newlines)
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            for line in lines:
                clean = line.lstrip('\u2022\u00b7\u2013\u2014-* ').strip()
                if not clean:
                    continue
                bullet = _clone_element(proto_bullet)
                texts = bullet.findall('.//' + qn('w:t'))
                if texts:
                    texts[0].text = clean
                    texts[0].set(qn('xml:space'), 'preserve')
                    for t in texts[1:]:
                        t.text = ''
                elements.append(bullet)

        return elements
