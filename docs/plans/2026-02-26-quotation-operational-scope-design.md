# Design: Quotation Operational Scope of Service

**Date:** 2026-02-26
**Status:** Approved
**Feature:** Add Operational Scope of Service section to quotation module (pallet dimension calculator)

---

## Context

The existing quotation module has a simple `scope_of_service` JSON field (checkboxes).
This is being **replaced** with a full "Operational Scope of Service" section that includes:
- Multiple product/SKU rows with dimensions and pallet planning calculations
- Summary: actual pallets required and billable storage area
- Calculations are **backend/form-only** — downloaded documents show only product names, operation type, and billable area

---

## Data Model

### Changes to `Quotation` model

**Remove:**
- `scope_of_service` JSONField (replaced by new section)

**Add operational summary fields:**

| Field | Type | Default | Notes |
|---|---|---|---|
| `operational_total_boxes` | DecimalField(10,2) | null, blank | Total boxes to store across all SKUs |
| `operational_variance_pct` | DecimalField(5,2) | 30.00 | Batch management buffer (%) |
| `operational_pallet_l` | DecimalField(6,3) | 3.33 | Pallet length in ft |
| `operational_pallet_w` | DecimalField(6,3) | 3.33 | Pallet width in ft |
| `operational_pallet_h` | DecimalField(6,3) | 4.00 | Pallet height in ft |

**Computed properties (not stored):**
- `pallet_area_sqft` = pallet_l × pallet_w
- `pallet_volume_ft3` = pallet_l × pallet_w × pallet_h
- `total_pallets_required` = Σ product.num_pallets
- `actual_pallets_required` = total_pallets × (1 + variance_pct / 100)
- `billable_storage_area_sqft` = actual_pallets × 25

### New `QuotationProduct` model

**Table:** `quotation_product`
**Relationship:** FK → `Quotation` (related_name=`products`)

| Field | Type | Notes |
|---|---|---|
| `product_id` | AutoField (PK) | |
| `quotation` | FK → Quotation | CASCADE delete |
| `product_name` | CharField(255) | e.g. "Baby Diapers" |
| `type_of_business` | CharField choices | `B2B` / `B2C` |
| `type_of_operation` | CharField choices | See below |
| `packaging_type` | CharField(100) blank | e.g. "Carton", "Polybag" |
| `avg_weight_kg` | DecimalField(8,2) null/blank | Average box/bag weight |
| `dim_l` | DecimalField(10,4) | Length as entered by user |
| `dim_w` | DecimalField(10,4) | Width as entered by user |
| `dim_h` | DecimalField(10,4) | Height as entered by user |
| `dim_unit` | CharField choices | `MM` / `CM` / `INCH` / `FT` |
| `share_pct` | DecimalField(6,2) | % of total boxes this SKU represents |
| `order` | IntegerField default=0 | Display order |

**Type of Operation choices:**
- `box_in_box_out` → "Box In – Box Out"
- `box_in_piece_out` → "Box In – Piece Out"
- `box_in_pallet_out` → "Box In – Pallet Out"
- `pallet_in_box_out` → "Pallet In – Box Out"

**Computed properties:**

Unit conversion to ft (MM÷304.8, CM÷30.48, INCH÷12, FT as-is):
- `dim_l_ft`, `dim_w_ft`, `dim_h_ft`

Per-product calculations:
- `volume_per_box_ft3` = dim_l_ft × dim_w_ft × dim_h_ft
- `boxes_per_pallet` = pallet_volume_ft3 (from quotation) ÷ volume_per_box_ft3
- `total_boxes` = operational_total_boxes × (share_pct ÷ 100)
- `num_pallets` = total_boxes ÷ boxes_per_pallet

### Migration

**File:** `projects/migrations/0039_quotation_operational_scope_product.py`

Operations:
1. `RemoveField('quotation', 'scope_of_service')` — remove old JSON field
2. `AddField` × 5 — add operational summary fields to Quotation
3. `CreateModel('QuotationProduct', ...)` — new product table

