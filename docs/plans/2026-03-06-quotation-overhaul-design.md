# Quotation Module Overhaul — Design Document
**Date:** 2026-03-06
**Scope:** 7 features + commercial table rework
**Reference:** https://github.com/gw-systems/Quotation-Generator.git

---

## Key Constraint: Line Item Structure (from reference repo)

The reference repo's `QuotationItem` has **only client-facing fields**:
- `item_description` (choices: storage_charges, inbound_handling, outbound_handling, pick_pack, packaging_material, labelling_services, wms_platform, value_added)
- `storage_unit_type` (per_sqft, per_pallet, per_unit, per_lumpsum, per_order) — shown only for storage_charges
- `unit_cost` (CharField — numeric or "at actual")
- `quantity` (CharField — numeric or "at actual")
- `order`

**The reference form JS auto-populates all 8 item types per location on load/add.**
**Triplet logic:** user can edit unit_cost OR quantity OR total — any two compute the third.

The current ERP model adds `vendor_unit_cost` and `vendor_quantity` inline on the same row.
**New design separates cost input from client pricing into two distinct conceptual tables, but keeps the SAME `QuotationItem` model fields** — no schema bloat.

---

## Architecture Decision: How to Handle Cost vs Client Pricing

### Chosen Approach: Two-Pass Entry with Same Model

**Model additions to `Quotation`:**
```python
commercial_type = CharField(choices=[('vendor', 'Vendor Commercial'), ('market_rate', 'Market Rate')], default='vendor')
default_markup_pct = DecimalField(default=26.00)  # Stored so user can change per-quotation
```

`QuotationItem` keeps existing fields. No rename needed:
- `vendor_unit_cost`, `vendor_quantity` = **cost side** (what we pay)
- `unit_cost`, `quantity` = **client side** (what client pays)

**Frontend UX flow:**
1. Toggle at top of each location: `[Vendor Commercial] [Market Rate]` — sets `quotation.commercial_type`
2. **Cost table** (left/top panel): user enters `vendor_unit_cost` + `vendor_quantity` per row
3. **Client pricing table** (right/bottom panel): auto-filled as `cost × (1 + markup_pct/100)`, editable
4. Live margin badge updates as user changes either side
5. Margin indicator:
   - ≥26% → green ✓
   - 15–25.99% → amber ⚠ → auto-routes to `pending_approval` on save
   - <15% → red ✗ → blocked, cannot save, must fix

**Triplet logic preserved:** within client pricing table, user can edit rate OR qty OR total (any two derive third) — same as reference JS.

**PDF/DOCX output:** Only renders client pricing. Cost table is internal only.

---

## Feature 1: Commercial Table Rework

### Model Changes

**`Quotation` — add 2 fields:**
```python
commercial_type = models.CharField(
    max_length=20,
    choices=[('vendor', 'Vendor Commercial'), ('market_rate', 'Market Rate')],
    default='vendor'
)
default_markup_pct = models.DecimalField(
    max_digits=5, decimal_places=2, default=Decimal('26.00'),
    help_text='Default markup % applied to cost to derive client price'
)
```

**`QuotationItem` — rename existing margin field + add markup field:**
- `vendor_unit_cost` → keep as-is (cost side rate)
- `vendor_quantity` → keep as-is (cost side qty)
- `unit_cost` → client side rate (auto-filled from cost × markup)
- `quantity` → client side qty

**Margin/Markup logic change:**
- **OLD:** `margin_pct = (client - cost) / client × 100` (margin on selling price)
- **NEW:** `markup_pct = (client - cost) / cost × 100` (markup on cost)
- Thresholds: ≥26% free, 15–26% needs approval, <15% auto-blocked
- Update `MINIMUM_MARGIN_PCT = Decimal('26.00')` and introduce `AUTO_REJECT_PCT = Decimal('15.00')`
- Update `margin_pct` property on `Quotation` to use markup formula

### View Changes (`views_quotation.py`)

**`_compute_margin_from_post()`:** Update formula to markup.

**`quotation_create` / `quotation_edit`:**
- Add `AUTO_REJECT_PCT = Decimal('15.00')`
- If `markup_pct < 15` → return error "Margin too low. Minimum 15% required. Directors will not review sub-15% requests."
- If `15 <= markup_pct < 26` → auto-set `status='pending_approval'`, `margin_override_requested=True`
- If `markup_pct >= 26` → save normally

**New AJAX endpoint:** `quotation_auto_price(request)` — POST with `{cost_unit, cost_qty, markup_pct}` → returns `{client_unit, client_qty, client_total, markup_pct}`. Called by JS as user types in cost table.

### Form Changes (`forms_quotation.py`)

`QuotationItemForm` — no field changes, but validation:
- If vendor cost is filled, client cost must also be filled (no blank client price)

Add `commercial_type` and `default_markup_pct` to `QuotationForm`.

### Frontend (`quotation_create.html` + JS)

