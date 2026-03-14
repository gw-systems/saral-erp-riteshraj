# Adobe Sign - Complete In-ERP Solution

## Your Requirement: Everything Inside ERP Portal

✅ **NO external tools**
✅ **NO Adobe interface**
✅ **NO manual coordinate measurement**
✅ **ALL actions inside ERP from start to finish**

## The Complete In-ERP Workflow

### For Admin: Template Creation (One-Time Setup)

**Step 1: Upload Template PDF**
```
Admin Dashboard → Adobe Sign → Templates → Create New Template

[Upload PDF]
┌─────────────────────────────┐
│ Drop PDF here or click      │
│ to upload                   │
└─────────────────────────────┘

Template Name: Standard NDA
Template Type: [NDA ▼]
Description: Standard non-disclosure agreement for clients
```

**Step 2: Visual Field Placement (In-ERP PDF Viewer)**
```
┌─────────────────────────────────────────────────┐
│  PDF Preview (Interactive)                      │
│  ┌───────────────────────────────────────────┐ │
│  │                                           │ │
│  │  NON-DISCLOSURE AGREEMENT                 │ │
│  │                                           │ │
│  │  Director:                                │ │
│  │  ┌─────────────────┐  [Click to place]   │ │ ← Admin clicks here
│  │  │ Signature Box   │  ✓ Placed           │ │   System draws box
│  │  └─────────────────┘                      │ │   Auto-captures coordinates
│  │  Date: [____] ✓                           │ │
│  │                                           │ │
│  │  Client:                                  │ │
│  │  ┌─────────────────┐  [Click to place]   │ │
│  │  │ Signature Box   │  ✓ Placed           │ │
│  │  └─────────────────┘                      │ │
│  │  Date: [____] ✓                           │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  Signature Fields:                              │
│  ✓ Director Signature (Page 1: 100,650)        │
│  ✓ Director Date (Page 1: 320,650)             │
│  ✓ Client Signature (Page 2: 100,700)          │
│  ✓ Client Date (Page 2: 320,700)               │
│                                                 │
│  [Save Template] [Test with Sample Document]   │
└─────────────────────────────────────────────────┘
```

**How It Works:**
1. ERP displays PDF using **PDF.js** (embedded viewer)
2. Admin clicks "Add Director Signature" button
3. Admin clicks on PDF where signature should go
4. ERP draws a draggable/resizable box
5. Admin adjusts size if needed
6. ERP captures: `{pageNumber: 1, top: 650, left: 100, width: 200, height: 40}`
7. Repeat for date, client signature, client date
8. Save template → coordinates stored in database

**Result:** Template with saved coordinates, ready for infinite reuse.

---

### For Backoffice: Create Agreement (Daily Use)

**Step 1: Upload Scanned PDF + Select Template**
```
Backoffice Dashboard → Adobe Sign → Create Agreement

[Upload Scanned Document]
┌─────────────────────────────┐
│ Drop scanned PDF here       │
└─────────────────────────────┘

Template: [Standard NDA ▼]  ← Selects saved template
        [Custom (no template)]

Client Name: ABC Warehousing Pvt Ltd
Client Email: contact@abcware.com
CC Emails: legal@abcware.com, admin@abcware.com

Signing Flow: ⦿ Director signs first, then client
              ○ Client only (Director already signed)
              ○ Both sign simultaneously

[Preview & Submit]
```

