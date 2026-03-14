# Quotation System - Quick Reference

## 🚀 Quick Start

### Setup (One-Time)
1. Create Google Cloud service account with Drive & Docs API access
2. Download JSON key file
3. Create Google Docs template with placeholders
4. Share template with service account email (Editor access)
5. In Saral ERP: Projects → Quotations → Settings
6. Upload JSON key file and paste template URL
7. Save settings ✅

### Generate Quotation
1. Projects → Quotations → Create New
2. Enter client details, locations, and line items
3. Save quotation
4. Click "Download PDF" or "Send Email"

---

## 📋 API Overview

### QuotationPdfGenerator

**Location:** `projects/services/quotation_pdf.py`

```python
from projects.services.quotation_pdf import QuotationPdfGenerator

# Initialize with quotation instance
generator = QuotationPdfGenerator(quotation)

# Generate PDF
pdf_path = generator.generate_pdf()  # Returns temp file path

# Generate DOCX
docx_path = generator.generate_docx()  # Returns temp file path
```

### Key Methods

| Method | Description | Returns | Use Case |
|--------|-------------|---------|----------|
| `generate_pdf()` | Generate PDF from Google Docs | str (temp file path) | Download PDF, email attachment |
| `generate_docx()` | Generate DOCX from Google Docs | str (temp file path) | Download DOCX for editing |
| `get_credentials()` | Get service account credentials | Credentials object | Internal use |
| `_populate_google_doc()` | Batch update placeholders | None | Internal use |
| `_build_replacement_map()` | Build placeholder map | dict | Internal use |

---

## 🔑 Placeholders

### Basic
```
{{QUOTATION_NUMBER}}      - GW-Q-20260213-0001
{{DATE}}                  - 13 February 2026
{{VALIDITY_DATE}}         - 15 March 2026
{{CLIENT_NAME}}           - John Doe
{{CLIENT_COMPANY}}        - ABC Logistics
{{CLIENT_EMAIL}}          - john@abc.com
{{CLIENT_PHONE}}          - +91 98765 43210
{{CLIENT_ADDRESS}}        - 123 MG Road, Mumbai
{{CLIENT_GST}}            - 27AABCU9603R1ZM
{{POINT_OF_CONTACT}}      - John - Operations Manager
{{GST_RATE}}              - 18%
{{SUBTOTAL}}              - ₹1,00,000.00
{{GST_AMOUNT}}            - ₹18,000.00
{{GRAND_TOTAL}}           - ₹1,18,000.00
```

### Multi-Location
```
{{LOCATION_1_NAME}}       - Mumbai Warehouse
{{LOCATION_1_SUBTOTAL}}   - ₹50,000.00
{{LOCATION_1_GST}}        - ₹9,000.00
{{LOCATION_1_TOTAL}}      - ₹59,000.00

{{LOCATION_2_NAME}}       - Delhi DC
{{LOCATION_2_SUBTOTAL}}   - ₹30,000.00
...
```

### Line Items
```
{{LOCATION_1_ITEM_1_DESCRIPTION}}  - Storage Charges
{{LOCATION_1_ITEM_1_UNIT_COST}}    - ₹500.00
{{LOCATION_1_ITEM_1_QUANTITY}}     - 100
{{LOCATION_1_ITEM_1_TOTAL}}        - ₹50,000.00
{{LOCATION_1_ITEM_1_UNIT_TYPE}}    - Per Pallet

{{LOCATION_1_ITEM_2_DESCRIPTION}}  - Handling Charges
{{LOCATION_1_ITEM_2_UNIT_COST}}    - At Actual
{{LOCATION_1_ITEM_2_QUANTITY}}     - As Applicable
{{LOCATION_1_ITEM_2_TOTAL}}        - As Applicable
```

---

## 🎯 Usage Examples

### View: Download PDF
```python
@login_required
def download_pdf(request, quotation_id):
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    generator = QuotationPdfGenerator(quotation)
    pdf_path = generator.generate_pdf()

    return FileResponse(
        open(pdf_path, 'rb'),
        content_type='application/pdf',
        as_attachment=True,
        filename=f'{quotation.quotation_number}.pdf'
    )
```

