# Porter Invoice Single Edit UX — Design Doc
Date: 2026-03-09

## Changes

### 1. CRN Field — Blank by Default
- On upload, `fields.crn` stays empty (do NOT pre-fill with extracted CRN)
- Placeholder shows original extracted CRN as hint
- If user types a value → that becomes the new CRN
- If left blank → original CRN (`file_record.crn`) used for PDF edit and filename

### 2. Invoice Date — Date Picker → DD MMM YYYY
- `<input type="date">` picker instead of free-text
- On change: convert value (YYYY-MM-DD) to `DD MMM YYYY` format for `fields.date`
  - Example: `2026-10-27` → `27 Oct 2026`
- `fields.date` (sent to backend) holds the formatted string

### 3. Pickup/Drop Date Autofill — DD/MM/YYYY
- When invoice date is picked, auto-fill `fields.pickup_date` and `fields.drop_date` as `DD/MM/YYYY`
  - Example: `2026-10-27` → `27/10/2026`
- Only autofills if those fields are currently empty (user can override)

### 4. Download Filename
- Backend: `invoice_{crn}.pdf` where crn = `fields['crn'].strip() or file_record.crn`
- Already partially correct at views line 493; confirm fallback to `file_record.crn`

## Files Changed
- `templates/operations/porter_invoice_single.html` — input type, JS logic
- `operations/views_porter_invoice.py` — filename fallback (line ~493)