**Step 2: Preview with Signature Blocks (In-ERP)**
```
Preview Agreement

┌─────────────────────────────────────────────────┐
│  Your Scanned Document                          │
│  ┌───────────────────────────────────────────┐ │
│  │                                           │ │
│  │  [Scanned contract image]                 │ │
│  │                                           │ │
│  │  Director: Vivek Tiwari                   │ │
│  │  ┌──────────────────┐                     │ │
│  │  │ 📝 Signature Box │  ← System overlays  │ │
│  │  │  (Vivek Tiwari)  │     boxes showing   │ │
│  │  └──────────────────┘     where Adobe     │ │
│  │  Date: [__/__/____]       will place      │ │
│  │                           fields           │ │
│  │  Client: ABC Warehousing                  │ │
│  │  ┌──────────────────┐                     │ │
│  │  │ 📝 Signature Box │                     │ │
│  │  │  (Client)        │                     │ │
│  │  └──────────────────┘                     │ │
│  │  Date: [__/__/____]                       │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  ✓ Signature blocks will be placed at          │
│    positions defined in "Standard NDA" template │
│                                                 │
│  [← Back]  [Submit for Director Approval]      │
└─────────────────────────────────────────────────┘
```

**Step 3: Submit**
- Click "Submit for Director Approval"
- ERP sends to Adobe with saved coordinates
- Adobe places signature fields automatically
- Agreement moves to PENDING_APPROVAL
- **No manual field placement!**

---

### For Director (Vivek Tiwari): Review & Approve

**Step 1: View Pending Agreements**
```
Director Dashboard → Adobe Sign → Pending Approvals

Pending Your Approval (3)
┌────────────────────────────────────────────────┐
│ Standard NDA - ABC Warehousing                 │
│ Client: contact@abcware.com                    │
│ Submitted: 2 hours ago by Rajesh (Backoffice)  │
│ [Review & Approve →]                           │
└────────────────────────────────────────────────┘
```

**Step 2: Review Agreement (Embedded Adobe Viewer in ERP)**
```
Review Agreement: Standard NDA - ABC Warehousing

┌─────────────────────────────────────────────────┐
│  Agreement Details          Status: Pending      │
│  ──────────────────────────────────────────────│ │
│  Client: ABC Warehousing Pvt Ltd                │
│  Client Email: contact@abcware.com              │
│  CC: legal@abcware.com                          │
│  Flow: Director signs first, then client        │
│  Submitted by: Rajesh, 2 hours ago              │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Document Preview (Embedded Adobe Viewer)       │
│  ┌───────────────────────────────────────────┐ │
│  │                                           │ │
│  │  [Adobe Sign embedded iframe shows:]     │ │
│  │  - Full document with signature fields   │ │
│  │  - All fields correctly placed            │ │
│  │  - Ready for director to sign             │ │
│  │                                           │ │
│  │  [If director needs to sign: embedded    │ │
│  │   signing interface appears here]         │ │
│  └───────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘

Actions:
[✓ Approve & Send to Client]  [✗ Reject & Send Back]
```

**Option A: Approve Directly**
- Director reviews document
- Fields are correctly placed (from template)
- Clicks "Approve & Send to Client"
- Agreement sent to client immediately

**Option B: Director Needs to E-Sign First**
- If flow = "Director signs first"
- Embedded Adobe signing interface appears
- Director signs directly in ERP (no email, no external page)
- After signing, auto-transitions to approved
- Sent to client automatically

**Option C: Reject**
```
Reject Agreement

Rejection Reason:
⦿ Incorrect information
○ Wrong document uploaded
○ Signature blocks misplaced
○ Missing details
○ Other

Detailed Instructions for Backoffice:
┌─────────────────────────────────────────┐
│ Client name should be "ABC Warehousing │
│ Pvt Ltd" not just "ABC Warehousing"    │
│                                         │
│ Please update and resubmit.            │
└─────────────────────────────────────────┘

[Send Back to Backoffice]
```

---

### For Custom Documents (No Template)

**When backoffice encounters unique document:**

```
Create Agreement → Upload PDF → Template: [Custom (no template)]

System shows:
┌─────────────────────────────────────────────────┐
│  Custom Document - Place Signature Fields       │
│  ┌───────────────────────────────────────────┐ │
│  │  Your Scanned PDF Preview                 │ │
│  │  [PDF displayed with PDF.js]              │ │
│  │                                           │ │
│  │  Click to place signature fields:         │ │
│  └───────────────────────────────────────────┘ │
│                                                 │
│  [Add Director Signature] [Add Director Date]  │
│  [Add Client Signature] [Add Client Date]      │
│                                                 │
│  Placed Fields:                                 │
│  (none yet)                                     │
│                                                 │
│  [Save as New Template] [Submit for Approval]  │
└─────────────────────────────────────────────────┘
```

