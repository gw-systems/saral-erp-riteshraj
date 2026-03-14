# Adobe Sign Integration - Implementation Summary

## Overview
Complete Adobe Sign e-signature integration for ERP system with enhanced workflow and improved signature placement via document templates.

## Key Enhancements Over Original

### 1. Template-Based Signature Placement
**Problem Solved**: Manual signature block placement is error-prone and inconvenient

**Solution**: Document Templates with pre-placed Adobe Text Tags
- Backoffice selects template instead of manually placing fields
- Templates have signature fields pre-configured using Adobe Text Tags
- Eliminates human error in field placement
- Faster document preparation

### 2. Enhanced Data Models
- **DocumentTemplate**: Reusable templates with predefined signature fields
- **AdobeSignSettings**: Singleton settings model for director info
- **AgreementEvent**: Full audit trail synced from Adobe
- Better status tracking with separate `adobe_status` and `approval_status`
- Improved timestamp tracking (submitted_at, approved_at, sent_at, completed_at)

### 3. Improved Workflow
- Clearer state machine for agreement lifecycle
- Helper methods: `can_edit()`, `can_submit_for_approval()`, `can_approve()`
- Better rejection workflow with structured reasons
- Document replacement for rejected agreements

### 4. Better API Service Layer
- Enhanced error handling and logging
- Retry logic for transient failures
- Support for reminders and cancellations
- Participant status tracking
- Configuration validation

## Architecture

```
integrations/adobe_sign/
├── __init__.py
├── apps.py
├── models.py              # Enhanced models with templates
├── admin.py               # Django admin interface
├── forms.py               # Enhanced forms
├── views.py               # Workflow views (TO BE CREATED)
├── urls.py                # URL routing
├── exceptions.py          # Custom exceptions
├── services/
│   ├── __init__.py
│   ├── adobe_auth.py      # Authentication service
│   ├── adobe_documents.py # Document upload service
│   └── adobe_agreements.py # Agreement management service
├── management/
│   └── commands/          # Management commands (TO BE CREATED)
├── migrations/            # Database migrations (TO BE CREATED)
├── templates/
│   └── adobe_sign/        # HTML templates (TO BE CREATED)
└── static/
    └── adobe_sign/        # CSS/JS assets (TO BE CREATED)
```

## Workflow

### Backoffice Flow
1. **Select Template** → Choose from predefined templates OR upload custom document
2. **Configure Agreement** → Set client name, email, CC, signing flow
3. **Submit for Approval** → Sends to director (Vivek Tiwari) for review
4. **If Rejected** → Replace document and resubmit

### Director (Admin) Flow
1. **Review Pending** → See all agreements awaiting approval
2. **Review Agreement** → View document, check details
3. **Sign (if needed)** → E-sign if flow_type = 'director_then_client'
4. **Approve** → Send to client
5. **Or Reject** → Send back to backoffice with specific corrections needed

### Signing Flows
- **director_then_client**: Director signs first, then client (sequential)
- **client_only**: Client only signs (director already signed physically)
- **parallel**: Both sign simultaneously
- **custom**: Custom order defined by admin

## Configuration Required

### Environment Variables (.env)
```bash
# Adobe Sign API Configuration
ADOBE_SIGN_INTEGRATION_KEY=your_integration_key_here
ADOBE_SIGN_BASE_URL=https://api.in1.adobesign.com/api/rest/v6
ADOBE_SIGN_DIRECTOR_EMAIL=vivek.tiwari@godamwale.com
```

### Django Settings (minierp/settings.py)
```python
# Adobe Sign Integration
ADOBE_SIGN_INTEGRATION_KEY = config('ADOBE_SIGN_INTEGRATION_KEY', default='')
ADOBE_SIGN_BASE_URL = config('ADOBE_SIGN_BASE_URL', default='https://api.in1.adobesign.com/api/rest/v6')
ADOBE_SIGN_DIRECTOR_EMAIL = config('ADOBE_SIGN_DIRECTOR_EMAIL', default='vivek.tiwari@godamwale.com')
```

## How Templates Work

### Adobe Text Tags
Adobe Sign uses text tags in PDFs to define signature fields:
- `{{DirectorSig_es_:signer1:signature}}` - Director signature field
- `{{DirectorDate_es_:signer1:datefield}}` - Director date field
- `{{ClientSig_es_:signer2:signature}}` - Client signature field
- `{{ClientDate_es_:signer2:datefield}}` - Client date field

