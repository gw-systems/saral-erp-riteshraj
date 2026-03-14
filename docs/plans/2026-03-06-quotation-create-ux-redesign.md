# Quotation Create/Edit UX Redesign

**Date:** 2026-03-06
**Scope:** `quotation_create.html`, `forms_quotation.py`, `views_quotation.py`

---

## Change 1 — Remove POC & Status from form, auto-fill from user

**What:** Remove `point_of_contact`, `poc_phone`, and `status` from the rendered form. These are not user inputs:
- `status` is system-controlled (always starts `draft`, transitions via dedicated UI)
- `point_of_contact` and `poc_phone` are auto-filled from the logged-in user

**Backend (views_quotation.py):**
- In `quotation_create`: after `form.save(commit=False)`, set:
  ```python
  quotation.point_of_contact = request.user.get_full_name()
  quotation.poc_phone = request.user.phone or ''
  quotation.status = 'draft'
  ```
- In `quotation_edit`: do NOT overwrite `point_of_contact`/`poc_phone` (preserve original creator's info)
- `status` field is already excluded from edit form (transitions are via `quotation_transition`)

**Form (forms_quotation.py):**
- Remove `point_of_contact`, `poc_phone`, `status` from `Meta.fields` list
- Remove their widget definitions

**Template (quotation_create.html):**
- Remove the "Point of Contact" and "Status" fields from "Quotation Details" section
- Quotation Details section becomes: Validity Period | GST Rate (2 fields, side by side)

---

## Change 2 — Operational Scope compact grid

**What:** Replace the current 5-column single-row layout with a 2-row grid.

**Layout:**
```
Row 1 (2 cols):  Total Boxes | Variance %
Row 2 (3 cols):  Pallet L (ft) | Pallet W (ft) | Pallet H (ft)
```

**Template change:** Replace `grid grid-cols-5 gap-4` with two separate `<div class="grid">` blocks:
```html
<div class="grid grid-cols-2 gap-4 mb-4">
  Total Boxes | Variance %
</div>
<div class="grid grid-cols-3 gap-4 mb-6">
  Pallet L | Pallet W | Pallet H
</div>
```

No backend or model changes needed.

---

## Change 3 — SKU section rename + duplicate validation

**What:**
- Rename "Add Product" button → "Add SKU"
- Rename section header "Products / SKUs" (already correct label in template)
- Add JS duplicate validation: on form submit, if ≥2 SKU rows share the same `prod-name` value AND each has `prod-share` = 100, show inline error and block save

**Validation logic (JS):**
```js
// On form submit:
const rows = document.querySelectorAll('.product-row');
const nameShareMap = {};
for (const row of rows) {
  const name = row.querySelector('.prod-name').value.trim().toLowerCase();
  const share = parseFloat(row.querySelector('.prod-share').value) || 0;
  if (!name) continue;
  if (!nameShareMap[name]) nameShareMap[name] = [];
  nameShareMap[name].push(share);
}
const dupes = Object.entries(nameShareMap)
  .filter(([name, shares]) => shares.length > 1 && shares.every(s => s === 100));
if (dupes.length > 0) {
  // Show error banner, prevent submit
  const names = dupes.map(([n]) => n).join(', ');
  showSkuError(`Duplicate SKU with 100% share: ${names}. Adjust Share % or remove duplicates.`);
  return false;
}
```

**Template:** Add an inline error `<div id="sku-error">` above the product rows container, hidden by default.

---

## Change 4 — Commercial type: pill toggle instead of dropdown

**What:** The `commercial_type` field (Vendor Rate / Market Rate) becomes a pill toggle UI. The actual form value is stored in a hidden `<input type="hidden" name="commercial_type">`.

**Layout:**
```html
<div class="inline-flex rounded-lg border border-gray-300 overflow-hidden">
  <button type="button" data-value="vendor_rate" class="toggle-pill px-5 py-2 text-sm font-medium ...">
    Vendor Rate
  </button>
  <button type="button" data-value="market_rate" class="toggle-pill px-5 py-2 text-sm font-medium ...">
    Market Rate
  </button>
</div>
<input type="hidden" id="commercial_type_input" name="commercial_type" value="vendor_rate">
```

Active pill: `bg-blue-600 text-white`, Inactive: `bg-white text-gray-700 hover:bg-gray-50`.

**JS:** On pill click → update hidden input value, update active styles, trigger label update in cost tables (shows "Vendor Rate" or "Market Rate" as the column header label in cost input tables).

**Form:** Keep `commercial_type` in `Meta.fields` (backend still reads it), but the widget is irrelevant since the template renders the toggle manually with a hidden input.

---

## Change 5 — Separate cost input table + auto-generated client pricing table

### Layout within Locations & Pricing section

```
┌─────────────────────────────────────────────────────┐
│  Commercial Type:  [Vendor Rate] [Market Rate]       │  ← global toggle (above all locations)
│  Default Markup %: [26.00]                           │
└─────────────────────────────────────────────────────┘

┌─ Location 1 ─────────────────────────────────────────┐
│  Location Name: ___________  Display Order: ___       │
│                                                       │
│  Cost Input  (label: "Vendor Costs" or "Market Rates")│
│  ┌──────────────────┬──────────┬────────┬──────────┐  │
│  │ Description      │ Rate     │ Qty    │ Total    │  │
│  ├──────────────────┼──────────┼────────┼──────────┤  │
│  │ Storage Charges  │ [150]    │ [100]  │ 15,000   │  │
│  │ Handling In      │ [12]     │ [500]  │ 6,000    │  │
│  │ ...              │          │        │          │  │
│  └──────────────────┴──────────┴────────┴──────────┘  │
│  [+ Add Item]                                         │
│                                                       │
│  Client Pricing  (read-only, auto-calculated)         │
│  ┌──────────────────┬──────────┬────────┬──────────┐  │
│  │ Description      │ Rate     │ Qty    │ Total    │  │
│  ├──────────────────┼──────────┼────────┼──────────┤  │
│  │ Storage Charges  │  189.00  │  100   │ 18,900   │  │
│  │ Handling In      │   15.12  │  500   │  7,560   │  │
│  ├──────────────────┼──────────┴────────┼──────────┤  │
│  │                  │ Subtotal          │ 26,460   │  │
│  │                  │ GST 18%           │  4,763   │  │
│  │                  │ Grand Total       │ 31,223   │  │
│  └──────────────────┴───────────────────┴──────────┘  │
└───────────────────────────────────────────────────────┘
```

### Data flow

- Cost Rate + Cost Qty → user enters in cost input table (these map to `vendor_unit_cost` + `vendor_quantity` form fields)
- Client Rate = Cost Rate × (1 + markup/100) — computed in JS
- Client Qty = Cost Qty (same value mirrored)
- `unit_cost` and `quantity` hidden inputs are auto-populated from the calculated client values before form submit
- Markup % per location: a small input above the client table, defaulting to `default_markup_pct`
- If cost value is non-numeric (e.g. "at actual"), client rate shows "At actual" too (no calculation)

### Real-time update triggers

Any change to:
- Cost rate input
- Cost qty input
- Per-location markup % input
- Global default markup % field

...triggers recalculation of that location's client pricing table and totals.

### Item form fields mapping

| UI Label | Form field written |
|---|---|
| Cost Rate (user input) | `vendor_unit_cost` |
| Cost Qty (user input) | `vendor_quantity` |
| Client Rate (calculated, hidden input) | `unit_cost` |
| Client Qty (mirrors cost qty, hidden input) | `quantity` |

The cost input table renders visible inputs. The client pricing table is purely display (no inputs). Hidden inputs `unit_cost` and `quantity` are populated by JS just before form submit.

### "At actual" handling

If Cost Rate is non-numeric (blank or text like "at actual"), the client rate cell shows "At actual" and the total shows "—". The `unit_cost` hidden input gets the same text value as `vendor_unit_cost`.

### Markup display

- Above each location's client table: `Markup: [26.00] %` input (editable, defaults from global)
- This per-location markup overrides the global for that location's calculation
- On change, recalculates only that location

### Item row deletion

Deleting an item from the cost table also removes the corresponding row from the client pricing display.

### Custom description

Still shown as a small optional input below each cost row (under the description dropdown).

### Storage unit type field

Shown conditionally below the cost row when `item_description = 'storage_per_pallet'` (same behaviour as today).

---

## Files to change

| File | Change |
|---|---|
| `templates/projects/quotations/quotation_create.html` | All 5 changes |
| `projects/forms_quotation.py` | Remove POC, poc_phone, status from fields |
| `projects/views_quotation.py` | Auto-set POC from user on create |

No model migrations needed. No new fields. The existing `vendor_unit_cost`, `vendor_quantity`, `unit_cost`, `quantity` fields are already in the model.