---

## Form Layer

### `QuotationForm` changes
- Remove `scope_of_service` field
- Add: `operational_total_boxes`, `operational_variance_pct`, `operational_pallet_l`, `operational_pallet_w`, `operational_pallet_h`

### New `QuotationProductForm`
ModelForm for `QuotationProduct` with all 9 user-entry fields.
Validation: `dim_l/w/h` must be positive numbers; `share_pct` must be 0–100.

### New `QuotationProductFormSet`
```python
QuotationProductFormSet = inlineformset_factory(
    Quotation, QuotationProduct,
    form=QuotationProductForm,
    extra=0, can_delete=True,
    min_num=0, max_num=20,
)
```

---

## View Layer

### `quotation_create` / `quotation_edit`
- Handle `QuotationProductFormSet` alongside existing location/item formsets
- On POST: validate and save product formset after quotation save
- On validation error: pass products JSON back to template for re-render (same pattern as locations/items)
- Build `existing_products_json` helper for edit pre-population

---

## Template Layer

### `quotation_create.html` — new section between Client Details and Pricing

**Section layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  SECTION 2: OPERATIONAL SCOPE OF SERVICE                    │
├─────────────────────────────────────────────────────────────┤
│  Pallet Dimensions (ft):  L [3.33]  W [3.33]  H [4.00]     │
│  Total Boxes to Store: [______]    Variance %: [30]         │
├─────────────────────────────────────────────────────────────┤
│ Product rows (dynamic add/remove):                          │
│ #│Product Name│B2B/B2C│Operation│Pkg Type│Wt(kg)│L│W│H│Unit│Share%│
│  └─ (computed display) Vol/Box │ Boxes/Pallet │ Pallets     │
├─────────────────────────────────────────────────────────────┤
│ LIVE SUMMARY (display only)                                 │
│ Pallet Volume: X ft³ | Total Pallets: Y | Actual: Z        │
│ Billable Storage Area: Z × 25 = ____ sq.ft                 │
└─────────────────────────────────────────────────────────────┘
```

### JavaScript (live calculations)
Unit conversion functions:
- MM → FT: val / 304.8
- CM → FT: val / 30.48
- INCH → FT: val / 12
- FT → FT: val

Per-row live display (not editable):
- Volume per box (ft³)
- Boxes per pallet
- No. of pallets

Summary panel (updates on any input change):
- Total pallets (sum of all rows)
- Actual pallets = total × (1 + variance/100)
- Billable area = actual_pallets × 25

All computed values are **display-only inputs** (readonly) in the form.

---

## Download (DOCX / PDF)

### What appears in the downloaded document:
- List of products: name + type of operation
- Billable / Storage Area (final sq.ft figure)

### What does NOT appear:
- Product dimensions (L, W, H)
- Unit conversions
- Volume/box, boxes/pallet, intermediate calculations
- Variance %, pallet dimensions

### Implementation:
- Pass `quotation.products.all()` and `quotation.billable_storage_area_sqft` to the DOCX generator
- Add replacement map entries: `{{PRODUCT_LIST}}`, `{{BILLABLE_AREA}}`
- For local DOCX generator: add a paragraph after scope section

---

## Quotation Detail Page

Show Operational Scope section with:
- Products list (name, operation type, pallets)
- Summary: actual pallets, billable area
- Pallet dimension overrides (read-only display)
- No dimension calculations shown

---

## Implementation Order

1. `models_quotation.py` — add `QuotationProduct` model + Quotation operational fields
2. `migrations/0039_...py` — migration
3. `forms_quotation.py` — `QuotationProductForm` + `QuotationProductFormSet`
4. `views_quotation.py` — handle product formset in create/edit
5. `quotation_create.html` — new Operational Scope section + JS
6. `quotation_detail.html` — display operational scope
7. `quotation_pdf.py` + `quotation_docx_local.py` — add product summary to download
8. `create_test_quotation.py` — update test data with product rows
9. Verification: `python manage.py check` + CI tests