### Creating Templates
1. Create PDF with text tags using Word/design tool
2. Upload as DocumentTemplate
3. Define field_definitions JSON:
```json
{
  "director_signature": "{{DirectorSig_es_:signer1:signature}}",
  "director_date": "{{DirectorDate_es_:signer1:datefield}}",
  "client_signature": "{{ClientSig_es_:signer2:signature}}",
  "client_date": "{{ClientDate_es_:signer2:datefield}}"
}
```
4. Set default_signer_order:
```json
[
  {"role": "Director", "order": 1},
  {"role": "Client", "order": 2}
]
```

### Using Templates
1. Backoffice selects template when creating agreement
2. System automatically uses template file
3. Adobe Sign processes text tags → places signature fields
4. No manual field placement needed!

## Database Models

### DocumentTemplate
- Pre-configured document with text tags
- Reusable across multiple agreements
- Supports different document types (NDA, Service Agreement, etc.)

### Document
- Individual uploaded document
- Can be linked to template
- Stores file, metadata, hash

### AdobeAgreement
- Main agreement record
- Tracks internal approval status + Adobe status
- Links to Document and Signers
- Full workflow state tracking

### Signer
- Participant in agreement
- Order-based signing
- Role labels (Director, Client, etc.)
- Status tracking

### AgreementEvent
- Audit trail from Adobe
- Every action tracked
- Synced from Adobe API

### AdobeSignSettings
- Singleton configuration
- Director details
- Default settings
- Notification preferences

## API Services

### AdobeAuthService
- Integration Key authentication
- Header generation
- Configuration validation

### AdobeDocumentService
- Upload transient documents (7-day expiry)
- Upload library documents (permanent templates)
- DOCX to PDF conversion

### AdobeAgreementService
- Create agreements in AUTHORING state
- Send agreements (AUTHORING → IN_PROCESS)
- Get status, details, events
- Get authoring/signing/viewing URLs
- Download signed documents
- Cancel agreements
- Send reminders

## Remaining Tasks

### 1. Views (views.py)
- Dashboard view
- Template CRUD views
- Agreement workflow views (create, edit, submit, review, approve, reject)
- AJAX endpoints (sync status, send reminder, cancel)
- Settings view

### 2. Templates (HTML)
- Dashboard (list all agreements)
- Template management pages
- Agreement create/edit forms
- Review page with embedded Adobe viewer
- Detail page with events timeline
- Settings page

### 3. Management Commands
- sync_agreement_statuses: Sync all pending agreements from Adobe
- download_signed_documents: Download all completed agreements
- cleanup_old_transient_docs: Cleanup tracking

### 4. Migrations
- Initial migration for all models
- Create default AdobeSignSettings instance

### 5. Static Assets
- CSS for custom styling
- JavaScript for interactive features
- Icons and images

### 6. Integration with ERP
- Add to INSTALLED_APPS
- Add URL include in main urls.py
- Add card to integrations hub
- Update admin dashboard view with statistics

### 7. Testing
- Unit tests for services
- Integration tests for workflow
- API mocking for tests

## Next Steps

1. Create views.py with all view functions
2. Create HTML templates
3. Create management commands
4. Run migrations
5. Register in INSTALLED_APPS
6. Add to integrations hub
7. Test complete workflow
8. Document user guide

## Benefits

### For Backoffice
- ✅ Select template → Fill details → Submit (3 steps instead of 5+)
- ✅ No manual signature field placement
- ✅ Clear rejection feedback
- ✅ Easy document replacement

### For Director (Vivek Tiwari)
- ✅ One-click review and approve
- ✅ E-sign directly in browser
- ✅ Reject with structured feedback
- ✅ Full audit trail

### For System
- ✅ Fewer errors in signature placement
- ✅ Faster document preparation
- ✅ Complete audit trail
- ✅ Status tracking synchronized with Adobe
- ✅ Automated reminders
- ✅ Centralized template management

## Notes

- All agreements are created under Director's Adobe Sign account
- No On-Behalf-Of (OBO) complexity for basic workflow
- Templates can be created/edited by admin only
- Backoffice has limited permissions (create, edit drafts)
- Director has full control (approve, reject, cancel)