**Per-location layout:**
```
┌─ Location: [Name] ──────────────────────────────────────┐
│  Cost Type: (●) Vendor Commercial  ( ) Market Rate       │
│                                                          │
│  ┌─ COST TABLE ───────────────────────────────────────┐ │
│  │ Service | Rate (₹) | Qty | Total                   │ │
│  │ [8 pre-filled rows, editable]                       │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  Markup: [26]% applied → CLIENT PRICING                  │
│                                                          │
│  ┌─ CLIENT PRICING (auto-calculated, editable) ───────┐ │
│  │ Service | Rate (₹) | Qty | Total | Markup%          │ │
│  │ [8 rows auto-filled from cost × 1.26]               │ │
│  └────────────────────────────────────────────────────┘ │
│                                                          │
│  Overall Markup: [██████░░░░] 26.3%  ✓ Good             │
│  Location Total: ₹1,26,000 + GST ₹22,680 = ₹1,48,680   │
└──────────────────────────────────────────────────────────┘
```

**JS additions:**
- `applyMarkupToRow(locationIdx, rowIdx)` — reads cost fields, calculates client fields
- `applyMarkupToAllRows(locationIdx)` — applies markup to all 8 rows on markup % change
- `calculateLocationMarkup(locationIdx)` — overall markup badge per location
- Triplet logic applied to client table (same as reference repo JS)
- Cost table items are `disabled` in output form so only client fields POST — actually both POST, but only client side goes to PDF

---

## Feature 2: Status Transitions via UI

### New Status: `voided`

Add to `Quotation.STATUS_CHOICES`:
```python
('voided', 'Voided')
```

### New View: `quotation_transition`

```python
@login_required
def quotation_transition(request, quotation_id):
    """Handle status transitions from detail page buttons."""
```

**Allowed transitions:**
| From | To | Who |
|------|----|-----|
| `sent` | `accepted` | Any staff |
| `sent` | `rejected` | Any staff |
| `accepted` | `draft` | Director/Admin |
| `rejected` | `draft` | Director/Admin |
| `draft` | `voided` | Director/Admin |

**New URL:** `quotations/<id>/transition/` → `quotation_transition`

### Detail Page Buttons

Conditionally render based on current status:
- Status=`sent`: `[✓ Mark Accepted]` `[✗ Mark Rejected]`
- Status=`accepted` or `rejected`: `[↩ Reopen as Draft]` (directors only)
- Status=`draft`: `[🚫 Void]` (directors only, with confirmation modal)

---

## Feature 3: Versioning / Revisions

### New Model: `QuotationRevision`

```python
class QuotationRevision(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='revisions')
    revision_number = models.IntegerField()
    snapshot = models.JSONField()  # Full snapshot: quotation fields + all locations/items
    reason = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['quotation', 'revision_number']]
        ordering = ['-revision_number']
```

### Revision Logic

**When triggered:** Editing a quotation with status `sent` or `accepted`.

**In `quotation_edit` view:**
1. Before saving, check if `quotation.status in ('sent', 'accepted')`
2. If yes, snapshot current state to `QuotationRevision`
3. Revision number = `quotation.revisions.count() + 1`
4. Snapshot includes: all quotation fields + locations + items (serialized to dict)
5. Status auto-resets to `draft` after revision (editing a sent quote creates new draft)

**Snapshot helper function:** `_snapshot_quotation(quotation)` → returns dict.

### Detail Page

Revision history accordion below audit logs:
```
Revision History
▶ Rev 2 — 2026-03-06 by Jignesh — "Updated storage rate" [View]
▶ Rev 1 — 2026-03-01 by Jignesh — Original [View]
```

**New URL:** `quotations/<id>/revisions/<rev_num>/` → `quotation_revision_view` (read-only detail of snapshot)

---

## Feature 4: Expiry Alerts

### Model Change

Add to `Quotation`:
```python
expiry_notified = models.BooleanField(default=False)
```

### New Status Value: `expired`

Add to `STATUS_CHOICES`:
```python
('expired', 'Expired')
```

### Management Command: `check_quotation_expiry`

**File:** `projects/management/commands/check_quotation_expiry.py`

Logic:
1. Find all `Quotation` where `status='sent'` and `date + validity_period < today`
2. For each: set `status='expired'`, `expiry_notified=True`, log audit action `status_changed`
3. Log count at end

**Running:** Add to crontab or Django-Q scheduler.

### UI

- List page: show amber "Expired" badge if status=`expired`
- Detail page: show banner "This quotation expired on {validity_date}"
- List filter: add `expired` to status dropdown

---

## Feature 5: Duplicate / Clone

### New View: `quotation_clone`

```python
@login_required
@transaction.atomic
def quotation_clone(request, quotation_id):
    """Clone a quotation — new number, all locations/items/products copied, status=draft."""
```

**Logic:**
1. Load original with `prefetch_related('locations__items', 'products')`
2. Create new `Quotation` (pk=None, quotation_number auto-generated, status='draft', created_by=request.user)
3. For each location → clone `QuotationLocation`
4. For each item in location → clone `QuotationItem`
5. For each product → clone `QuotationProduct`
6. Log audit: action=`created`, metadata=`{'cloned_from': original.quotation_number}`
7. Redirect to `quotation_edit` of new quotation

**New URL:** `quotations/<id>/clone/` POST → `quotation_clone`

**UI:** "Clone" button on detail page.

