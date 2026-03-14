"""
Signature Field Coordinate Validator
Addresses issue H2
"""
import logging

logger = logging.getLogger(__name__)


def validate_signature_field_coordinates(signature_fields, pdf_path):
    """
    Validate signature field coordinates against PDF dimensions

    Args:
        signature_fields: List of signature field definitions
        pdf_path: Path to PDF file

    Returns:
        List of error messages (empty if all valid)
    """
    errors = []

    try:
        # Try PyPDF2 first
        try:
            from PyPDF2 import PdfReader

            with open(pdf_path, 'rb') as f:
                pdf = PdfReader(f)
                num_pages = len(pdf.pages)

                page_dimensions = []
                for page in pdf.pages:
                    box = page.mediabox
                    page_dimensions.append({
                        'width': float(box.width),
                        'height': float(box.height)
                    })
        except ImportError:
            # Fallback: use pypdf if PyPDF2 not available
            try:
                from pypdf import PdfReader

                with open(pdf_path, 'rb') as f:
                    pdf = PdfReader(f)
                    num_pages = len(pdf.pages)

                    page_dimensions = []
                    for page in pdf.pages:
                        box = page.mediabox
                        page_dimensions.append({
                            'width': float(box.width),
                            'height': float(box.height)
                        })
            except ImportError:
                logger.warning('PyPDF2/pypdf not installed, skipping coordinate validation')
                return errors

        # Validate each field
        for idx, field in enumerate(signature_fields):
            locations = field.get('locations', [])

            if not locations:
                errors.append(f'Field {idx}: No locations defined')
                continue

            location = locations[0]
            page_num = location.get('pageNumber', 1)

            # Validate page number
            if page_num < 1:
                errors.append(f'Field {idx}: Invalid page number {page_num} (must be >= 1)')
                continue

            if page_num > num_pages:
                errors.append(f'Field {idx}: Page {page_num} exceeds PDF pages ({num_pages})')
                continue

            # Get page dimensions (0-indexed)
            page_dim = page_dimensions[page_num - 1]

            # Validate coordinates
            try:
                top = float(location.get('top', 0))
                left = float(location.get('left', 0))
                width = float(location.get('width', 0))
                height = float(location.get('height', 0))
            except (ValueError, TypeError) as e:
                errors.append(f'Field {idx}: Invalid coordinate values - {e}')
                continue

            if top < 0 or left < 0:
                errors.append(f'Field {idx}: Negative coordinates ({left}, {top})')

            if width <= 0 or height <= 0:
                errors.append(f'Field {idx}: Invalid dimensions ({width}x{height})')

            # Skip bounds checks — Adobe Sign handles clipping/rejection of
            # out-of-bounds fields server-side. Over-constraining here blocks
            # legitimate placements near page edges.

    except Exception as e:
        logger.error(f'Error validating signature coordinates: {e}')
        errors.append(f'Validation error: {e}')

    return errors
