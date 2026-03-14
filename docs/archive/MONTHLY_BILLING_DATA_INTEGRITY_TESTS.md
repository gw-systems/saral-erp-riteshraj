# Monthly Billing Form - Data Integrity Test Scenarios

**Date Created**: February 5, 2026
**Priority**: CRITICAL - Test before deploying to production
**Related Files**:
- `/Users/apple/Documents/DataScienceProjects/ERP/operations/views_monthly_billing.py`
- `/Users/apple/Documents/DataScienceProjects/ERP/templates/operations/monthly_billing_form.html`

---

## 🎯 PURPOSE

Validate that the monthly billing form NEVER loses data when:
1. User edits billing without touching certain tabs
2. User edits very quickly after page load
3. Form receives empty string values from frontend
4. User accidentally clears populated entries

---

## ✅ FIXES IMPLEMENTED

### Fix #1: Safe Backend POST Handler
**Location**: `operations/views_monthly_billing.py` lines 154-220
**What Changed**: Added `safe_decimal_update()`, `safe_int_update()`, `safe_fk_update()`, `safe_string_update()` helper functions
**Impact**: Empty strings NO LONGER overwrite existing database values with zero

### Fix #2: Race Condition Protection
**Location**: `monthly_billing_form.html` lines 2255-2635
**What Changed**:
- Added `window.billingDataPopulated` flag
- Increased population delay from 200ms to 500ms
- Block aggregation until flag is `true`
**Impact**: User cannot trigger aggregation before data is fully loaded

### Fix #3: Validation Warnings
**Location**: `monthly_billing_form.html` lines 1922-1940, 2008-2026
**What Changed**: Added console warnings when data drops from non-zero to zero
**Impact**: Developers can see warnings in browser console if data loss occurs

---

## 🧪 TEST SCENARIOS

### **Test 1: Edit Without Touching Tabs**
**Risk Level**: 🔴 CRITICAL
**Tests**: Fix #1 (Safe Backend Handler)

**Steps**:
1. Create a monthly billing with:
   - Storage: min_space=1000, client_billing=₹50,000, vendor_cost=₹35,000
   - Handling IN: quantity=500, client_billing=₹25,000, vendor_cost=₹18,000
   - Transport: client_amount=₹10,000, vendor_amount=₹8,000
2. Save the billing
3. Open edit form (wait 5 seconds for full page load)
4. Go to Transport tab ONLY
5. Change client_amount to ₹12,000
6. Click "Update Billing"
7. Refresh and check database

**Expected Result**:
- ✅ Storage: min_space=1000, client_billing=₹50,000, vendor_cost=₹35,000 (PRESERVED)
- ✅ Handling IN: quantity=500, client_billing=₹25,000, vendor_cost=₹18,000 (PRESERVED)
- ✅ Transport: client_amount=₹12,000 (UPDATED), vendor_amount=₹8,000 (PRESERVED)

**Failure Indicators**:
- ❌ Storage or Handling IN values become 0
- ❌ Any data that wasn't edited changes
- ❌ Django error messages

---

### **Test 2: Rapid Edit Before Population Completes**
**Risk Level**: 🟠 HIGH
**Tests**: Fix #2 (Race Condition Protection)

**Steps**:
1. Create a monthly billing with data in all sections
2. Open edit form
3. **IMMEDIATELY** (within 1 second) start typing in Storage min_space field
4. Type "2000" quickly
5. Wait 3 seconds
6. Check browser console
7. Click "Update Billing"
8. Check database

**Expected Result**:
- ✅ Console shows: "⏸️ Skipping aggregation - data population not yet complete"
- ✅ After 500ms, console shows: "✅ Billing data population flag set"
- ✅ Storage min_space saved as 2000
- ✅ All other sections preserved from database

**Failure Indicators**:
- ❌ Console error: "Cannot read property 'value' of null"
- ❌ Data from untouched tabs becomes 0
- ❌ Aggregation runs before population completes

---

### **Test 3: Empty String POST Data**
**Risk Level**: 🔴 CRITICAL
**Tests**: Fix #1 (Safe Backend Handler)