### View: Download DOCX
```python
@login_required
def download_docx(request, quotation_id):
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    generator = QuotationPdfGenerator(quotation)
    docx_path = generator.generate_docx()

    return FileResponse(
        open(docx_path, 'rb'),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        as_attachment=True,
        filename=f'{quotation.quotation_number}.docx'
    )
```

### View: Send Email
```python
@login_required
def send_email(request, quotation_id):
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    # Generate PDF
    generator = QuotationPdfGenerator(quotation)
    pdf_path = generator.generate_pdf()

    # Read for attachment
    with open(pdf_path, 'rb') as f:
        pdf_data = f.read()

    # Send via Gmail API
    from gmail.services import EmailService
    EmailService.send_email(
        user=request.user,
        sender_email='sender@example.com',
        to_email=quotation.client_email,
        subject=f'Quotation {quotation.quotation_number}',
        message_text='Please find attached quotation...',
        attachments=[{
            'filename': f'{quotation.quotation_number}.pdf',
            'data': pdf_data
        }]
    )

    messages.success(request, 'Quotation sent successfully!')
    return redirect('projects:quotation_detail', quotation_id=quotation_id)
```

---

## ⚙️ Settings Model

**Location:** `projects/models_quotation_settings.py`

```python
from projects.models_quotation_settings import QuotationSettings

# Get singleton instance (always returns the same settings)
settings = QuotationSettings.get_settings()

# Access fields
template_url = settings.google_docs_template_url
template_id = settings.google_docs_template_id  # Auto-extracted from URL
credentials_file = settings.google_service_account_file
default_gst = settings.default_gst_rate
validity_days = settings.default_validity_days
email_subject = settings.email_subject_template
email_body = settings.email_body_template
```

### Available Fields
| Field | Type | Description |
|-------|------|-------------|
| `google_docs_template_url` | URLField | Full Google Docs URL |
| `google_docs_template_id` | CharField | Auto-extracted document ID |
| `google_service_account_file` | FileField | Uploaded JSON key |
| `default_gst_rate` | DecimalField | Default GST % (18.00) |
| `default_validity_days` | IntegerField | Default validity (30 days) |
| `email_subject_template` | CharField | Email subject template |
| `email_body_template` | TextField | Email body template |

---

## 🔧 Troubleshooting

### Error Messages & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| "Google service account credentials not configured" | No JSON key uploaded | Upload JSON key in Settings |
| "Google Docs template not configured" | No template URL | Paste template URL in Settings |
| "Template download failed" | Template not shared | Share template with service account email |
| "Permission denied" | Service account no access | Grant Editor access to template |
| "API not enabled" | Drive/Docs API disabled | Enable in Cloud Console |
| "Invalid credentials file" | Malformed JSON | Re-download JSON key |

### Debug Commands

```bash
# Check if APIs are enabled
gcloud services list --enabled | grep -E 'drive|docs'

# View service account email
cat service-account-key.json | grep client_email

# Test API access
python manage.py shell
>>> from projects.services.quotation_pdf import QuotationPdfGenerator
>>> from projects.models_quotation import Quotation
>>> q = Quotation.objects.first()
>>> gen = QuotationPdfGenerator(q)
>>> gen.get_credentials()  # Should return credentials object
```

---

## 📊 Performance

### Expected Timing
- **PDF Generation:** 2-5 seconds
- **DOCX Generation:** 2-5 seconds
- **Email Sending:** 3-7 seconds (includes PDF generation)

### Optimization Tips
1. Generate PDFs asynchronously for bulk operations
2. Cache template metadata (document ID extraction)
3. Use batch operations for multiple quotations
4. Clean up temp files immediately

### API Quotas
- **Google Drive API:** 1B requests/day
- **Typical usage:** ~500 requests/day (100 quotations × 5 calls)
- **Headroom:** 99.99995% quota remaining ✅

---

## 🔐 Security Checklist

