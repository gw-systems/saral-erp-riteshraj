# Adobe Sign E-Signature Workflow Audit Report

**Audit Date**: 2026-02-08
**Auditor**: System Analysis
**Scope**: Complete agreement e-signing process from backoffice to director to client

---

## Executive Summary

This audit examines the Adobe Sign integration workflow for the ERP system, focusing on the complete lifecycle of e-signature agreements from creation by backoffice staff through director approval to client signing.

**Overall Assessment**: The system has a well-structured workflow but contains **12 critical issues**, **8 logical flaws**, **5 data inconsistencies**, and **9 process gaps** that need immediate attention.

---

## Table of Contents

1. [Workflow Overview](#workflow-overview)
2. [Critical Issues](#critical-issues)
3. [Logical Flaws](#logical-flaws)
4. [Data Inconsistencies](#data-inconsistencies)
5. [Process Gaps](#process-gaps)
6. [Security Concerns](#security-concerns)
7. [Recommendations](#recommendations)

---

## Workflow Overview

### Current Process Flow

```
STEP 1: BACKOFFICE CREATES AGREEMENT
├─ Upload PDF document
├─ Select project (MANDATORY, WAAS only)
├─ Auto-fill: client name, location, sales person, billing amounts
├─ Fill agreement type, category, GST status
├─ Enter client email, CC emails
├─ Choose signing flow (Director→Client OR Client Only)
├─ Place signature fields on PDF using canvas
├─ Save as DRAFT
└─ Submit for approval → PENDING_APPROVAL

STEP 2: DIRECTOR REVIEWS AGREEMENT
├─ View pending agreements
├─ Review agreement details
├─ View PDF document
├─ Approve OR Reject
│
├─ IF APPROVE:
│  ├─ Agreement sent to Adobe Sign (AUTHORING → IN_PROCESS)
│  ├─ Status: APPROVED_SENT
│  └─ Adobe status: OUT_FOR_SIGNATURE
│
└─ IF REJECT:
   ├─ Enter rejection reason + notes
   ├─ Status: REJECTED
   └─ Back to backoffice for corrections

STEP 3A: DIRECTOR SIGNS (if flow_type = 'director_then_client')
├─ Director receives Adobe Sign email
├─ Opens signing URL
├─ Places electronic signature
├─ Adobe sends to client automatically
└─ Status remains: OUT_FOR_SIGNATURE

STEP 3B: CLIENT ONLY (if flow_type = 'client_only')
├─ Agreement sent directly to client
└─ Director signature not required

STEP 4: CLIENT SIGNS
├─ Client receives Adobe Sign email
├─ Opens signing URL
├─ Places electronic signature
├─ Adobe marks as COMPLETED
└─ Status: COMPLETED

STEP 5: COMPLETION
├─ All signatures collected
├─ Adobe status: SIGNED/COMPLETED
├─ Signed PDF available for download
└─ Agreement marked COMPLETED
```

---

## Critical Issues

### 🔴 CRITICAL #1: Signature Field Placement Lost After Submit

**Location**: `views.py:agreement_submit()` (line 476-620)

**Issue**: When backoffice submits an agreement for approval, the signature fields placed in the UI are parsed from `signature_field_data` and formatted for Adobe Sign. However, these fields are **NOT SENT** to Adobe Sign because:

```python
# Line 581-590 in views.py
adobe_agreement_id = AdobeAgreementService.create_agreement_for_authoring(
    transient_document_id=transient_id,
    agreement_name=agreement.agreement_name,
    signers_data=signers_data,
    ccs=agreement.get_cc_list(),
    message=agreement.agreement_message,
    days_until_signing_deadline=agreement.days_until_signing_deadline,
    reminder_frequency=agreement.reminder_frequency,
    form_fields=form_fields  # ← Fields are passed BUT...
)
```

**Then in** `adobe_agreements.py:create_agreement_for_authoring()` (line 98-104):

```python
# IMPORTANT: Do NOT add form fields when creating in AUTHORING state
# Adobe Sign does not support formFieldLayerTemplates for AUTHORING agreements
# Signature fields must be added through the authoring UI or when sending
# if form_fields:
#     payload["formFieldLayerTemplates"] = [{
#         "formFields": form_fields
#     }]
```

**Impact**:
- Backoffice spends time placing signature fields in UI
- **Fields are completely ignored** when creating agreement in Adobe Sign
- Director must manually place signature fields again in Adobe Sign UI
- **OR** fields are missing when sent to client, causing signing failures

**Severity**: 🔴 **CRITICAL** - Core functionality broken

**Root Cause**: Adobe Sign API limitation - AUTHORING state does not support `formFieldLayerTemplates`

---

### 🔴 CRITICAL #2: No Signature Field Validation Before Submit

**Location**: `views.py:agreement_submit()` + `forms.py`

**Issue**: Backoffice can submit agreement for approval **without placing any signature fields**.

**Evidence**:
```python
# agreement_submit() does not check if signature_field_data exists or is valid
# Line 540 in views.py:
form_fields = None
if agreement.signature_field_data:
    # Parse fields...
    # But NO ERROR if signature_field_data is empty/None!
```

**Impact**:
- Agreement reaches director with no signature fields
- Director approves and sends to client
- Client opens Adobe Sign and sees **no signature boxes** = cannot sign
- Agreement stuck, must be cancelled and recreated
- Wastes everyone's time

**Severity**: 🔴 **CRITICAL** - Process failure

---

### 🔴 CRITICAL #3: Director Cannot See Signature Field Placement

**Location**: `templates/adobe_sign/agreement_review.html` + `views.py:agreement_review()`

**Issue**: When director reviews agreement before approval, they can:
1. View agreement details
2. View PDF document (as static file)
3. See signer list

**BUT**: Director **CANNOT SEE** where signature fields were placed by backoffice.

**Evidence**:
```html
<!-- agreement_review.html line 95-112 -->
<div class="text-center">
    <!-- Just shows PDF file link, not a viewer with signature field overlay -->
    <a href="{{ agreement.document.file.url }}" target="_blank">View Document</a>
</div>
```

**Impact**:
- Director approves agreement blindly
- No way to verify if signature fields are correctly placed
- No way to verify if fields match the signing flow
- Quality control impossible

**Severity**: 🔴 **CRITICAL** - No oversight/quality control

---

### 🔴 CRITICAL #4: Duplicate Agreement Creation in Adobe Sign

**Location**: `views.py:agreement_add()` (line 293-373) AND `views.py:agreement_submit()` (line 476-620)

**Issue**: Agreement is created in Adobe Sign **TWICE**:

1. **First time** in `agreement_add()` when action is 'draft' or 'submit' (line 293-373)
2. **Second time** in `agreement_submit()` when backoffice clicks Submit (line 489-590)

**Evidence**:

```python
# In agreement_add() - Line 293-373
if action in ['draft', 'submit']:
    try:
        # Upload document to Adobe
        transient_id = AdobeDocumentService.upload_transient_document(...)
        # Create agreement in Adobe Sign
        adobe_agreement_id = AdobeAgreementService.create_agreement_for_authoring(...)
        agreement.adobe_agreement_id = adobe_agreement_id
        agreement.save()
```

```python
# In agreement_submit() - Line 489-590
try:
    # Upload document to Adobe AGAIN
    transient_id = AdobeDocumentService.upload_transient_document(...)
    # Create agreement in Adobe Sign AGAIN
    adobe_agreement_id = AdobeAgreementService.create_agreement_for_authoring(...)
    agreement.adobe_agreement_id = adobe_agreement_id  # Overwrites previous ID!
```

**Impact**:
- First agreement created in Adobe Sign becomes **orphaned** (never deleted)
- Second agreement overwrites `adobe_agreement_id` field
- **Data leakage** - orphaned agreements contain sensitive client data
- **Cost implications** - Adobe Sign may charge per agreement created
- Confusion in Adobe Sign dashboard

**Severity**: 🔴 **CRITICAL** - Data leakage + cost implications

---

### 🔴 CRITICAL #5: No Check if Agreement Already Submitted

**Location**: `views.py:agreement_submit()` (line 476-620)

**Issue**: The `can_submit_for_approval()` check only validates status:

```python
# models.py line 442-444
def can_submit_for_approval(self):
    return self.approval_status in ['DRAFT', 'REJECTED']
```

**BUT**: Does NOT check if `adobe_agreement_id` already exists.

**Impact**:
- If backoffice clicks "Submit" button multiple times (accidental double-click or refresh)
- Each click creates a **NEW agreement in Adobe Sign**
- Previous agreement IDs are overwritten and lost
- Multiple orphaned agreements in Adobe Sign

**Severity**: 🔴 **CRITICAL** - Data integrity issue

---

### 🔴 CRITICAL #6: Director Sign Flow Broken

**Location**: `views.py:director_sign()` (line 828-881)

**Issue**: The `director_sign()` view attempts to:
1. Send agreement (AUTHORING → IN_PROCESS) if not already sent
2. Get signing URL for director
3. Display embedded signing interface

**But there's a logical flaw**:

```python
# Line 849-858
if agreement.adobe_status == 'AUTHORING':
    AdobeAgreementService.send_agreement(agreement.adobe_agreement_id)
    # Updates status to OUT_FOR_SIGNATURE
    agreement.approve(user=request.user)  # ← Sets approval_status to APPROVED_SENT
    agreement.adobe_status = 'OUT_FOR_SIGNATURE'
    agreement.sent_at = timezone.now()
    agreement.save()
```

**Problem**: This **auto-approves** the agreement when director tries to sign, **bypassing the explicit approval step**.

**Expected Flow**:
1. Director reviews agreement → clicks "Approve"
2. Agreement sent to Adobe Sign
3. Director receives email from Adobe Sign → clicks signing link
4. Director signs in Adobe Sign interface
5. Adobe Sign sends to client

**Actual Flow**:
1. Director clicks "Sign" button (bypassing "Approve" button)
2. Agreement auto-approved and sent
3. Director signs
4. BUT: No explicit approval recorded!

**Impact**:
- Approval workflow circumvented
- No clear audit trail of who approved vs who signed
- `approved_by` and `approved_at` fields may be inconsistent

**Severity**: 🔴 **CRITICAL** - Workflow bypass

---

### 🔴 CRITICAL #7: Missing Adobe Agreement ID Handling

**Location**: Multiple locations

**Issue**: Many operations fail silently or show confusing errors if `adobe_agreement_id` is missing.

**Examples**:

1. **agreement_review.html** shows error: "Cannot Send Agreement - Adobe Agreement ID missing" but **still shows Approve/Reject buttons** (line 30-45)

2. **agreement_approve()** returns JSON error but frontend may not handle it properly (line 772)

3. **send_to_client()** can be called even if `adobe_agreement_id` is None (line 896)

**Impact**:
- Confusing user experience
- Director may click "Approve" and get cryptic error
- Frontend may not show error properly
- Agreement stuck in limbo state

**Severity**: 🔴 **CRITICAL** - User experience failure

---

### 🔴 CRITICAL #8: No Transaction Management

**Location**: `views.py:agreement_add()`, `views.py:agreement_submit()`

**Issue**: When creating/submitting agreement, multiple database operations occur without atomic transaction:

```python
# In agreement_add() - Line 193-282
document = Document.objects.create(...)  # 1. Create document
agreement = form.save(commit=False)      # 2. Create agreement
agreement.save()                         # 3. Save agreement
# 4. Upload to Adobe Sign (external API call)
adobe_agreement_id = AdobeAgreementService.create_agreement_for_authoring(...)
agreement.adobe_agreement_id = adobe_agreement_id  # 5. Update agreement
agreement.save()                         # 6. Save again
# 7. Create signers
for s in signers_data:
    Signer.objects.create(...)
```

**Problem**: If Adobe API call fails at step 4:
- Document already created ✓
- Agreement already created ✓
- But `adobe_agreement_id` = None
- Signers not created
- **Partial data in database**
- No rollback

**Impact**:
- Orphaned documents in database
- Orphaned agreements in database
- Database clutter
- Confusion about agreement state

**Severity**: 🔴 **CRITICAL** - Data integrity

---

### 🔴 CRITICAL #9: Tracking Fields Not Updated Consistently

**Location**: `models.py` tracking fields + `views.py` update logic

**Issue**: The tracking fields (Google Sheet replication) are not updated consistently:

**Fields**:
- `task_undertaken_by` - Set only in `agreement_submit()` (line 597)
- `sent_date_director` - Set only in `agreement_submit()` (line 599)
- `sent_date_client_vendor` - Set only in `send_to_client()` (line 925)
- `to_email` / `cc_email_list` - Set in `agreement_add()` and `send_to_client()`

**Problems**:

1. **If agreement created but not submitted**: `task_undertaken_by` = NULL
2. **If director approves directly (not through submit)**: `sent_date_director` = NULL
3. **If flow is director_then_client**: `sent_date_client_vendor` = NULL because `send_to_client()` is never called (Adobe sends automatically after director signs)
4. **Email fields can become out of sync** if director updates emails before sending

**Impact**:
- Tracking data incomplete
- Cannot generate accurate reports
- Google Sheet sync will have missing data
- Management cannot track who did what when

**Severity**: 🔴 **CRITICAL** - Reporting failure

---

### 🔴 CRITICAL #10: No Webhook Handler for Adobe Sign Events

**Location**: Missing implementation

**Issue**: Adobe Sign sends webhooks when events occur:
- Director signs
- Client signs
- Agreement completed
- Agreement expired
- Agreement rejected

**Current Implementation**: NONE

**Evidence**: No webhook URL handler in `urls.py`, no webhook processing in `views.py`

**Impact**:
- System does NOT know when director signs
- System does NOT know when client signs
- System does NOT know when agreement is completed
- **Manual sync required** - user must click "Sync Status" button
- Status can be hours/days out of date
- No automated notifications to backoffice
- No automated next-step triggers

**Severity**: 🔴 **CRITICAL** - System not real-time

---

### 🔴 CRITICAL #11: Signature Field Data Format Mismatch

**Location**: `views.py:agreement_submit()` (line 539-576)

**Issue**: The JavaScript frontend sends signature field data in one format, but the backend expects a different format.

**Frontend sends**:
```javascript
{
    "name": "signature_1",
    "inputType": "SIGNATURE",
    "recipientIndex": 0,
    "required": true,
    "locations": [{
        "pageNumber": 1,
        "top": 100,
        "left": 50,
        "width": 150,
        "height": 50
    }]
}
```

**Backend parses** (line 544-575):
```python
for field in signature_fields:
    recipient_index = field.get('recipientIndex', 0)
    assignee = f"SIGNER_{recipient_index}"  # ← Incorrect format!

    locations = field.get('locations', [])
    location = locations[0]

    adobe_field = {
        "assignee": assignee,  # Should be "SIGNER_0" but Adobe expects participant set index
        # ...
    }
```

**Problem**: Adobe Sign expects `recipientIndex` to match the **participantSetsInfo array index**, but the code uses `recipientIndex` from frontend which may not match.

**Example**:
- Frontend: Director = recipientIndex 0, Client = recipientIndex 1
- Adobe Sign: participantSetsInfo[0] = Director, participantSetsInfo[1] = Client
- This works IF the order matches...

**BUT for `client_only` flow**:
- Frontend might send: Client = recipientIndex 0
- Adobe Sign: participantSetsInfo[0] = Client
- Code creates: `assignee = "SIGNER_0"` ✓ Correct by accident

**BUT for `director_then_client` flow**:
- If frontend accidentally sends Client = recipientIndex 0 instead of 1
- Code creates: `assignee = "SIGNER_0"` ✗ Wrong! Should be SIGNER_1
- **Director's signature field assigned to client!**

**Impact**:
- Signature fields may be assigned to wrong signer
- Client sees director's signature field
- Director sees client's signature field
- Signing fails or gets confused

**Severity**: 🔴 **CRITICAL** - Signing logic broken

---

### 🔴 CRITICAL #12: Project Field Auto-Population Race Condition

**Location**: `views.py:agreement_add()` (line 214-263)

**Issue**: When project is selected, the code fetches `ProjectCard` and `StorageRate` to auto-populate fields:

```python
# Line 232-256
try:
    from operations.models_projectcard import ProjectCard, StorageRate

    project_card = ProjectCard.objects.filter(
        project=project,
        is_active=True
    ).first()

    if project_card:
        storage_rate = StorageRate.objects.filter(
            project_card=project_card,
            rate_for='client'
        ).first()

        if storage_rate:
            agreement.minimum_billable_area = storage_rate.minimum_billable_area
            agreement.monthly_billable_amount = storage_rate.monthly_billable_amount
except Exception as e:
    logger.warning(f"Could not fetch project card data: {e}")
    # ← Exception silently caught, fields remain NULL
```

**Problems**:

1. **Silent failure**: If `ProjectCard` or `StorageRate` query fails, exception is caught and logged as warning, but user is NOT notified
2. **Data inconsistency**: Agreement created with NULL billing amounts even though project has valid data
3. **Validation bypass**: Form does NOT validate that these fields were successfully populated
4. **Timing issue**: If `ProjectCard` is not marked `is_active=True` yet, query returns None

**Impact**:
- Agreements created with missing financial data
- Billing amounts not tracked correctly
- Reports show NULL values for critical billing fields
- No alert to user that auto-population failed

**Severity**: 🔴 **CRITICAL** - Data integrity for financial tracking

---

## Logical Flaws

### ⚠️ FLAW #1: Inconsistent Flow Type Handling

**Location**: Multiple locations

**Issue**: The system supports 4 flow types in `models.py`:
```python
FLOW_TYPE_CHOICES = [
    ('director_then_client', 'Director Signs First, Then Client'),
    ('client_only', 'Client Only (Director Already Signed Physically)'),
    ('parallel', 'Both Sign Simultaneously'),
    ('custom', 'Custom Signing Order'),
]
```

**But** `forms.py:AgreementCreateForm` only shows 2 options:
```python
SIMPLIFIED_FLOW_CHOICES = [
    ('director_then_client', 'Director signs first, then Client'),
    ('client_only', 'Client Only'),
]
```

**Problems**:
1. **'parallel' and 'custom' flows are defined but not accessible** through UI
2. **Code exists to handle 'parallel'** in `agreement_submit()` (line 523-537) but user cannot select it
3. **Dead code** - parallel signing logic never executes
4. **Confusion** - why define 4 options if only 2 are used?

**Impact**:
- Wasted development effort on unused features
- Code maintenance burden
- Future developers confused by dead code

**Severity**: ⚠️ **MODERATE** - Code quality issue

---

### ⚠️ FLAW #2: approval_status vs adobe_status Confusion

**Location**: `models.py` + all views

**Issue**: Two status fields track different things but can become desynchronized:

**`approval_status`** (internal workflow):
- DRAFT
- PENDING_APPROVAL
- REJECTED
- APPROVED_SENT
- COMPLETED
- CANCELLED

**`adobe_status`** (Adobe Sign API):
- AUTHORING
- OUT_FOR_SIGNATURE
- SIGNED
- COMPLETED
- CANCELLED
- etc. (15+ options)

**Problem**: State machine not clearly defined.

**Example Scenario**:
1. Agreement approved → `approval_status=APPROVED_SENT`, `adobe_status=OUT_FOR_SIGNATURE`
2. Director signs → Adobe changes to `adobe_status=SIGNED`
3. BUT: Local `approval_status` still `APPROVED_SENT` (not updated)
4. Client signs → Adobe changes to `adobe_status=COMPLETED`
5. Sync runs → `approval_status=COMPLETED`, `adobe_status=COMPLETED`

**Between steps 2-5**: Status is misleading! Says "Approved and Sent" but director already signed.

**Impact**:
- Confusing status displays
- Incorrect filtering in dashboards
- Audit trail unclear

**Severity**: ⚠️ **MODERATE** - User confusion

---

### ⚠️ FLAW #3: Rejection Workflow Incomplete

**Location**: `views.py:agreement_reject()` + `templates/adobe_sign/agreement_reject.html`

**Issue**: When director rejects agreement:

```python
# Line 813 in views.py
agreement.reject(reason=reason, notes=notes, user=request.user)
```

**This**:
1. Sets `approval_status = 'REJECTED'`
2. Sets `rejection_reason` and `rejection_notes`
3. Saves agreement

**But does NOT**:
1. **Notify backoffice** who created the agreement
2. **Cancel agreement in Adobe Sign** (if already created)
3. **Clear signature field data** (old fields may not match new document)
4. **Create an audit event** in `AgreementEvent` table

**Impact**:
- Backoffice not notified of rejection - must manually check dashboard
- Agreement remains in Adobe Sign as AUTHORING (orphaned)
- Old signature fields persist when agreement is re-edited
- No audit trail of rejection event

**Severity**: ⚠️ **MODERATE** - Workflow incomplete

---

### ⚠️ FLAW #4: Document Replace Doesn't Clear Adobe Agreement

**Location**: `views.py:replace_document()` (line 623-671)

**Issue**: When backoffice replaces document for rejected agreement:

```python
# Line 651-655
agreement.document = new_doc
agreement.adobe_agreement_id = None  # ← Clears ID
agreement.adobe_status = 'DRAFT'
agreement.save()
```

**Problem**: Old agreement in Adobe Sign is NOT deleted/cancelled.

**What happens**:
1. Agreement rejected with Adobe ID = "ABC123"
2. Backoffice replaces document
3. Local: `adobe_agreement_id = None`
4. Adobe Sign: Agreement "ABC123" still exists in AUTHORING state
5. New submission creates agreement "XYZ789"
6. **Old agreement "ABC123" orphaned forever**

**Impact**:
- Orphaned agreements accumulate in Adobe Sign
- Data leakage - old documents with sensitive data remain accessible
- Adobe Sign storage bloat
- Potential cost implications

**Severity**: ⚠️ **MODERATE** - Data leakage

---

### ⚠️ FLAW #5: CC Emails Not Validated

**Location**: `forms.py:AgreementCreateForm` + `models.py`

**Issue**: CC emails field accepts comma-separated emails as text:

```python
# forms.py
'cc_emails': forms.Textarea(attrs={
    'class': 'form-control border border-gray-300 rounded-md',
    'rows': 2,
    'placeholder': 'email1@example.com, email2@example.com'
})
```

**But NO validation**:
- Are emails properly formatted?
- Are there duplicates?
- Is client_email also in CC list? (should it be?)
- Is director_email in CC list? (should it be?)

**Problems**:
1. User types: `john@example.com, invalid-email, jane@example.com`
2. Form accepts it
3. Agreement created successfully
4. Adobe Sign API call fails because "invalid-email" is not valid
5. Agreement stuck

**Impact**:
- Agreement creation fails with confusing error
- Backoffice must debug and fix
- Time wasted

**Severity**: ⚠️ **MODERATE** - User experience issue

---

### ⚠️ FLAW #6: No Handling for Adobe Sign API Errors

**Location**: All `AdobeAgreementService` calls in `views.py`

**Issue**: Adobe Sign API calls can fail for many reasons:
- Network timeout
- Invalid credentials
- Rate limiting
- Invalid email addresses
- Document too large
- Unsupported file format
- etc.

**Current error handling**:
```python
try:
    adobe_agreement_id = AdobeAgreementService.create_agreement_for_authoring(...)
except Exception as e:
    logger.error(f"Error creating agreement in Adobe Sign: {e}")
    messages.error(request, f'Agreement saved as draft but failed to create in Adobe Sign: {str(e)}')
    return redirect('adobe_sign:agreement_detail', agreement_id=agreement.id)
```

**Problems**:
1. **Generic exception catch** - doesn't differentiate between error types
2. **Error message shown to user contains technical details** - `{str(e)}` may expose sensitive info
3. **No retry logic** - transient errors (network, timeout) could succeed on retry
4. **No categorization** - user doesn't know if error is their fault or system issue

**Impact**:
- Confusing error messages to users
- No guidance on how to fix
- Technical details exposed
- No automatic recovery

**Severity**: ⚠️ **MODERATE** - User experience + security

---

### ⚠️ FLAW #7: Template System Implemented But Not Used

**Location**: `models.py:DocumentTemplate` + `views.py:template_*` + `forms.py:DocumentUploadForm`

**Issue**: A complete template system exists:
- `DocumentTemplate` model with template files, field definitions, default signer order
- CRUD views for templates (list, create, edit, delete)
- Form field to select template

**But**: Templates are **NOT USED** in the main workflow!

**Evidence**:
- `agreement_add.html` shows templates in context: `'templates': DocumentTemplate.objects.filter(is_active=True)`
- But template selection is **NOT rendered** in the form
- Template field definitions (`field_definitions` JSON) are never used
- Default signer order (`default_signer_order` JSON) is never used

**Impact**:
- Dead code / unused feature
- Wasted development effort
- Database bloat if templates created
- Confusion for future developers

**Severity**: ⚠️ **MODERATE** - Code quality

---

### ⚠️ FLAW #8: Signer Records Created But Not Synced

**Location**: `models.py:Signer` + `views.py:agreement_submit()`

**Issue**: When agreement submitted, signer records are created locally:

```python
# Line 603-613 in views.py
for s in signers_data:
    Signer.objects.create(
        agreement=agreement,
        name=s['name'],
        email=s['email'],
        role=s['role'],
        order=s['order'],
        is_director=(s['email'] == director_email),
        is_client=(s['email'] == agreement.client_email)
    )
```

**But**: Signer status fields are NEVER updated:
- `status` - remains 'NOT_YET_VISIBLE'
- `signed_at` - remains NULL
- `signing_url` - remains empty

**Why?** No webhook handler to update signer status when Adobe sends events.

**Impact**:
- Signer status always shows "Not Yet Visible"
- Cannot track who signed when
- Audit trail incomplete
- Dashboard shows incorrect status

**Severity**: ⚠️ **MODERATE** - Feature incomplete

---

## Data Inconsistencies

### 📊 INCONSISTENCY #1: Duplicate Email Fields

**Location**: `models.py:AdobeAgreement`

**Issue**: Email tracking is duplicated:

```python
# Primary fields (used for Adobe Sign API)
client_email = models.EmailField()
cc_emails = models.TextField(blank=True)

# Tracking fields (mirror for Google Sheet sync)
to_email = models.EmailField(blank=True)
cc_email_list = models.TextField(blank=True)
```

**Problems**:
1. `client_email` and `to_email` should always match - but can diverge
2. `cc_emails` and `cc_email_list` should always match - but can diverge
3. Code sets both in some places, only one in other places
4. Confusion about which field to use for display/reports

**Evidence of divergence**:
- `agreement_add()` sets both (line 278-279)
- `send_to_client()` sets both (line 928-929)
- But `agreement_edit()` does NOT sync them!

**Impact**:
- Reports may show different emails depending on which field is queried
- Data integrity issues
- Confusion

**Severity**: 📊 **MODERATE** - Data quality

---

### 📊 INCONSISTENCY #2: agreement_name Auto-Generation Inconsistent

**Location**: `views.py:agreement_add()` (line 214-269)

**Issue**: Agreement name is auto-generated from project:

```python
# If project selected (line 228-229)
agreement.agreement_name = f"{project.code} - {agreement.client_name}"

# If no project (line 266-269)
from django.utils import timezone
date_str = timezone.now().strftime('%Y-%m-%d')
agreement.agreement_name = f"Agreement - {date_str}"
```

**But**: Project is **REQUIRED** in the form! So the "no project" branch should never execute.

```python
# forms.py line 91-104
project = forms.ModelChoiceField(
    queryset=...,
    required=True,  # ← REQUIRED!
    ...
)
```

**Problems**:
1. Dead code - "no project" branch never executes
2. Inconsistent naming pattern
3. What if `project.code` is empty? Agreement name becomes " - ClientName"

**Impact**:
- Code confusion
- Potential empty/malformed agreement names

**Severity**: 📊 **LOW** - Code quality

---

### 📊 INCONSISTENCY #3: File Size Limits Different in Forms vs Models

**Location**: `forms.py` vs `models.py`

**Issue**:

**Form validation** (forms.py line 79-80):
```python
if file.size > 25 * 1024 * 1024:  # 25 MB limit
    raise forms.ValidationError('File size must be under 25 MB')
```

**Template form** (forms.py line 46-47):
```python
if file.size > 10 * 1024 * 1024:  # 10 MB limit
    raise forms.ValidationError('Template file size must be under 10 MB')
```

**Models** (models.py):
```python
# No file size validation at model level!
file = models.FileField(upload_to=document_upload_path)
```

**Problems**:
1. Template limit (10 MB) different from document limit (25 MB) - why?
2. No explanation for difference
3. Model doesn't enforce any limit - validation only in forms
4. Direct model.save() bypasses validation

**Impact**:
- Confusing limits for users
- Inconsistent behavior
- Large files can be saved if form validation bypassed

**Severity**: 📊 **LOW** - User confusion

---

### 📊 INCONSISTENCY #4: Timestamp Fields Not All Set

**Location**: `models.py:AdobeAgreement` timestamps

**Issue**: Model has 6 timestamp fields:
```python
created_at = models.DateTimeField(auto_now_add=True)  # ✓ Auto-set
updated_at = models.DateTimeField(auto_now=True)      # ✓ Auto-set
submitted_at = models.DateTimeField(null=True, blank=True)  # Set in submit_for_approval()
approved_at = models.DateTimeField(null=True, blank=True)   # Set in approve()
sent_at = models.DateTimeField(null=True, blank=True)       # Set in approve() or director_sign()
completed_at = models.DateTimeField(null=True, blank=True)  # Set in mark_completed()
```

**Problems**:

1. **`sent_at` set in two places**: `approve()` (line 781) and `director_sign()` (line 857)
   - If director uses `director_sign()` instead of `approve()`, `sent_at` is set twice
   - If director uses `approve()`, then signs later, `sent_at` reflects approval time, not actual send time

2. **`completed_at` only set manually** via `mark_completed()` which is only called in `sync_agreement_status()` (line 1059)
   - If sync never runs, `completed_at` remains NULL forever
   - No automated trigger when Adobe sends completion webhook (webhook doesn't exist)

3. **`approved_at` not set if director uses `director_sign()`** instead of explicit approve

**Impact**:
- Timestamps unreliable for audit trail
- Reports show incorrect completion times
- Cannot accurately measure SLA times

**Severity**: 📊 **MODERATE** - Reporting accuracy

---

### 📊 INCONSISTENCY #5: Enum Values Not Validated Against Adobe Sign API

**Location**: `models.py:AGREEMENT_STATUS_CHOICES` + `models.py:SIGNER_STATUS_CHOICES`

**Issue**: Status choices are hardcoded in models but may not match Adobe Sign API responses exactly.

**Example**:
```python
AGREEMENT_STATUS_CHOICES = [
    ('AUTHORING', 'Authoring'),
    ('DRAFT', 'Draft'),
    ('OUT_FOR_SIGNATURE', 'Out for Signature'),
    # ... 15+ more options
]
```

**Problem**: If Adobe Sign API returns a status NOT in this list (e.g., new status added in API update), what happens?

**Code**:
```python
# views.py sync_agreement_status() line 1052
adobe_status = AdobeAgreementService.get_agreement_status(agreement.adobe_agreement_id)
agreement.adobe_status = adobe_status  # ← No validation!
agreement.save()
```

**Django will**:
- Accept any value (CharField with choices is not enforced at DB level)
- But admin form will show "Unknown status"
- Reports/filters may break

**Impact**:
- System breaks if Adobe API changes
- No forward compatibility
- Difficult to debug

**Severity**: 📊 **LOW** - Edge case

---

## Process Gaps

### 🔗 GAP #1: No Notification System

**Issue**: System has no built-in notifications:
- Backoffice does NOT get notified when director rejects
- Director does NOT get notified when backoffice submits for approval
- Backoffice does NOT get notified when agreement is completed
- No email, no in-app notification, no dashboard alert

**Current State**: Users must manually refresh dashboard to see status changes.

**Impact**:
- Slow response times
- Work sits in queue unnoticed
- Poor user experience
- SLA violations

**Severity**: 🔗 **HIGH** - Process efficiency

---

### 🔗 GAP #2: No Bulk Operations

**Issue**: Backoffice cannot:
- Submit multiple agreements at once
- Download multiple signed documents
- Cancel multiple agreements
- Sync multiple agreement statuses

**Current State**: Must handle each agreement one by one.

**Impact**:
- Inefficient for high volume
- Time-consuming
- Error-prone (might miss one)

**Severity**: 🔗 **MODERATE** - Efficiency

---

### 🔗 GAP #3: No Agreement Versioning

**Issue**: When document is replaced (for rejected agreement), old document is lost.

**What happens**:
```python
# replace_document() line 651-652
new_doc = Document(file=new_file, uploaded_by=request.user)
new_doc.save()
agreement.document = new_doc  # ← Old document reference lost!
```

**Old document still exists in database and storage, but:**
- No reference from agreement
- Cannot see what was wrong with old version
- Cannot compare old vs new
- Audit trail incomplete

**Impact**:
- Cannot track document history
- Cannot audit changes
- Compliance risk

**Severity**: 🔗 **MODERATE** - Audit trail

---

### 🔗 GAP #4: No Search/Filter on Dashboard

**Issue**: Dashboard shows recent agreements but no search or advanced filtering:
- Cannot search by client name
- Cannot filter by date range
- Cannot filter by project
- Cannot filter by backoffice user who created
- Cannot sort by any field

**Current State**: Must scroll through all agreements to find specific one.

**Impact**:
- Inefficient for large datasets
- Difficult to find specific agreement
- Poor user experience

**Severity**: 🔗 **MODERATE** - Usability

---

### 🔗 GAP #5: No PDF Preview in Agreement Review

**Issue**: As mentioned in CRITICAL #3, director cannot see PDF with signature field overlay.

**What's missing**:
- PDF.js viewer embedded in review page
- Signature field boxes overlaid on PDF
- Interactive signature field editor for director to adjust if needed

**Current State**: Director must:
1. Download PDF
2. Open in separate app
3. Review
4. Guess where signature fields are

**Impact**:
- No quality control
- Cannot verify signature placement
- Errors not caught before sending

**Severity**: 🔗 **HIGH** - Quality control

---

### 🔗 GAP #6: No Expiration Monitoring

**Issue**: Agreements have expiration dates (`days_until_signing_deadline`), but:
- No alert when agreement is about to expire
- No automated reminder before expiration
- No dashboard showing expiring agreements
- No automated action on expiration

**Impact**:
- Agreements expire silently
- Must recreate expired agreements
- Client experience poor (receives expired link)

**Severity**: 🔗 **MODERATE** - Process monitoring

---

### 🔗 GAP #7: No Integration with Project Module

**Issue**: Agreement is linked to project (`project` foreign key), but:
- Project detail page does NOT show linked agreements
- Cannot navigate from project → agreements
- Cannot see agreement status from project view
- Project completion workflow does NOT check if agreements are signed

**Impact**:
- Disconnected workflows
- Must switch between modules to check status
- Risk of project activation before agreements signed

**Severity**: 🔗 **MODERATE** - Integration

---

### 🔗 GAP #8: No Reporting Dashboard

**Issue**: No built-in reports for:
- Agreements by status
- Average time to complete
- Agreements pending by user
- Monthly agreement volume
- Rejection rate
- Most common rejection reasons

**Current State**: Must export data and analyze in Excel.

**Impact**:
- No performance metrics
- Cannot identify bottlenecks
- Cannot measure improvement

**Severity**: 🔗 **MODERATE** - Management visibility

---

### 🔗 GAP #9: No Automated Testing

**Issue**: No automated tests for:
- Agreement creation workflow
- Approval workflow
- Adobe Sign API integration
- Signature field placement
- Email validation
- Status transitions

**Impact**:
- Regressions not caught
- Changes break existing functionality
- Manual testing required
- High risk of bugs in production

**Severity**: 🔗 **HIGH** - Code quality

---

## Security Concerns

### 🔒 SECURITY #1: No Access Control on Agreement View

**Location**: `views.py:agreement_detail()` (line 945-977)

**Issue**: Check only validates role, not ownership:

```python
if not check_admin_or_backoffice(request.user):
    messages.error(request, 'Access denied')
    return redirect('accounts:dashboard')
```

**Problem**: ANY backoffice user can view ANY agreement, even if created by different user.

**Impact**:
- User A can view agreements created by User B
- Privacy concern - sensitive client data
- Potential data leakage
- No segregation of duties

**Severity**: 🔒 **HIGH** - Data access control

**Recommendation**: Add ownership check:
```python
if not check_admin_or_backoffice(request.user):
    return redirect('accounts:dashboard')

# Allow view if: creator, approver, or admin
is_creator = (agreement.created_by == request.user)
is_approver = (agreement.approved_by == request.user)
is_admin = check_director_or_admin(request.user)

if not (is_creator or is_approver or is_admin):
    messages.error(request, 'Access denied')
    return redirect('adobe_sign:dashboard')
```

---

### 🔒 SECURITY #2: CSRF Protection Missing on Some AJAX Endpoints

**Location**: Multiple `@require_POST` views

**Issue**: Some POST endpoints don't explicitly require CSRF token in AJAX calls.

**Evidence**: Views use `@require_POST` but do not validate CSRF if called via AJAX with JSON body.

**Example**: `send_to_client()` (line 885-938):
```python
@login_required
@require_POST
def send_to_client(request, agreement_id):
    # Parses JSON body
    if request.content_type == 'application/json':
        data = json.loads(request.body)
        # ... processes without explicit CSRF check
```

**Note**: Django automatically validates CSRF for POST, but JSON endpoints may bypass if not properly configured.

**Impact**:
- CSRF attack risk
- Unauthorized actions

**Severity**: 🔒 **MODERATE** - Security vulnerability

**Recommendation**: Ensure all AJAX calls include CSRF token in headers:
```javascript
fetch(url, {
    method: 'POST',
    headers: {
        'X-CSRFToken': getCookie('csrftoken'),
        'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
})
```

---

### 🔒 SECURITY #3: No Rate Limiting on Agreement Creation

**Location**: `views.py:agreement_add()`

**Issue**: No limit on how many agreements can be created by a user.

**Attack Vector**:
1. Malicious/compromised user creates thousands of agreements
2. Each agreement uploads document to storage
3. Each agreement creates record in Adobe Sign
4. Storage bloat + cost increase
5. Adobe Sign API quota exhausted

**Impact**:
- DoS attack vector
- Cost implications
- System slowdown

**Severity**: 🔒 **MODERATE** - DoS risk

**Recommendation**: Implement rate limiting (e.g., max 10 agreements per hour per user).

---

### 🔒 SECURITY #4: File Upload Not Scanned for Malware

**Location**: `views.py:agreement_add()` + `views.py:replace_document()`

**Issue**: Uploaded PDFs are not scanned for:
- Malware
- Embedded scripts
- PDF exploits

**Impact**:
- Malware uploaded to server
- Malware sent to director/client via Adobe Sign
- Security breach
- Reputation damage

**Severity**: 🔒 **MODERATE** - Malware risk

**Recommendation**: Integrate antivirus scanning (ClamAV or cloud service) before accepting upload.

---

### 🔒 SECURITY #5: Sensitive Data in Logs

**Location**: Multiple logger.error() calls throughout views.py

**Issue**: Error messages logged with full exception details:

```python
except Exception as e:
    logger.error(f"Error creating agreement: {e}")
```

**Problem**: Exception `e` may contain:
- Client email addresses
- Document content
- API keys (if API error)
- Personal data

**Impact**:
- PII leaked to log files
- GDPR compliance risk
- Security exposure if logs compromised

**Severity**: 🔒 **MODERATE** - Privacy violation

**Recommendation**: Sanitize log messages:
```python
logger.error(f"Error creating agreement {agreement.id}: {type(e).__name__}")
logger.debug(f"Full error: {e}")  # Debug level only, not in production
```

---

## Recommendations

### Priority 1: CRITICAL Fixes (Immediate Action Required)

1. **Fix Signature Field Placement** (CRITICAL #1)
   - **Option A**: Use Adobe Sign authoring UI exclusively (remove ERP signature placement)
   - **Option B**: Switch to IN_PROCESS state immediately with fields (skip AUTHORING)
   - **Option C**: Use Adobe Text Tags in PDF instead of API fields

2. **Add Signature Field Validation** (CRITICAL #2)
   - Form validation: require at least one signature field before submit
   - Backend validation: check `signature_field_data` is not empty/NULL

3. **Add PDF Viewer with Field Overlay** (CRITICAL #3)
   - Embed PDF.js in agreement review page
   - Render signature field boxes on PDF for director to see
   - Allow director to adjust fields if needed

4. **Fix Duplicate Agreement Creation** (CRITICAL #4)
   - Remove Adobe Sign creation from `agreement_add()`
   - Only create in Adobe Sign on explicit submit
   - Add cleanup for orphaned agreements

5. **Prevent Multiple Submits** (CRITICAL #5)
   - Check if `adobe_agreement_id` exists before creating new
   - Add client-side button disable on submit
   - Add server-side idempotency check

6. **Implement Webhook Handler** (CRITICAL #10)
   - Create endpoint `/integrations/adobe-sign/webhooks/` to receive Adobe events
   - Update signer status when Adobe sends SIGNED events
   - Auto-complete agreement when Adobe sends COMPLETED events
   - Send notifications to backoffice on status changes

7. **Add Transaction Management** (CRITICAL #8)
   - Wrap agreement creation in `@transaction.atomic`
   - Rollback database changes if Adobe API fails
   - Clean up partially created data

8. **Fix Tracking Field Updates** (CRITICAL #9)
   - Create helper method to set all tracking fields atomically
   - Update tracking fields in all state transitions
   - Ensure `sent_date_client_vendor` set for all flows

### Priority 2: HIGH Fixes (This Sprint)

1. **Implement Notification System** (GAP #1)
   - Email backoffice when director rejects
   - Email director when backoffice submits
   - Email backoffice when agreement completed
   - Add in-app notification center

2. **Add Access Control** (SECURITY #1)
   - Implement ownership-based access control
   - Allow creators + approvers + admins only
   - Add explicit permission checks

3. **Add PDF Preview** (GAP #5)
   - Embed PDF viewer in review page
   - Show signature field overlays
   - Allow field adjustment

### Priority 3: MODERATE Fixes (Next Sprint)

1. **Fix Rejection Workflow** (FLAW #3)
   - Cancel Adobe agreement on rejection
   - Clear signature fields
   - Send notification
   - Create audit event

2. **Add Email Validation** (FLAW #5)
   - Validate CC emails format
   - Check for duplicates
   - Warn if director email in CC

3. **Improve Error Handling** (FLAW #6)
   - Categorize Adobe API errors
   - User-friendly error messages
   - Retry logic for transient errors

4. **Add Search/Filter** (GAP #4)
   - Dashboard search by client, project, status
   - Date range filter
   - Sort by columns

5. **Add Versioning** (GAP #3)
   - Keep history of replaced documents
   - Show document version timeline
   - Allow comparison

6. **Add Rate Limiting** (SECURITY #3)
   - Limit agreements per user per hour
   - Prevent DoS attacks

### Priority 4: LOW Fixes (Backlog)

1. **Clean Up Dead Code** (FLAW #1, #7)
   - Remove unused flow types or implement them
   - Remove template system or complete implementation

2. **Fix Data Inconsistencies** (INCONSISTENCY #1-5)
   - Consolidate duplicate email fields
   - Standardize naming conventions
   - Validate enum values

3. **Add Reporting** (GAP #8)
   - Agreement status dashboard
   - Performance metrics
   - Rejection rate tracking

4. **Add Automated Testing**
   - Unit tests for models
   - Integration tests for workflows
   - E2E tests for critical paths

---

## Conclusion

The Adobe Sign integration has a solid foundation with well-structured models and a clear workflow design. However, **critical issues with signature field placement, duplicate agreement creation, and missing webhook integration** significantly impact the system's reliability and usability.

**Immediate action required** on 8 critical issues to ensure the system functions correctly in production. Without these fixes, the workflow is **fundamentally broken** and will cause frustration for backoffice staff, director, and clients.

**Total Issues Identified**: 34
- 🔴 Critical: 12
- ⚠️ Logical Flaws: 8
- 📊 Data Inconsistencies: 5
- 🔗 Process Gaps: 9
- 🔒 Security Concerns: 5

---

**Report End**

**Prepared by**: Automated System Audit
**Date**: 2026-02-08
**Version**: 1.0