**Process:**
1. Backoffice clicks "Add Director Signature"
2. Clicks on PDF where it should go
3. ERP draws resizable box
4. Repeat for other fields
5. **Option to save as template** for future use
6. Submit for approval

**Benefits:**
- Still no Adobe interface
- Everything in ERP
- Can create templates on-the-fly
- Builds template library organically

---

## Technical Implementation Stack

### Frontend (In-ERP UI Components)

**1. PDF.js Integration**
```javascript
// Embedded PDF viewer in ERP
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>

// Display PDF in canvas
const pdfDoc = await pdfjsLib.getDocument(pdfUrl).promise;
const page = await pdfDoc.getPage(pageNumber);
const canvas = document.getElementById('pdf-canvas');
page.render({canvasContext: canvas.getContext('2d'), viewport});
```

**2. Click-to-Place Signature Fields**
```javascript
// Capture click coordinates on PDF canvas
canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Convert canvas coordinates to PDF coordinates
    const pdfX = (x / canvas.width) * pdfPage.width;
    const pdfY = (y / canvas.height) * pdfPage.height;

    // Create signature field
    createSignatureField(pdfX, pdfY, pageNumber);
});
```

**3. Draggable/Resizable Field Boxes**
```javascript
// Use libraries like Interact.js or custom implementation
interact('.signature-field')
  .draggable({
    onmove: (event) => {
      // Update field position
      updateFieldCoordinates(event.target, event.dx, event.dy);
    }
  })
  .resizable({
    onmove: (event) => {
      // Update field dimensions
      updateFieldDimensions(event.target, event.rect.width, event.rect.height);
    }
  });
```

**4. Embedded Adobe Viewer (for review/signing)**
```html
<!-- Director reviews/signs within ERP -->
<iframe
  src="https://secure.adobesign.com/public/apiv6embed/..."
  width="100%"
  height="800px"
  frameborder="0">
</iframe>
```

### Backend (Already Built)

**Models** ✅
- `DocumentTemplate.field_definitions` stores coordinates
- `AdobeAgreement` tracks workflow
- `Signer` manages participants

**Services** ✅ (needs minor enhancement)
- `AdobeAgreementService.create_agreement_with_form_fields()` - send coordinates to Adobe
- Already has all API methods

**Views** ✅ (needs coordinate handling)
- Template creation with coordinate capture
- Agreement preview with overlay
- Review with embedded viewer

---

## User Experience: Complete Flow

### Scenario: Backoffice creates NDA for new client

**9:00 AM - Backoffice (Rajesh)**
1. Opens ERP → Adobe Sign → Create Agreement
2. Uploads scanned NDA PDF (drag & drop)
3. Selects "Standard NDA" template from dropdown
4. Enters: Client Name, Email, CC
5. Clicks "Preview"
6. Sees PDF with overlay boxes showing where signatures will go
7. Looks correct → Clicks "Submit for Approval"
8. **Time: 1 minute**

**9:05 AM - System**
- Uploads PDF to Adobe with coordinates from template
- Adobe creates agreement with signature fields at exact positions
- Notifies Director (Vivek)

**10:30 AM - Director (Vivek)**
1. Opens ERP → Adobe Sign → Pending Approvals
2. Sees "Standard NDA - ABC Warehousing (submitted by Rajesh)"
3. Clicks "Review"
4. Embedded viewer shows full document with signature fields
5. Everything looks correct
6. Clicks "Approve & Send to Client"
7. **Time: 30 seconds**

**10:31 AM - System**
- Adobe sends agreement to client email
- Client receives email with signing link

