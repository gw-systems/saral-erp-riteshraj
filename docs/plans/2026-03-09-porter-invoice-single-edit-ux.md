# Porter Invoice Single Edit UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix CRN pre-fill, add date picker with DD MMM YYYY format, autofill pickup/drop dates in DD/MM/YYYY, and ensure download filename uses correct CRN.

**Architecture:** All changes are frontend (Alpine.js template) except one backend line — the filename fallback in `views_porter_invoice.py`. No new models, no new URLs, no migrations.

**Tech Stack:** Django templates, Alpine.js (x-data), `<input type="date">` native browser picker.

---

### Task 1: Fix CRN field — blank on load, placeholder shows original

**Files:**
- Modify: `templates/operations/porter_invoice_single.html:251` (JS uploadFile)
- Modify: `templates/operations/porter_invoice_single.html:54` (CRN input)

**Step 1: Remove CRN pre-fill in uploadFile JS**

In `uploadFile()`, find this line (~line 251):
```js
this.fields.crn = data.crn;
```
Remove it. `fields.crn` stays `''` (blank) after upload.

**Step 2: Update CRN input placeholder to show original CRN dynamically**

Find the CRN input (~line 54):
```html
<input type="text" x-model="fields.crn" :placeholder="crn"
```
This already uses `:placeholder="crn"` which is the extracted CRN — this is correct. No change needed here.

**Step 3: Manual verify**
- Upload a PDF → CRN field should be blank, placeholder shows extracted CRN
- Leave blank → submit → filename should use original CRN
- Type new CRN → submit → filename uses new CRN

---

### Task 2: Fix backend filename fallback to original CRN

**Files:**
- Modify: `operations/views_porter_invoice.py:493`

**Step 1: Update filename line**

Find in `porter_invoice_edit_api` (~line 493):
```python
output_filename = f"invoice_{crn}.pdf" if crn else file_record.original_filename
```

Replace with:
```python
effective_crn = crn if crn else file_record.crn
output_filename = f"invoice_{effective_crn}.pdf"
```

This ensures:
- User typed new CRN → `invoice_{new_crn}.pdf`
- User left blank → `invoice_{original_crn}.pdf` (from DB record, not original filename)

**Step 2: Manual verify**
- Submit with blank CRN → downloaded file named `invoice_{extracted_crn}.pdf`
- Submit with new CRN → downloaded file named `invoice_{new_crn}.pdf`

---

### Task 3: Invoice date — date picker with DD MMM YYYY format

**Files:**
- Modify: `templates/operations/porter_invoice_single.html` (date input + JS)

**Step 1: Replace invoice date input with date picker**

Find (~line 58-62):
```html
<input type="text" x-model="fields.date" placeholder="e.g. 15/01/2026"
       @change="if (!fields.pickup_date) fields.pickup_date = fields.date; if (!fields.drop_date) fields.drop_date = fields.date;"
       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-blue-500 focus:border-blue-500">
```

Replace with:
```html
<input type="date" x-ref="invoiceDatePicker"
       @change="onInvoiceDateChange($event.target.value)"
       class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-blue-500 focus:border-blue-500">
```

Note: We do NOT use `x-model` here because we store a formatted string in `fields.date`, not the raw YYYY-MM-DD picker value.

**Step 2: Add `onInvoiceDateChange` method to Alpine.js component**

In the `singleEditor()` return object, add the method after `applyEdits()`:

```js
onInvoiceDateChange(rawDate) {
    // rawDate is 'YYYY-MM-DD' from the date picker
    if (!rawDate) return;
    const [year, month, day] = rawDate.split('-');
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const monthName = months[parseInt(month, 10) - 1];

    // Invoice date on PDF: "27 Oct 2026"
    this.fields.date = `${parseInt(day, 10)} ${monthName} ${year}`;

    // Autofill pickup/drop dates: "27/10/2026"
    const ddmmyyyy = `${day}/${month}/${year}`;
    if (!this.fields.pickup_date) this.fields.pickup_date = ddmmyyyy;
    if (!this.fields.drop_date) this.fields.drop_date = ddmmyyyy;
},
```

**Step 3: Manual verify**
- Pick date 27 Oct 2026 → `fields.date` should be `"27 Oct 2026"`
- Pickup date should auto-fill as `27/10/2026`
- Drop date should auto-fill as `27/10/2026`
- If pickup_date already has a value, it should NOT be overwritten
- Submitted PDF should show `27 Oct 2026` on the invoice

---

### Task 4: Also reset date picker on resetUpload

**Files:**
- Modify: `templates/operations/porter_invoice_single.html` (resetUpload JS)

**Step 1: Clear the native date picker input on reset**

In `resetUpload()`, after resetting `this.fields`, add:
```js
this.$nextTick(() => {
    if (this.$refs.invoiceDatePicker) {
        this.$refs.invoiceDatePicker.value = '';
    }
});
```

This clears the browser's date picker UI when the user clicks "Upload Different File" or "Edit Another Invoice".

**Step 2: Manual verify**
- Complete an edit → click "Edit Another Invoice" → date picker should be blank again

---

## Full Changeset Summary

| File | Changes |
|---|---|
| `templates/operations/porter_invoice_single.html` | Remove CRN pre-fill, date input → picker, add `onInvoiceDateChange()`, reset picker on resetUpload |
| `operations/views_porter_invoice.py` | Line ~493: filename uses `file_record.crn` as fallback |
