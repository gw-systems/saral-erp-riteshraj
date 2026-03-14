# Adobe Sign - Coordinate-Based Signature Field Placement

## The Real Problem: Scanned PDFs

You're absolutely right! The text tag approach **only works for editable PDFs**. For **scanned PDFs** (which are just images), you cannot add text tags.

### Your Actual Workflow
1. Contracts are **scanned** (becoming image-based PDFs)
2. Cannot add text to scanned images
3. Need to place signature blocks **programmatically using coordinates**

## Solution: Coordinate-Based Field Placement

Adobe Sign API supports placing signature fields using **absolute coordinates** (pageNumber, left, top, width, height).

### How It Works

Instead of text tags, you define signature fields with pixel coordinates:

```json
{
  "name": "Director Signature",
  "inputType": "SIGNATURE",
  "locations": {
    "pageNumber": 1,
    "top": 520,
    "left": 162,
    "width": 280,
    "height": 30
  },
  "contentType": "SIGNATURE",
  "required": 1,
  "recipientIndex": 1
}
```

**This means**: Place a signature field on page 1, 520 pixels from top, 162 pixels from left, sized 280×30 pixels.

---

## Three Approaches for Your Use Case

### Approach 1: Template with Saved Coordinates (RECOMMENDED)

**Concept**: For standard documents (NDAs, Service Agreements), measure coordinates ONCE, save in template, reuse forever.