**11:00 AM - Client (ABC Warehousing)**
- Opens email
- Clicks "Review and Sign"
- Signs in Adobe (external to ERP, but that's okay - they're not ERP users)
- Submits

**11:05 AM - System**
- Syncs status from Adobe
- Marks agreement as COMPLETED
- Downloads signed PDF
- Stores in ERP

**11:10 AM - Director/Backoffice**
- Views agreement in ERP
- Clicks "Download Signed Document"
- PDF downloaded with all signatures
- **Complete!**

**Total time in ERP:** 1.5 minutes (vs 10+ minutes with manual placement)

---

## Implementation Priority

### Phase 1: Basic Template System (Week 1)
✅ **Already built backend**
- Models support coordinate storage
- Services ready for enhancement
- Views structure in place

⏳ **Need to add:**
- PDF.js integration in templates
- Click-to-place UI for template creation
- Coordinate capture and save
- Preview with overlay

### Phase 2: Enhanced UX (Week 2)
- Drag/resize field boxes
- Field validation
- Save-as-template from custom documents
- Better preview visualization

### Phase 3: Advanced Features (Week 3+)
- Template versioning
- Field libraries (reusable field definitions)
- Bulk agreement creation
- Analytics dashboard

---

## Technical Requirements

### Frontend Libraries (Free/Open Source)
```html
<!-- PDF Rendering -->
<script src="pdf.js"></script>

<!-- Drag & Drop / Resize -->
<script src="interact.js"></script>

<!-- Or use native HTML5 drag/drop + resize handles -->
```

### Backend Enhancements Needed

**1. Update Adobe Agreement Service**
```python
# Add coordinate-based field creation
def create_agreement_with_form_fields(
    transient_document_id,
    agreement_name,
    signers_data,
    form_fields=None,  # Accept coordinate definitions
    ...
):
    payload = {
        "fileInfos": [{"transientDocumentId": transient_document_id}],
        "name": agreement_name,
        "participantSetsInfo": participant_sets_info,
        "signatureType": "ESIGN",
        "state": "AUTHORING",
    }

    if form_fields:
        # Add form fields with coordinates
        payload["formFields"] = form_fields

    # Send to Adobe
    response = requests.post(url, json=payload, headers=headers)
    return response.json()['id']
```

**2. Add Template Coordinate API**
```python
# New view for saving field coordinates
@login_required
def save_template_fields(request, template_id):
    """Save signature field coordinates for template"""
    template = get_object_or_404(DocumentTemplate, id=template_id)

    # Get coordinates from request
    fields = request.POST.get('fields')  # JSON string

    # Parse and validate
    field_data = json.loads(fields)

    # Save to template
    template.field_definitions = {"fields": field_data}
    template.save()

    return JsonResponse({'success': True})
```

**3. Add Preview Overlay View**
```python
@login_required
def preview_agreement(request, agreement_id):
    """Preview agreement with signature field overlays"""
    agreement = get_object_or_404(AdobeAgreement, id=agreement_id)

    # Get field positions from template
    template = agreement.document.template
    fields = template.field_definitions.get('fields', [])

    context = {
        'agreement': agreement,
        'fields': fields,  # Pass to template for overlay
        'document_url': agreement.document.file.url
    }

    return render(request, 'adobe_sign/preview_agreement.html', context)
```

---

## Summary: Complete In-ERP Solution

✅ **Admin creates templates** → Visual click-to-place in ERP
✅ **Backoffice creates agreements** → Select template, instant placement
✅ **Director reviews/approves** → Embedded viewer in ERP
✅ **Director signs (if needed)** → Embedded Adobe signing in ERP
✅ **Custom documents** → Click-to-place in ERP, save as template
✅ **Download signed PDFs** → Direct from ERP

**NO external tools, NO Adobe interface, NO manual coordinate measurement!**

Everything happens inside your ERP portal from start to finish.

Want me to implement the enhanced services and create sample template HTML with PDF.js integration?