- [ ] Service account JSON key uploaded (not in settings.py)
- [ ] Template shared only with service account (not public)
- [ ] Service account has minimal scopes (drive + docs only)
- [ ] Temp documents deleted after generation
- [ ] Credentials file encrypted in database
- [ ] No API keys in environment variables
- [ ] Audit logs track all generations

---

## 🎨 Template Design Tips

### Structure
```
1. Header section (company logo, quotation number, date)
2. Client information block
3. Line items table per location
4. Pricing summary (subtotal, GST, total)
5. Terms & conditions
6. Signature section
```

### Best Practices
- Use tables for structured data (line items)
- Use placeholders in double curly braces `{{PLACEHOLDER}}`
- Test with sample data before using in production
- Keep formatting simple (Google Docs export limitations)
- Use consistent font sizes and styles
- Include page breaks for multi-page quotations

### Common Mistakes
❌ Missing placeholders (won't be replaced)
❌ Typos in placeholder names
❌ Not sharing template with service account
❌ Using complex formatting (charts, embedded objects)
❌ Too many nested tables

---

## 📁 File Structure

```
projects/
├── models_quotation.py              # Quotation, Location, Item, Audit models
├── models_quotation_settings.py     # Settings model (singleton)
├── forms_quotation.py               # Forms for CRUD operations
├── views_quotation.py               # Views (list, detail, create, edit, download, email)
├── admin.py                         # Admin configuration
├── urls.py                          # URL routing
└── services/
    ├── quotation_pdf.py             # PDF/DOCX generation (Google Docs API)
    ├── quotation_template.py        # Template fetching (Drive API)
    └── quotation_audit.py           # Audit logging

templates/projects/quotations/
├── quotation_list.html              # List view
├── quotation_detail.html            # Detail view with audit log
├── quotation_create.html            # Create/edit form
├── quotation_email.html             # Email sending form
└── quotation_settings.html          # Settings page

Documentation/
├── QUOTATION_GOOGLE_DOCS_SETUP.md   # Complete setup guide
├── QUOTATION_MIGRATION_SUMMARY.md   # Migration details
└── QUOTATION_QUICK_REFERENCE.md     # This file
```

---

## 🚀 Deployment

### Local Development
```bash
# No LibreOffice installation needed!
python manage.py runserver
```

### GCP Cloud Run
```dockerfile
# Dockerfile - no system dependencies needed
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD exec gunicorn --bind :$PORT minierp.wsgi:application
```

### Docker Compose
```yaml
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=...
    # No volumes needed for LibreOffice!
```

---

## 📞 Support

### Resources
- Setup Guide: `QUOTATION_GOOGLE_DOCS_SETUP.md`
- Migration Details: `QUOTATION_MIGRATION_SUMMARY.md`
- Google Drive API Docs: https://developers.google.com/drive/api/v3/reference
- Google Docs API Docs: https://developers.google.com/docs/api/reference/rest

### Common Questions

**Q: Do I need LibreOffice?**
A: No! Uses Google Docs API only.

**Q: Can I use my personal Gmail for the service account?**
A: No. Must create a service account in Google Cloud Console.

**Q: How do I update the template?**
A: Just edit the Google Doc directly. Changes apply immediately.

**Q: Are there usage limits?**
A: Yes, but quotas are very high. You can generate ~1M quotations/day.

**Q: Is the data secure?**
A: Yes. Service account has minimal permissions, temp docs are deleted immediately.

**Q: Can I have multiple templates?**
A: Currently one template per system. Future enhancement will support multiple templates.

---

## ✅ Success Checklist

Before going live:
- [ ] Service account created in GCP
- [ ] Drive API enabled
- [ ] Docs API enabled
- [ ] JSON key downloaded
- [ ] Template created in Google Docs
- [ ] Template shared with service account (Editor access)
- [ ] JSON key uploaded in Settings
- [ ] Template URL pasted in Settings
- [ ] Test quotation created
- [ ] PDF download works
- [ ] DOCX download works
- [ ] Email sending works
- [ ] Placeholders replaced correctly
- [ ] Audit logs working
- [ ] No errors in Django logs

---

**🎉 You're ready to generate quotations with Google Docs API!**