**How to Create Template:**
1. Admin opens a sample PDF in Adobe Acrobat or any PDF viewer
2. Identifies where signature should go (visually)
3. Notes the coordinates (can use Adobe Acrobat's measuring tools or estimate)
4. Creates template in system with these coordinates saved as JSON:

```json
{
  "template_name": "Standard NDA",
  "field_definitions": {
    "director_signature": {
      "pageNumber": 1,
      "top": 650,
      "left": 100,
      "width": 200,
      "height": 40
    },
    "director_date": {
      "pageNumber": 1,
      "top": 650,
      "left": 320,
      "width": 100,
      "height": 40
    },
    "client_signature": {
      "pageNumber": 2,
      "top": 700,
      "left": 100,
      "width": 200,
      "height": 40
    },
    "client_date": {
      "pageNumber": 2,
      "top": 700,
      "left": 320,
      "width": 100,
      "height": 40
    }
  }
}
```

**Backoffice Workflow:**
1. Upload scanned PDF
2. Select "Standard NDA" template
3. System automatically sends to Adobe with coordinates from template
4. Adobe places signature blocks at exact positions
5. **No manual work!**

**Benefits:**
- ✅ Works with scanned PDFs
- ✅ One-time coordinate measurement
- ✅ Reusable for all similar documents
- ✅ No manual placement per document
- ✅ Consistent positioning

**Implementation**: Already built into the models I created! `DocumentTemplate.field_definitions` stores this JSON.

---

### Approach 2: Interactive Coordinate Picker (ENHANCED UX)

**Concept**: Visual interface where backoffice clicks on PDF to place signature blocks.

**How It Works:**
1. Backoffice uploads scanned PDF
2. System displays PDF in browser
3. Backoffice clicks: "Place Director Signature Here" → clicks on PDF
4. System captures coordinates (x, y from click event)
5. Backoffice clicks: "Place Client Signature Here" → clicks on PDF
6. System sends coordinates to Adobe API
7. Adobe places signature fields at clicked positions

**User Experience:**
```
[PDF Preview]
┌─────────────────────────────┐
│                             │
│  This is a scanned          │
│  contract document          │
│                             │
│  Director: ___[Click]___    │ ← User clicks here
│  Date: ___[Click]___        │
│                             │
│  Client: ___[Click]___      │
│  Date: ___[Click]___        │
│                             │
└─────────────────────────────┘

[Save Template] [Submit for Approval]
```

**Benefits:**
- ✅ Visual, intuitive
- ✅ No coordinate calculation needed
- ✅ Can save as template for reuse
- ✅ Better than Adobe's authoring interface (stays in your system)

**Implementation**: Requires JavaScript PDF viewer (PDF.js) + click coordinate capture.

---

### Approach 3: Hybrid - Use Authoring for First Time, Save Coordinates

**Concept**: Use Adobe's authoring interface ONCE to place fields, then extract and save those coordinates for future use.

**How It Works:**
1. **First document of each type:**
   - Backoffice uses Adobe authoring interface (current method)
   - Places signature blocks manually
   - System calls Adobe API to GET the placed field coordinates
   - Saves coordinates as template

2. **Subsequent documents of same type:**
   - Backoffice selects saved template
   - System uses saved coordinates
   - No manual placement needed

**Benefits:**
- ✅ Uses familiar Adobe interface for initial setup
- ✅ Automatically becomes template
- ✅ All future documents instant

**Implementation**: Call `GET /agreements/{agreementId}/formFields` after authoring, extract coordinates, save as template.

---

## Recommended Implementation

### Phase 1: Template with Saved Coordinates (Immediate)

**For You**: This solves 80% of use cases with minimal effort.

**Standard Documents**: Most of your agreements are probably similar (NDAs, Service Agreements, Lease Agreements). These have signature blocks in same positions every time.

**One-Time Setup:**
1. Measure coordinates for each standard document type (30 min per template)
2. Save in template
3. Done forever!

**Daily Use:**
```
Backoffice → Upload scanned PDF → Select "Standard NDA" → Submit
            └─ System uses saved coordinates
            └─ 30 seconds, zero manual work
```

### Phase 2: Interactive Coordinate Picker (If Needed)

**For You**: Only needed for truly unique documents.

**Custom Documents**: For one-off contracts with unique layouts, give backoffice a visual click interface instead of making them use Adobe's authoring.

---

## Technical Implementation

### Update the `field_definitions` JSON Structure

Already built into your models! Just need to populate it correctly:

```python
# In DocumentTemplate model (already created)
field_definitions = models.JSONField(
    default=dict,
    help_text='JSON mapping of field names to coordinates'
)

# Example data:
{
  "fields": [
    {
      "name": "Director Signature",
      "inputType": "SIGNATURE",
      "contentType": "SIGNATURE",
      "required": true,
      "recipientIndex": 0,  # 0 = first signer (Director)
      "locations": {
        "pageNumber": 1,
        "top": 650,
        "left": 100,
        "width": 200,
        "height": 40
      }
    },
    {
      "name": "Director Date",
      "inputType": "DATE",
      "contentType": "DATE",
      "required": true,
      "recipientIndex": 0,
      "locations": {
        "pageNumber": 1,
        "top": 650,
        "left": 320,
        "width": 100,
        "height": 40
      }
    },
    {
      "name": "Client Signature",
      "inputType": "SIGNATURE",
      "contentType": "SIGNATURE",
      "required": true,
      "recipientIndex": 1,  # 1 = second signer (Client)
      "locations": {
        "pageNumber": 2,
        "top": 700,
        "left": 100,
        "width": 200,
        "height": 40
      }
    },
    {
      "name": "Client Date",
      "inputType": "DATE",
      "contentType": "DATE",
      "required": true,
      "recipientIndex": 1,
      "locations": {
        "pageNumber": 2,
        "top": 700,
        "left": 320,
        "width": 100,
        "height": 40
      }
    }
  ]
}
```

### Update Adobe Agreement Service

I'll create an enhanced version that uses coordinates instead of/in addition to text tags:

```python
# In services/adobe_agreements.py

@staticmethod
def create_agreement_with_form_fields(
    transient_document_id,
    agreement_name,
    signers_data,
    form_fields=None,  # NEW: Accept form field definitions
    ccs=None,
    message='',
    days_until_signing_deadline=30,
    reminder_frequency='EVERY_OTHER_DAY'
):
    """
    Create agreement with pre-defined form fields at specific coordinates
    Works for scanned PDFs without text tags!
    """
    url = f"{AdobeAgreementService.BASE_URL}/agreements"
    headers = AdobeAuthService.get_headers()

    # Build participant sets
    participant_sets_info = []
    for signer in signers_data:
        participant_sets_info.append({
            "memberInfos": [{"email": signer['email']}],
            "order": signer.get('order', 1),
            "role": signer.get('role', 'SIGNER')
        })

    # Build payload
    payload = {
        "fileInfos": [{
            "transientDocumentId": transient_document_id
        }],
        "name": agreement_name,
        "participantSetsInfo": participant_sets_info,
        "signatureType": "ESIGN",
        "state": "AUTHORING",
    }

    # Add form fields with coordinates (if provided)
    if form_fields:
        payload["formFields"] = form_fields

    # ... rest of the method
```

### How Backoffice Uses It

```python
# When creating agreement with template that has coordinates

# 1. Backoffice selects template
template = DocumentTemplate.objects.get(id=template_id)

# 2. Get form field definitions from template
form_fields = template.field_definitions.get('fields', [])

# 3. Create agreement with these coordinates
adobe_agreement_id = AdobeAgreementService.create_agreement_with_form_fields(
    transient_document_id=transient_id,
    agreement_name=agreement_name,
    signers_data=signers_data,
    form_fields=form_fields,  # Coordinates from template!
    ccs=cc_list
)

# Done! Signature blocks placed automatically at saved coordinates
```

---

## Measuring Coordinates

### Method 1: Adobe Acrobat Pro
1. Open PDF in Adobe Acrobat Pro
2. Tools → Measure → Distance Tool
3. Click on point where signature should start
4. Note X,Y coordinates (shown in tool)
5. Measure width and height of desired signature box

### Method 2: Online PDF Coordinate Tool
Use free online tools:
- PDFtk
- Sejda PDF editor
- Any PDF editor with ruler/grid

### Method 3: Trial and Error
1. Start with estimated coordinates
2. Send test agreement
3. See where field appears
4. Adjust coordinates
5. Repeat 2-3 times until perfect
6. Save final coordinates

### Adobe Sign Coordinate System
- **Origin**: Top-left corner of page
- **Top**: Pixels from top edge (0 = top)
- **Left**: Pixels from left edge (0 = left)
- **Units**: Pixels
- **Page Size**: Varies by PDF (A4 ≈ 595×842 points, Letter ≈ 612×792 points)

**Example:**
```
Page (Letter size: 612×792)
┌──────────────────┐ (0,0)
│                  │
│  top: 100        │
│  left: 50        │
│  ┌────────┐      │ ← Signature box
│  │  Sign  │      │   (width: 200, height: 40)
│  └────────┘      │
│                  │
└──────────────────┘ (612,792)
```

---

## Comparison: All 4 Methods

| Method | Works with Scanned PDFs? | Manual Work Per Doc | Setup Time | Flexibility |
|--------|-------------------------|---------------------|------------|-------------|
| **Text Tags** | ❌ No (editable PDFs only) | None | Low (edit PDF once) | Medium |
| **Adobe Authoring** | ✅ Yes | 5-10 min per doc | None | High |
| **Saved Coordinates** | ✅ Yes | None (after setup) | Medium (measure once) | Low |
| **Click-to-Place** | ✅ Yes | 30 sec per doc | High (build UI) | High |

---

## Recommendation for Your Use Case

### Immediate Solution (This Week)

**Use Saved Coordinates for Standard Documents:**

1. Identify your top 5 most-used document types
2. Measure coordinates for each (30 min per type)
3. Create templates with saved coordinates
4. Backoffice uses templates → instant placement

**Estimated Impact:**
- 80% of documents covered
- Zero manual placement for these
- 10x faster than current method

### Future Enhancement (If Needed)

**Build Click-to-Place UI for Custom Documents:**
- Only needed for the other 20% (unique documents)
- Better UX than Adobe's authoring interface
- Stays within your system

---

## Sources

- [Adobe Sign API Usage Guide](https://opensource.adobe.com/acrobat-sign/developer_guide/apiusage.html)
- [How to place form-fields in a document using REST API](https://helpx.adobe.com/sign/kb/place-form-fields-in-a-document-using-rest-api-adobe-sign.html)
- [Adobe Sign API - Adding Form Fields](https://community.adobe.com/t5/adobe-acrobat-sign-discussions/adding-form-field-signature-to-a-pdf-using-rest-api-v6/td-p/13742580)
- [Adobe Sign Developer Guide](https://developer.adobe.com/acrobat-sign/docs/overview/developer_guide/apiusage)
- [Position signature blocks using v6 API](https://community.adobe.com/t5/adobe-acrobat-sign-discussions/esign-position-signature-block-to-specific-postion-using-v6-api-php/td-p/10446221)

---

## Next Steps

Want me to:
1. ✅ Update the service layer to support coordinate-based placement
2. ✅ Enhance the template model to store coordinates properly
3. ✅ Update views to use coordinates when template selected
4. ⏳ Create a UI for measuring/saving coordinates (optional)
5. ⏳ Build click-to-place interface (future enhancement)

Let me know and I'll implement the coordinate-based solution right away!
