# Quotation Create/Edit UX Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Overhaul the quotation create/edit form with 5 UX improvements: remove auto-managed fields from the form (POC, status), compact the Operational Scope grid, add SKU duplicate validation, replace the commercial type dropdown with a pill toggle, and split cost input / client pricing into two separate tables per location with real-time markup calculation.

**Architecture:** All changes are frontend-heavy (HTML template + JS). Backend changes are minimal: remove 3 fields from `QuotationForm` and auto-set them in `quotation_create` view. The cost/client split reuses existing model fields (`vendor_unit_cost`/`vendor_quantity` for cost input; `unit_cost`/`quantity` populated by JS before submit). No migrations needed.

**Tech Stack:** Django templates, Tailwind CSS, vanilla JavaScript, existing `quotation_create.html` (1609 lines), `forms_quotation.py`, `views_quotation.py`

---

## Task 1: Remove POC, poc_phone, and status from form

**Files:**
- Modify: `projects/forms_quotation.py:35-67` (Meta.fields list)
- Modify: `projects/views_quotation.py:386-393` (quotation_create save block)

### Step 1: Remove 3 fields from QuotationForm.Meta.fields

In `projects/forms_quotation.py`, remove `'point_of_contact'`, `'poc_phone'`, and `'status'` from the `fields` list at lines 45-49:

```python
# BEFORE (lines 44-49):
            # Quotation details
            'point_of_contact',
            'poc_phone',
            'validity_period',
            'gst_rate',
            'status',

# AFTER:
            # Quotation details
            'validity_period',
            'gst_rate',
```

Also remove their widget definitions from `Meta.widgets` (search for `'point_of_contact':`, `'poc_phone':`, `'status':` blocks and delete them).

### Step 2: Auto-set POC from logged-in user in quotation_create view

In `projects/views_quotation.py`, at line 387 (after `quotation.created_by = request.user`), add:

```python
            quotation.created_by = request.user
            # Auto-fill POC from the creating user
            quotation.point_of_contact = request.user.get_full_name()
            quotation.poc_phone = request.user.phone or ''
```

`status` already defaults to `'draft'` in the model, so no change needed there.

### Step 3: Remove POC and Status fields from the template

In `templates/projects/quotations/quotation_create.html`, the "Quotation Details" section (around line 105-159) has a `grid grid-cols-3 gap-6` with 4 fields. Remove the Point of Contact `<div>` (lines ~127-135) and the Status `<div>` (lines ~137-146). The section becomes a `grid grid-cols-2 gap-6` with just Validity Period and GST Rate:

```html
<!-- Section 2: Quotation Details -->
<div class="bg-white shadow rounded-lg p-6">
    <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
        <svg width="20" height="20" aria-hidden="true" class="h-5 w-5 text-blue-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
        </svg>
        Quotation Details
    </h2>
    <div class="grid grid-cols-2 gap-6">
        <div>
            <label for="{{ form.validity_period.id_for_label }}" class="block text-sm font-medium text-gray-700 mb-2">
                Validity Period (Days)
            </label>
            {{ form.validity_period }}
            {% if form.validity_period.errors %}
                <p class="mt-1 text-sm text-red-600">{{ form.validity_period.errors.0 }}</p>
            {% endif %}
        </div>
        <div>
            <label for="{{ form.gst_rate.id_for_label }}" class="block text-sm font-medium text-gray-700 mb-2">
                GST Rate (%)
            </label>
            {{ form.gst_rate }}
            {% if form.gst_rate.errors %}
                <p class="mt-1 text-sm text-red-600">{{ form.gst_rate.errors.0 }}</p>
            {% endif %}
        </div>
    </div>
</div>
```

### Step 4: Verify system check passes