---

## Feature 6: Client Acceptance Link

### New Models

```python
class QuotationAcceptanceToken(models.Model):
    quotation = models.OneToOneField(Quotation, on_delete=models.CASCADE, related_name='acceptance_token')
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    expires_at = models.DateTimeField()  # = quotation.validity_date as datetime
    used_at = models.DateTimeField(null=True, blank=True)
    accepted = models.BooleanField(null=True)  # None=pending, True=accepted, False=rejected
    client_remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### Views

**`quotation_generate_acceptance_link(request, quotation_id)`** — staff only
- Creates/regenerates `QuotationAcceptanceToken`
- Returns link: `{BASE_URL}/quotations/accept/{token}/`
- Optionally emails link to client via Gmail API

**`quotation_accept_public(request, token)`** — NO `@login_required`
- GET: Show read-only quotation summary (client-facing, clean template, no ERP nav)
- POST: Record `accepted=True/False`, `client_remarks`, `used_at=now()`
- Transitions quotation status to `accepted` or `rejected`
- Logs audit with `action='status_changed'`, metadata=`{'via': 'client_link'}`
- Shows thank-you page

**Token validation:**
- `expires_at < now()` → show "This link has expired" page
- `used_at is not None` → show "Already responded" page

### New URLs

```python
path('quotations/<int:quotation_id>/acceptance-link/', ..., name='quotation_acceptance_link'),
path('quotations/accept/<uuid:token>/', ..., name='quotation_accept_public'),
```

### Public Template

`templates/projects/quotations/quotation_accept_public.html` — standalone (no base.html ERP nav), shows:
- Godamwale logo + quotation summary
- Accept / Reject buttons
- Remarks textarea
- Expiry date reminder

---

## Feature 7: Win/Loss Dashboard

### New View: `quotation_dashboard`

Director/admin only. URL: `quotations/dashboard/`

### Metrics

```
┌─ This Month ──────────────────────────────────────────┐
│  Total Sent: 12    Won: 7 (58%)    Lost: 3 (25%)      │
│  Avg Markup (Won): 31.2%                               │
│  Pipeline Value: ₹45,60,000                            │
└───────────────────────────────────────────────────────┘
┌─ Pending Actions ─────────────────────────────────────┐
│  Approval Required: 3 quotations                       │
│  Expiring This Week: 5 quotations                      │
│  Client Response Pending: 8 quotations (sent, no token)│
└───────────────────────────────────────────────────────┘
┌─ Top Clients by Value (Won) ───────────────────────────┐
│  1. ABC Logistics — ₹12,40,000                        │
│  2. XYZ Retail — ₹9,20,000                            │
└───────────────────────────────────────────────────────┘
```

**Implementation:** Pure Django ORM aggregations, Tailwind CSS cards. No external charting library.

```python
from django.db.models import Count, Sum, Avg, Q
```

---

## Margin Logic Summary (Updated)

| Markup % | Action |
|----------|--------|
| ≥26% | Save freely as draft |
| 15–25.99% | Save as `pending_approval`, notify directors |
| <15% | **Blocked.** Error shown. Directors NOT notified. |

**Formula:** `markup_pct = (client_total - cost_total) / cost_total × 100`

Where cost = vendor_unit_cost × vendor_quantity, client = unit_cost × quantity.

---

## Migration Plan

1. Add `commercial_type`, `default_markup_pct` to `Quotation`
2. Add `expiry_notified` to `Quotation`
3. Add `voided`, `expired` to `STATUS_CHOICES`
4. Create `QuotationRevision` model
5. Create `QuotationAcceptanceToken` model
6. Run migrations

---

## Files to Change

| File | Change |
|------|--------|
| `projects/models_quotation.py` | Add fields, new models, update properties |
| `projects/views_quotation.py` | Add 5 new views, update margin logic |
| `projects/forms_quotation.py` | Add `commercial_type`, `default_markup_pct` to `QuotationForm` |
| `projects/urls.py` | Add 6 new URL patterns |
| `templates/projects/quotations/quotation_create.html` | Complete frontend redesign (cost + client tables) |
| `templates/projects/quotations/quotation_detail.html` | Status buttons, revision history, clone button |
| `templates/projects/quotations/quotation_list.html` | Expired badge, dashboard link |
| `templates/projects/quotations/quotation_accept_public.html` | New — public acceptance page |
| `templates/projects/quotations/quotation_dashboard.html` | New — win/loss dashboard |
| `templates/projects/quotations/quotation_revision.html` | New — read-only revision view |
| `projects/management/commands/check_quotation_expiry.py` | New — expiry management command |
| `projects/services/quotation_docx_local.py` | Remove vendor table from output |

---

## Reference JS Patterns to Preserve

From `gw-systems/Quotation-Generator`:
- **Auto-populate all 8 item types** on location add (`populateAllItemsForLocation`)
- **Triplet logic** on client table: any 2 of (rate, qty, total) derive the third
- **Storage unit type dropdown** shown only for `storage_charges` item
- **Management form update** (`updateItemManagementForm`) on every add/remove
- Template-clone pattern (hidden `.item-template` row cloned for new rows)