**Steps**:
1. Create billing with Storage client_billing=₹50,000
2. Open browser developer tools → Network tab
3. Open edit form
4. Click "Update Billing" (don't change anything)
5. In Network tab, find the POST request
6. Check POST data for: `storage_min_space`, `client_storage_billing`
7. Check database values

**Expected Result**:
- ✅ If POST contains `storage_min_space=''` (empty string), database value PRESERVED
- ✅ If POST contains `client_storage_billing=''`, database value PRESERVED
- ✅ No values changed to 0 unintentionally

**Failure Indicators**:
- ❌ Database shows storage_min_space=0 after POST with empty string
- ❌ Any decimal field becomes 0 when it should be preserved

---

### **Test 4: Delete Populated Entry (Validation Warning)**
**Risk Level**: 🟡 MEDIUM
**Tests**: Fix #3 (Validation Warnings)

**Steps**:
1. Create billing with Storage client_billing=₹50,000
2. Open edit form (wait for population)
3. Open browser console
4. Click "Remove" button on the storage entry
5. Check console immediately
6. Click "Update Billing"
7. Check console again
8. Check database

**Expected Result**:
- ✅ Console shows: "⚠️ ALERT: Storage client billing dropped from ₹50000 to ₹0!"
- ✅ Database IS UPDATED to 0 (user action was intentional)
- ✅ Warning helps user realize they deleted data

**Failure Indicators**:
- ❌ No warning in console
- ❌ Data silently becomes 0 without user being aware

---

### **Test 5: Edit Multiple Sections Simultaneously**
**Risk Level**: 🟢 LOW
**Tests**: All fixes working together

**Steps**:
1. Create billing with all sections filled
2. Open edit form
3. Edit Storage: Change min_space to 2000
4. Switch to Handling IN tab: Change quantity to 600
5. Switch to Transport tab: Change amount to ₹15,000
6. Click "Update Billing"
7. Check database

**Expected Result**:
- ✅ Storage min_space=2000 (updated)
- ✅ Handling IN quantity=600 (updated)
- ✅ Transport amount=₹15,000 (updated)
- ✅ All other fields in these sections preserved
- ✅ Sections not touched (VAS, Infrastructure) preserved

**Failure Indicators**:
- ❌ Any untouched field becomes 0
- ❌ Data from hidden fields not saved

---

### **Test 6: Save Without Any Changes**
**Risk Level**: 🔴 CRITICAL
**Tests**: Fix #1 (Safe Backend Handler)

**Steps**:
1. Create billing with complete data in all sections
2. Note all values (Storage, Handling IN, Handling OUT, Transport, VAS, Infrastructure)
3. Open edit form
4. Wait 5 seconds (do not touch anything)
5. Click "Update Billing"
6. Check database

**Expected Result**:
- ✅ ALL fields remain EXACTLY as they were
- ✅ No data changed
- ✅ No fields set to 0

**Failure Indicators**:
- ❌ ANY field changes value
- ❌ ANY field becomes 0
- ❌ updated_at timestamp changes but data doesn't (minor)

---

### **Test 7: Edit With One Section Having Zero Values**
**Risk Level**: 🟢 LOW
**Tests**: Edge case handling

**Steps**:
1. Create billing with:
   - Storage: client_billing=₹50,000
   - Handling IN: 0 (intentionally empty)
   - Transport: ₹10,000
2. Open edit form
3. Change Transport to ₹12,000
4. Click "Update Billing"
5. Check database

**Expected Result**:
- ✅ Storage preserved (₹50,000)
- ✅ Handling IN remains 0 (was 0, stays 0)
- ✅ Transport updated (₹12,000)
- ✅ No console warnings (Handling IN was already 0)

**Failure Indicators**:
- ❌ Storage becomes 0
- ❌ False warnings about Handling IN

---

### **Test 8: Create New Billing (Not Edit Mode)**
**Risk Level**: 🟢 LOW
**Tests**: Create mode still works correctly

**Steps**:
1. Navigate to billing create page
2. Fill all sections:
   - Storage: min_space=1000, rate=50
   - Handling IN: quantity=500, rate=50
   - Transport: amount=10000
3. Click "Create Billing"
4. Check database

**Expected Result**:
- ✅ New billing record created
- ✅ All entered values saved correctly
- ✅ No fields are 0 that should have values
- ✅ Aggregation worked correctly

**Failure Indicators**:
- ❌ Cannot create billing
- ❌ Some fields are 0 unexpectedly
- ❌ JavaScript errors in console

---

## 📊 TEST CHECKLIST

Use this checklist when running tests:

```
□ Test 1: Edit Without Touching Tabs - PASSED / FAILED
□ Test 2: Rapid Edit Before Population - PASSED / FAILED
□ Test 3: Empty String POST Data - PASSED / FAILED
□ Test 4: Delete Populated Entry - PASSED / FAILED
□ Test 5: Edit Multiple Sections - PASSED / FAILED
□ Test 6: Save Without Changes - PASSED / FAILED
□ Test 7: Edit With Zero Values - PASSED / FAILED
□ Test 8: Create New Billing - PASSED / FAILED

OVERALL RESULT: ______ / 8 tests passed
```

---

## 🔍 DEBUGGING TIPS

### If Test Fails:

1. **Check Browser Console**:
   - Open DevTools (F12)
   - Go to Console tab
   - Look for warnings starting with "⚠️ ALERT:"
   - Look for errors (red text)

2. **Check Network Tab**:
   - Find the POST request to `/operations/billing/.../edit/`
   - Click on it
   - Go to "Payload" or "Form Data"
   - Check what values were actually sent

3. **Check Database Directly**:
   ```bash
   python manage.py shell
   from operations.models import MonthlyBilling
   billing = MonthlyBilling.objects.get(id=YOUR_ID)
   print(f"Storage min: {billing.storage_min_space}")
   print(f"Client billing: {billing.client_storage_billing}")
   print(f"Vendor cost: {billing.vendor_storage_cost}")
   ```

4. **Check Backend Logs**:
   - Look in terminal where Django server is running
   - Safe update functions print warnings if they skip updates
   - Example: "⚠️ Warning: Invalid decimal value for storage_min_space: '' - keeping existing value"

---

## 🚨 CRITICAL SUCCESS CRITERIA

The system is **SAFE FOR PRODUCTION** only if:

1. ✅ **Test 1 PASSES** - Edit without touching tabs preserves all data
2. ✅ **Test 3 PASSES** - Empty strings don't overwrite with zeros
3. ✅ **Test 6 PASSES** - Save without changes preserves everything

If ANY of these fail, **DO NOT DEPLOY TO PRODUCTION**

---

## 📝 ADDITIONAL VALIDATION CHECKS

### Check 1: Verify Safe Update Functions Are Used
```bash
grep -n "Decimal(request.POST.get" operations/views_monthly_billing.py | grep "billing_edit"
```
**Expected**: Should find NO instances (all should use safe_decimal_update)

### Check 2: Verify Population Flag Exists
```bash
grep -n "window.billingDataPopulated" templates/operations/monthly_billing_form.html
```
**Expected**: Should find 3+ instances (declaration, setting, checking)

### Check 3: Verify Delay Increased
```bash
grep -n "setTimeout.*500" templates/operations/monthly_billing_form.html
```
**Expected**: Should find the 500ms delay for population

---

## 🎬 VIDEO RECORDING RECOMMENDATION

For critical tests (1, 3, 6), consider:
1. Recording screen during test
2. Keeping browser console visible
3. Showing before/after database values
4. Documenting exact steps taken

This helps debug issues if they occur.

---

## ✉️ REPORTING ISSUES

If any test fails, report with:
1. Test number and name
2. Exact steps taken
3. Screenshot of browser console
4. Screenshot of POST data (Network tab)
5. Database values before and after
6. Django version and browser used

---

**Last Updated**: February 5, 2026
**Version**: 1.0
**Reviewed By**: Claude Code (Sonnet 4.5)