```bash
cd /Users/apple/Documents/DataScienceProjects/ERP
source venv/bin/activate
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

---

## Task 2: Compact Operational Scope grid into 2 rows

**Files:**
- Modify: `templates/projects/quotations/quotation_create.html:171-217`

### Step 1: Replace the 5-column grid with two separate grids

Find the `<!-- Pallet Configuration -->` block (around line 171) and replace the `grid grid-cols-5 gap-4 mb-6` div with two grids:

```html
<!-- Pallet Configuration -->
<!-- Row 1: Total Boxes + Variance -->
<div class="grid grid-cols-2 gap-4 mb-4">
    <div>
        <label for="{{ form.operational_total_boxes.id_for_label }}" class="block text-sm font-medium text-gray-700 mb-2">
            Total Boxes
        </label>
        {{ form.operational_total_boxes }}
        {% if form.operational_total_boxes.errors %}
            <p class="mt-1 text-sm text-red-600">{{ form.operational_total_boxes.errors.0 }}</p>
        {% endif %}
    </div>
    <div>
        <label for="{{ form.operational_variance_pct.id_for_label }}" class="block text-sm font-medium text-gray-700 mb-2">
            Variance %
        </label>
        {{ form.operational_variance_pct }}
        {% if form.operational_variance_pct.errors %}
            <p class="mt-1 text-sm text-red-600">{{ form.operational_variance_pct.errors.0 }}</p>
        {% endif %}
    </div>
</div>
<!-- Row 2: Pallet dimensions -->
<div class="grid grid-cols-3 gap-4 mb-6">
    <div>
        <label for="{{ form.operational_pallet_l.id_for_label }}" class="block text-sm font-medium text-gray-700 mb-2">
            Pallet L (ft)
        </label>
        {{ form.operational_pallet_l }}
        {% if form.operational_pallet_l.errors %}
            <p class="mt-1 text-sm text-red-600">{{ form.operational_pallet_l.errors.0 }}</p>
        {% endif %}
    </div>
    <div>
        <label for="{{ form.operational_pallet_w.id_for_label }}" class="block text-sm font-medium text-gray-700 mb-2">
            Pallet W (ft)
        </label>
        {{ form.operational_pallet_w }}
        {% if form.operational_pallet_w.errors %}
            <p class="mt-1 text-sm text-red-600">{{ form.operational_pallet_w.errors.0 }}</p>
        {% endif %}
    </div>
    <div>
        <label for="{{ form.operational_pallet_h.id_for_label }}" class="block text-sm font-medium text-gray-700 mb-2">
            Pallet H (ft)
        </label>
        {{ form.operational_pallet_h }}
        {% if form.operational_pallet_h.errors %}
            <p class="mt-1 text-sm text-red-600">{{ form.operational_pallet_h.errors.0 }}</p>
        {% endif %}
    </div>
</div>
```

---

## Task 3: Rename "Add Product" → "Add SKU" + duplicate validation

**Files:**
- Modify: `templates/projects/quotations/quotation_create.html`

### Step 1: Rename button and section header

Find (around line 222-227):
```html
<h3 class="text-md font-semibold text-gray-700">Products / SKUs</h3>
<button type="button" id="add-product" class="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 transition">
    + Add Product
</button>
```

Change button text to `+ Add SKU`.

### Step 2: Add SKU error banner above product rows container

After the `<div class="flex items-center justify-between mb-3">` block (after the button row), add:

```html
<!-- SKU duplicate error banner (hidden by default) -->
<div id="sku-error" class="hidden mb-3 bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 font-medium"></div>
```

### Step 3: Add duplicate validation in form submit handler

In the JS `submit` event listener (around line 1293), inside the handler before the `errors.length > 0` block, add SKU duplicate check:

```js
// SKU duplicate check: same name + both share% = 100 is invalid
const skuRows = productContainer.querySelectorAll('.product-row:not(.product-deleted)');
const skuMap = {};
skuRows.forEach(function(row) {
    const name = (row.querySelector('.prod-name').value || '').trim().toLowerCase();
    const share = parseFloat(row.querySelector('.prod-share').value) || 0;
    if (!name) return;
    if (!skuMap[name]) skuMap[name] = [];
    skuMap[name].push(share);
});
const skuErrorEl = document.getElementById('sku-error');
const dupeNames = Object.entries(skuMap)
    .filter(([, shares]) => shares.length > 1 && shares.every(s => s === 100))
    .map(([name]) => name);
if (dupeNames.length > 0) {
    if (skuErrorEl) {
        skuErrorEl.textContent = 'Duplicate SKU with 100% share: "' + dupeNames.join('", "') + '". Adjust Share % or remove duplicates.';
        skuErrorEl.classList.remove('hidden');
        skuErrorEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    e.preventDefault();
    return;
}
if (skuErrorEl) skuErrorEl.classList.add('hidden');
```

---

## Task 4: Replace commercial_type dropdown with pill toggle

**Files:**
- Modify: `templates/projects/quotations/quotation_create.html:264-291`

### Step 1: Replace the Commercial Settings section HTML

Find the `<!-- Section 2b: Commercial Settings -->` block and replace the `{{ form.commercial_type }}` field with a pill toggle + hidden input. The `default_markup_pct` field stays as-is.

```html
<!-- Section 2b: Commercial Settings -->
<div class="bg-white shadow rounded-lg p-6">
    <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
        <svg width="20" height="20" aria-hidden="true" class="h-5 w-5 text-purple-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 11h.01M12 11h.01M15 11h.01M12 7h.01M15 7h.01M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
        </svg>
        Commercial Settings
    </h2>
    <div class="grid grid-cols-2 gap-6">
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">Cost Type</label>
            <div class="inline-flex rounded-lg border border-gray-300 overflow-hidden">
                <button type="button" data-value="vendor_rate" class="commercial-toggle-pill px-5 py-2 text-sm font-medium transition">
                    Vendor Rate
                </button>
                <button type="button" data-value="market_rate" class="commercial-toggle-pill px-5 py-2 text-sm font-medium border-l border-gray-300 transition">
                    Market Rate
                </button>
            </div>
            <input type="hidden" id="id_commercial_type" name="commercial_type" value="{{ form.commercial_type.value|default:'vendor_rate' }}">
            <p class="mt-2 text-xs text-gray-500">Determines whether cost inputs are vendor rates or market rates.</p>
        </div>
        <div>
            <label for="{{ form.default_markup_pct.id_for_label }}" class="block text-sm font-medium text-gray-700 mb-2">
                Default Markup % <span class="text-red-500">*</span>
            </label>
            {{ form.default_markup_pct }}
            {% if form.default_markup_pct.errors %}
                <p class="mt-1 text-sm text-red-600">{{ form.default_markup_pct.errors.0 }}</p>
            {% endif %}
            <p class="mt-1 text-xs text-gray-500">Client price = Cost × (1 + Markup%). Min 26% or request approval.</p>
        </div>
    </div>
</div>
```

### Step 2: Add pill toggle JS (in the `<script>` block, near CONFIG section)

Add after the constants block (around line 675):

```js
// ========================================================================
// COMMERCIAL TYPE PILL TOGGLE
// ========================================================================
(function initCommercialToggle() {
    const pills = document.querySelectorAll('.commercial-toggle-pill');
    const hiddenInput = document.getElementById('id_commercial_type');
    if (!pills.length || !hiddenInput) return;

    function setActive(val) {
        pills.forEach(function(pill) {
            if (pill.dataset.value === val) {
                pill.classList.add('bg-blue-600', 'text-white');
                pill.classList.remove('bg-white', 'text-gray-700', 'hover:bg-gray-50');
            } else {
                pill.classList.remove('bg-blue-600', 'text-white');
                pill.classList.add('bg-white', 'text-gray-700', 'hover:bg-gray-50');
            }
        });
        hiddenInput.value = val;
        // Update cost table column header labels
        const costLabel = val === 'vendor_rate' ? 'Vendor Costs' : 'Market Rates';
        document.querySelectorAll('.cost-table-label').forEach(function(el) {
            el.textContent = costLabel;
        });
    }

    // Initialize from current value
    setActive(hiddenInput.value || 'vendor_rate');

    pills.forEach(function(pill) {
        pill.addEventListener('click', function() {
            setActive(pill.dataset.value);
        });
    });
})();
```

---

## Task 5: Split cost input / client pricing tables (the big one)

This is the core redesign. The item template is completely replaced. The existing `item-unit-cost`, `item-quantity`, `item-vendor-unit-cost`, `item-vendor-quantity` form fields are preserved but hidden — JS populates them before submit.

**Files:**
- Modify: `templates/projects/quotations/quotation_create.html` — item template, location section, JS

### Step 1: Replace the location items section HTML (inside the location template)

Find the `<!-- Items Section -->` block in the location form (around line 364-402) and replace it:

```html
<!-- Items Section -->
<div class="items-section space-y-4">

    <!-- Cost Input Table -->
    <div class="bg-orange-50 border border-orange-200 rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
            <h4 class="text-sm font-semibold text-orange-800 cost-table-label">Vendor Costs</h4>
            <button type="button" class="add-item px-3 py-1 bg-orange-600 text-white text-xs rounded hover:bg-orange-700 transition">
                + Add Item
            </button>
        </div>
        <div class="items-container space-y-2">
            <!-- Item rows injected here by JS -->
        </div>
    </div>

    <!-- Client Pricing Table (read-only, auto-calculated) -->
    <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
            <h4 class="text-sm font-semibold text-blue-800">Client Pricing</h4>
            <div class="flex items-center gap-2">
                <span class="text-xs text-gray-600">Markup:</span>
                <input type="number" class="loc-markup-pct w-20 px-2 py-1 text-sm border border-blue-300 rounded focus:ring-2 focus:ring-blue-400 text-center"
                       value="{{ form.default_markup_pct.value|default:'26.00' }}" step="0.01" min="0">
                <span class="text-xs text-gray-600">%</span>
            </div>
        </div>
        <!-- Client pricing display table -->
        <div class="overflow-x-auto">
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-xs text-blue-700 border-b border-blue-200">
                        <th class="text-left py-1 pr-3 font-medium w-2/5">Description</th>
                        <th class="text-right py-1 px-2 font-medium">Client Rate</th>
                        <th class="text-right py-1 px-2 font-medium">Qty</th>
                        <th class="text-right py-1 pl-2 font-medium">Total (₹)</th>
                    </tr>
                </thead>
                <tbody class="client-pricing-tbody">
                    <!-- Rows injected by JS -->
                </tbody>
                <tfoot>
                    <tr class="border-t border-blue-200 text-xs text-blue-700">
                        <td colspan="3" class="text-right py-1 pr-2 font-medium">Subtotal:</td>
                        <td class="text-right py-1 pl-2 font-semibold location-subtotal">₹0.00</td>
                    </tr>
                    <tr class="text-xs text-blue-700">
                        <td colspan="3" class="text-right py-1 pr-2 font-medium gst-label">GST (18%):</td>
                        <td class="text-right py-1 pl-2 font-semibold location-gst">₹0.00</td>
                    </tr>
                    <tr class="text-xs font-bold text-blue-900 border-t border-blue-300">
                        <td colspan="3" class="text-right py-1 pr-2">Grand Total:</td>
                        <td class="text-right py-1 pl-2 location-total text-blue-700">₹0.00</td>
                    </tr>
                </tfoot>
            </table>
        </div>
    </div>

</div>
```

### Step 2: Replace the item template (`<template id="item-template">`)

Replace the entire `<template id="item-template">` block with a cost-only input row. Hidden inputs for `unit_cost` and `quantity` (client side) are included but hidden — JS fills them on submit:

```html
<template id="item-template">
    <div class="item-row border border-orange-200 rounded bg-white p-2">
        <!-- Visible cost inputs -->
        <div class="grid grid-cols-12 gap-2 items-end">
            <div class="col-span-4">
                <label class="block text-xs font-medium text-gray-600 mb-1">Description</label>
                <select class="item-description w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-orange-400">
                    <option value="">Select...</option>
                    {% for value, label in item_choices %}
                    <option value="{{ value }}">{{ label }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-span-3">
                <label class="block text-xs font-medium text-orange-700 mb-1">Cost Rate</label>
                <input type="text" class="item-vendor-unit-cost w-full px-2 py-1.5 text-sm border border-orange-300 rounded focus:ring-2 focus:ring-orange-400" placeholder="Rate">
            </div>
            <div class="col-span-2">
                <label class="block text-xs font-medium text-orange-700 mb-1">Qty</label>
                <input type="text" class="item-vendor-quantity w-full px-2 py-1.5 text-sm border border-orange-300 rounded focus:ring-2 focus:ring-orange-400" placeholder="Qty">
            </div>
            <div class="col-span-2">
                <label class="block text-xs font-medium text-gray-500 mb-1">Cost Total</label>
                <p class="item-cost-total text-sm font-semibold text-orange-700 py-1.5">—</p>
            </div>
            <div class="col-span-1 flex items-end pb-0.5">
                <button type="button" class="delete-item w-full px-1.5 py-1.5 bg-red-100 text-red-600 rounded hover:bg-red-200 transition text-center">
                    <svg width="14" height="14" aria-hidden="true" class="h-3.5 w-3.5 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                    </svg>
                </button>
            </div>
        </div>
        <!-- Custom description (optional) -->
        <div class="mt-1.5">
            <input type="text" class="item-custom-desc w-full px-2 py-1 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-gray-400 text-gray-500" placeholder="Custom description (optional)">
        </div>
        <!-- Storage unit type (conditionally shown) -->
        <div class="storage-unit-field hidden mt-1.5">
            <select class="storage-unit-type w-full px-2 py-1 text-xs border border-gray-300 rounded focus:ring-1 focus:ring-gray-400">
                <option value="">Select storage unit...</option>
                {% for value, label in storage_unit_choices %}
                <option value="{{ value }}">{{ label }}</option>
                {% endfor %}
            </select>
        </div>
        <!-- Hidden client-side form fields (populated by JS before submit) -->
        <div class="hidden">
            <input type="text" class="item-unit-cost">
            <input type="text" class="item-quantity">
        </div>
    </div>
</template>
```

### Step 3: Add `syncClientFieldsBeforeSubmit()` function

In the JS section, add a function that copies calculated client values into the hidden `unit_cost` / `quantity` inputs. Call it from the `submit` event handler before validation:

```js
// ========================================================================
// SYNC CLIENT FIELDS FROM COST + MARKUP BEFORE SUBMIT
// ========================================================================
function syncClientFieldsBeforeSubmit() {
    document.querySelectorAll('.location-form:not([style*="display: none"])').forEach(function(loc) {
        const markupPct = parseFloat(loc.querySelector('.loc-markup-pct').value) || 26;
        const multiplier = 1 + markupPct / 100;

        loc.querySelectorAll('.item-row:not(.item-deleted)').forEach(function(row) {
            const vuc = row.querySelector('.item-vendor-unit-cost').value.trim();
            const vq = row.querySelector('.item-vendor-quantity').value.trim();
            const ucInput = row.querySelector('.item-unit-cost');
            const qInput = row.querySelector('.item-quantity');

            const vucNum = parseFloat(vuc);
            const vqNum = parseFloat(vq);

            if (!isNaN(vucNum) && !isNaN(vqNum)) {
                ucInput.value = (vucNum * multiplier).toFixed(2);
                qInput.value = vqNum.toFixed(2);
            } else {
                // Non-numeric (e.g. "at actual") — pass through as-is
                ucInput.value = vuc;
                qInput.value = vq;
            }
        });
    });
}
```

Call `syncClientFieldsBeforeSubmit()` at the top of the `submit` event handler, before the errors array check.

### Step 4: Add `updateClientPricingTable(locationEl)` function

This replaces `calculateLocationTotal`. It reads cost inputs + markup, rebuilds the client pricing tbody rows, and updates subtotal/GST/total in the tfoot:

```js
// ========================================================================
// CLIENT PRICING TABLE — real-time update
// ========================================================================
function updateClientPricingTable(locationEl) {
    if (!locationEl) return;
    const markupPct = parseFloat(locationEl.querySelector('.loc-markup-pct').value) || 26;
    const multiplier = 1 + markupPct / 100;
    const tbody = locationEl.querySelector('.client-pricing-tbody');
    if (!tbody) return;

    // Clear existing display rows
    tbody.innerHTML = '';

    let subtotal = 0;
    locationEl.querySelectorAll('.item-row:not(.item-deleted)').forEach(function(row) {
        const desc = row.querySelector('.item-description');
        const vuc = row.querySelector('.item-vendor-unit-cost').value.trim();
        const vq = row.querySelector('.item-vendor-quantity').value.trim();
        const customDesc = (row.querySelector('.item-custom-desc').value || '').trim();

        const vucNum = parseFloat(vuc);
        const vqNum = parseFloat(vq);
        const hasNumbers = !isNaN(vucNum) && !isNaN(vqNum);

        // Description label
        let descLabel = '';
        if (desc) {
            const opt = desc.querySelector(`option[value="${desc.value}"]`);
            descLabel = opt ? opt.textContent : desc.value;
        }
        if (customDesc) descLabel = customDesc;

        // Update cost total display in the cost row
        const costTotalEl = row.querySelector('.item-cost-total');
        if (costTotalEl) {
            costTotalEl.textContent = hasNumbers
                ? '₹' + (vucNum * vqNum).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                : '—';
        }

        // Client values
        let clientRate = '—', clientQty = '—', clientTotal = '—', clientTotalNum = 0;
        if (hasNumbers) {
            const cr = vucNum * multiplier;
            const ct = cr * vqNum;
            clientRate = '₹' + cr.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            clientQty = vqNum.toLocaleString('en-IN');
            clientTotal = '₹' + ct.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            clientTotalNum = ct;
            subtotal += ct;
        } else if (vuc) {
            clientRate = 'At actual';
            clientQty = vq || '—';
            clientTotal = '—';
        }

        const tr = document.createElement('tr');
        tr.className = 'text-xs border-b border-blue-100';
        tr.innerHTML = `
            <td class="py-1 pr-3 text-gray-700">${escapeHtml(descLabel) || '—'}</td>
            <td class="py-1 px-2 text-right text-gray-800">${clientRate}</td>
            <td class="py-1 px-2 text-right text-gray-800">${clientQty}</td>
            <td class="py-1 pl-2 text-right font-medium text-blue-800">${clientTotal}</td>
        `;
        tbody.appendChild(tr);
    });

    const gstRate = GST_RATE;
    const gst = subtotal * gstRate;
    const grandTotal = subtotal + gst;
    const gstPct = (gstRate * 100).toFixed(0);

    locationEl.querySelector('.location-subtotal').textContent = formatCurrency(subtotal);
    locationEl.querySelector('.location-gst').textContent = formatCurrency(gst);
    locationEl.querySelector('.location-total').textContent = formatCurrency(grandTotal);
    const gstLabel = locationEl.querySelector('.gst-label');
    if (gstLabel) gstLabel.textContent = `GST (${gstPct}%):`;

    calculateGrandTotal();
    updateMarginSummary();
}

function escapeHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
```

### Step 5: Replace `calculateLocationTotal` calls with `updateClientPricingTable`

Every place in the JS that calls `calculateLocationTotal(...)` should be changed to `updateClientPricingTable(...)`. Specifically:

- In `autoPopulateItems`: change `calculateLocationTotal(locationEl)` → `updateClientPricingTable(locationEl)`
- In `loadExistingItemsForLocation`: same change
- In `addItemRow`: change `calculateItemTotals(row)` → `updateClientPricingTable(row.closest('.location-form'))`
- In `onItemFieldInput` (bottom): change `calculateLocationTotal(...)` → `updateClientPricingTable(...)`
- In event delegation for `delete-location`: change `calculateGrandTotal()` call site — `updateClientPricingTable` handles that
- In event delegation for `delete-item`: change `calculateLocationTotal(locForm)` → `updateClientPricingTable(locForm)`
- In event delegation for `apply-markup-btn`: this button is **removed** from the UI (markup is now the `loc-markup-pct` input directly above the client table). Remove the `apply-markup-btn` event delegation block entirely.
- In `addLocationBtn` click handler: change `autoPopulateItems` call which already calls the updated version
- In initialization: change `calculateGrandTotal()` + `updateMarginSummary()` → just call `updateClientPricingTable` for each location on init

### Step 6: Update `onItemFieldInput` to only listen to cost fields

The old handler listened to `item-unit-cost`, `item-quantity`, `item-total-display` (client-side triplet). These are now hidden/unused for input. Replace the input listener logic:

```js
// Input events — cost fields trigger client pricing recalc
locationFormsContainer.addEventListener('input', function(e) {
    if (e.target.classList.contains('item-vendor-unit-cost') ||
        e.target.classList.contains('item-vendor-quantity') ||
        e.target.classList.contains('item-custom-desc') ||
        e.target.classList.contains('loc-markup-pct')) {
        updateClientPricingTable(e.target.closest('.location-form'));
    }
});
```

Also add a listener for `loc-markup-pct` change on the location container (it fires on the markup input above the client table):
```js
locationFormsContainer.addEventListener('change', function(e) {
    if (e.target.classList.contains('item-description')) {
        toggleStorageUnit(e.target.closest('.item-row'));
        updateClientPricingTable(e.target.closest('.location-form'));
    }
    if (e.target.classList.contains('loc-markup-pct')) {
        updateClientPricingTable(e.target.closest('.location-form'));
    }
});
```

### Step 7: Update `updateMarginSummary` to read from cost fields (already correct)

The existing `updateMarginSummary` already reads `item-vendor-unit-cost` and `item-vendor-quantity` for vendor total, and `item-unit-cost`/`item-quantity` for client total. Since we now populate `item-unit-cost`/`item-quantity` via `syncClientFieldsBeforeSubmit` but NOT live, the margin summary panel needs to compute client total from cost + markup directly:

Replace the client total accumulation inside `updateMarginSummary`:

```js
// BEFORE:
const uc = parseFloat(item.querySelector('.item-unit-cost').value);
const q = parseFloat(item.querySelector('.item-quantity').value);
if (!isNaN(uc) && !isNaN(q)) totalClient += uc * q;

// AFTER (compute from cost + markup):
const locForm = item.closest('.location-form');
const markupPct = parseFloat(locForm.querySelector('.loc-markup-pct').value) || 26;
const multiplier = 1 + markupPct / 100;
const vuc = parseFloat(item.querySelector('.item-vendor-unit-cost').value);
const vq = parseFloat(item.querySelector('.item-vendor-quantity').value);
if (!isNaN(vuc) && !isNaN(vq)) totalClient += vuc * multiplier * vq;
```

### Step 8: Update `calculateGrandTotal` to read from location totals

`calculateGrandTotal` reads `.location-total` text which is now set by `updateClientPricingTable`. No change needed there — it already works via the DOM.

### Step 9: Remove the old "apply-markup-btn" from Add Location clone

In the `addLocationBtn` click handler, remove any reference to `loc-markup-pct` initialization from cloning — the cloned location already has `loc-markup-pct` in the new template which is set to the default value `{{ form.default_markup_pct.value|default:'26.00' }}`.

### Step 10: Add `default_markup_pct` change listener to cascade to all locations

When the global `default_markup_pct` field changes, update all per-location markup inputs and recalculate:

```js
// When global markup changes, cascade to all locations
const globalMarkupInput = document.querySelector('[name="default_markup_pct"]');
if (globalMarkupInput) {
    globalMarkupInput.addEventListener('input', function() {
        const val = this.value;
        document.querySelectorAll('.loc-markup-pct').forEach(function(locInput) {
            locInput.value = val;
        });
        document.querySelectorAll('.location-form:not([style*="display: none"])').forEach(function(loc) {
            updateClientPricingTable(loc);
        });
    });
}
```

### Step 11: Verify form submission still saves correct data

The `unit_cost` and `quantity` hidden inputs get their `name` attributes set in `addItemRow`. Confirm that in `addItemRow`, the name-setting lines still reference `.item-unit-cost` and `.item-quantity`:

```js
row.querySelector('.item-unit-cost').name = `${prefix}-unit_cost`;
row.querySelector('.item-quantity').name = `${prefix}-quantity`;
row.querySelector('.item-vendor-unit-cost').name = `${prefix}-vendor_unit_cost`;
row.querySelector('.item-vendor-quantity').name = `${prefix}-vendor_quantity`;
```

These lines remain unchanged. The sync function populates the values before submit.

### Step 12: Run system check + visual smoke test

```bash
cd /Users/apple/Documents/DataScienceProjects/ERP
source venv/bin/activate
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

Then open the quotation create page in browser and verify:
1. Quotation Details shows only Validity Period + GST Rate (no POC, no Status)
2. Operational Scope has 2-row layout (2+3)
3. Products section says "Add SKU"
4. Commercial Settings shows pill toggle (Vendor Rate | Market Rate), not a dropdown
5. Location section shows "Vendor Costs" table (orange) + "Client Pricing" table (blue)
6. Typing a cost rate + qty in the orange table immediately updates the blue client table
7. Changing markup % updates client table live
8. Changing global default markup % cascades to all location markup inputs

---

## Summary of what changes where

| Change | File | Nature |
|---|---|---|
| Remove POC/status from form fields | `forms_quotation.py` | Remove 3 items from `Meta.fields` + widgets |
| Auto-set POC from user | `views_quotation.py` | 2 lines after `created_by = request.user` |
| Remove POC/Status from template | `quotation_create.html:105-159` | Rewrite Quotation Details section |
| Compact Operational Scope grid | `quotation_create.html:171-217` | Replace 1 grid with 2 grids |
| Rename Add Product → Add SKU | `quotation_create.html:224` | Text change + error banner |
| SKU duplicate validation | `quotation_create.html` JS | Add to submit handler |
| Commercial type pill toggle | `quotation_create.html:264-291` | Replace select with buttons + hidden input |
| Pill toggle JS | `quotation_create.html` JS | ~25 lines new function |
| Item template redesign | `quotation_create.html` | Rewrite `<template id="item-template">` |
| Location items section redesign | `quotation_create.html` | Rewrite per-location items HTML |
| Client pricing table JS | `quotation_create.html` JS | New `updateClientPricingTable()` function |
| Sync hidden fields on submit | `quotation_create.html` JS | New `syncClientFieldsBeforeSubmit()` |
| Update input event listeners | `quotation_create.html` JS | Swap old listeners for new |
| Fix `updateMarginSummary` | `quotation_create.html` JS | Read from cost+markup instead of unit_cost |
| Global markup cascade | `quotation_create.html` JS | Add listener on `default_markup_pct` |
