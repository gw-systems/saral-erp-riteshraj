# DATABASE SCHEMA AUDIT REFERENCE
## Complete Authoritative Schema Map

**Generated:** 2026-01-27
**Database:** PostgreSQL - erp
**Total Tables:** 120 (excluding Django built-in tables)
**Total Foreign Keys:** 211

---

## FILES GENERATED

1. **schema_audit_reference.txt** - Complete table-by-table reference with all columns, types, and FKs
2. **schema_quick_lookup.txt** - Quick index organized by module/app
3. **schema_fk_relationships.txt** - Complete foreign key relationship map
4. **schema_map_complete.txt** - Detailed full schema with all metadata

---

## TABLE OVERVIEW BY MODULE

### CORE TABLES (Most Critical for Audit)

#### PROJECT MANAGEMENT (4 tables)
- **project_codes** - Master project registry (26 cols, 2 FKs)
- **project_documents** - Project document attachments (8 cols, 2 FKs)
- **project_code_change_logs** - Audit trail for project code changes (8 cols, 1 FK)
- **project_name_change_logs** - Audit trail for project name changes (9 cols, 2 FKs)

#### OPERATIONS - PROJECT CARDS (1 table + 6 rate tables)
- **operations_projectcard** - Contract terms and rate cards (25 cols, 6 FKs)
  - operations_storagerate (12 cols, 3 FKs)
  - operations_storagerateslab (11 cols, 3 FKs)
  - operations_handlingrate (10 cols, 3 FKs)
  - operations_transportrate (9 cols, 1 FK)
  - operations_valueaddedservice (8 cols, 2 FKs)
  - operations_infrastructurecost (8 cols, 2 FKs)

#### BILLING (3 tables)
- **monthly_billings** - Monthly billing entries (92 cols, 20 FKs) ⚠️ LARGEST TABLE
- **billing_statements** - Legacy billing (59 cols, 2 FKs)
- **operations_adhocbillingentry** - Ad-hoc billing (11 cols, 3 FKs)
  - operations_adhocbillinglineitem (10 cols, 3 FKs)
  - operations_adhocbillingattachment (7 cols, 2 FKs)

#### DAILY OPERATIONS (3 tables)
- **operations_dailyspaceutilization** - Daily space tracking (12 cols, 4 FKs)
- **operations_dailymislog** - MIS reporting log (9 cols, 2 FKs)
- **operations_daily_update** - Legacy daily updates (10 cols, 1 FK)

#### CLIENT MANAGEMENT (4 tables)
- **client_cards** - Master client registry (13 cols, 0 FKs)
- **client_contacts** - Client contact persons (10 cols, 1 FK)
- **client_gst** - Client GST details (8 cols, 1 FK)
- **client_documents** - Client document uploads (6 cols, 2 FKs)

#### VENDOR/WAREHOUSE MANAGEMENT (9 tables)
- **vendor_cards** - Master vendor registry (12 cols, 0 FKs)
- **vendor_warehouses** - Warehouse master (14 cols, 2 FKs)
- **vendor_contacts** - Vendor contacts (10 cols, 1 FK)
- **vendor_warehouse_documents** - Warehouse docs (15 cols, 3 FKs)
- **warehouse_profiles** - Warehouse specifications (10 cols, 4 FKs)
- **warehouse_capacities** - Capacity details (15 cols, 2 FKs)
- **warehouse_commercials** - Commercial terms (15 cols, 3 FKs)
- **warehouse_contacts** - Warehouse contacts (10 cols, 1 FK)
- **warehouse_photos** - Warehouse images (7 cols, 2 FKs)

#### DISPUTE MANAGEMENT (3 tables)
- **operations_disputelog** - Dispute tracking (27 cols, 10 FKs)
- **dispute_activities** - Dispute activity log (8 cols, 3 FKs)
- **dispute_comments** - Dispute comments (7 cols, 2 FKs)

#### ESCALATION & RENEWAL TRACKING (4 tables)
- **operations_escalationtracker** - Price escalation tracking (23 cols, 4 FKs)
- **operations_escalationlog** - Escalation actions log (9 cols, 3 FKs)
- **operations_agreementrenewaltracker** - Agreement renewal tracking (21 cols, 4 FKs)
- **operations_agreementrenewallog** - Renewal actions log (9 cols, 3 FKs)

#### TALLY INTEGRATION (14 tables)
- **tallysync_company** - Tally companies (8 cols, 0 FKs)
- **tallysync_cost_centre** - Tally cost centres (14 cols, 2 FKs)
- **tallysync_ledger** - Tally ledgers (12 cols, 2 FKs)
- **tallysync_voucher** - Tally vouchers (33 cols, 3 FKs)
- **tallysync_voucher_ledger_entry** - Voucher line items (21 cols, 2 FKs)
- **tallysync_variance_alert** - ERP vs Tally variance alerts (18 cols, 5 FKs)
- **tallysync_project_mapping** - Project to cost centre mapping (8 cols, 3 FKs)
- Plus 7 more financial snapshot and reference tables

#### BIGIN CRM INTEGRATION (2 tables)
- **bigin_biginauthtoken** - Auth tokens (5 cols, 0 FKs)
- **bigin_biginrecord** - Synced CRM records (30 cols, 0 FKs)

#### MASTER DATA (44 tables)
All master_* tables are reference/dropdown tables with standard structure:
- code (primary key)
- label
- description
- is_active
- display_order
- updated_by_id (FK to users)
- updated_at

Key master tables:
- master_monthly_billing_statuses
- master_handling_base_types
- master_handling_units
- master_storage_units
- master_vehicle_types
- master_vas_service_types
- master_approval_actions
- master_dispute_statuses
- master_escalation_statuses
- Plus 35 more reference tables

#### DROPDOWN DATA (4 tables)
Similar structure to master tables but app-specific:
- dropdown_adhoc_billing_statuses
- dropdown_dispute_categories
- dropdown_renewal_action_types
- dropdown_renewal_statuses

#### USER MANAGEMENT (4 tables)
- **users** - User accounts (15 cols, 0 FKs)
- **users_groups** - User-group mapping (3 cols, 2 FKs)
- **users_user_permissions** - User permissions (3 cols, 2 FKs)
- **password_history** - Password change history (7 cols, 2 FKs)

#### SYSTEM TABLES (7 tables)
- **notifications** - In-app notifications (12 cols, 3 FKs)
- **operations_inappalert** - Alert system (10 cols, 1 FK)
- **operations_projectcardalert** - Project card alerts (11 cols, 3 FKs)
- **error_logs** - Error tracking (16 cols, 2 FKs)
- **tickets** - Support tickets (13 cols, 2 FKs)
- **ticket_comments** - Ticket comments (6 cols, 2 FKs)
- **system_settings** - System config (4 cols, 0 FKs)

#### REFERENCE DATA (4 tables)
- **locations** - Location master (11 cols, 0 FKs)
- **city_codes** - City codes (7 cols, 0 FKs)
- **gst_states** - GST state codes (8 cols, 0 FKs)
- **master_state_codes** - State codes (6 cols, 0 FKs)

#### AUDIT TABLES (2 tables)
- **operations_dailyentryauditlog** - Daily entry changes (8 cols, 2 FKs)
- **unused_project_ids** - Deleted project tracking (8 cols, 1 FK)

---

## CRITICAL FOREIGN KEY RELATIONSHIPS

### Primary Entity Relationships

```
users (15 cols)
  ├─> project_codes (26 cols)
  │     ├─> operations_projectcard (25 cols)
  │     │     ├─> operations_storagerate
  │     │     ├─> operations_storagerateslab
  │     │     ├─> operations_handlingrate
  │     │     ├─> operations_transportrate
  │     │     ├─> operations_valueaddedservice
  │     │     ├─> operations_infrastructurecost
  │     │     ├─> operations_escalationtracker
  │     │     └─> operations_agreementrenewaltracker
  │     ├─> monthly_billings (92 cols, 20 FKs)
  │     ├─> operations_adhocbillingentry (11 cols)
  │     ├─> operations_dailyspaceutilization (12 cols)
  │     ├─> operations_disputelog (27 cols, 10 FKs)
  │     ├─> operations_dailymislog (9 cols)
  │     └─> tallysync_cost_centre (14 cols)
  │
  ├─> client_cards (13 cols)
  │     ├─> client_contacts
  │     ├─> client_gst
  │     ├─> client_documents
  │     ├─> project_codes (FK: client_card_code)
  │     └─> operations_projectcard (FK: client_card_code)
  │
  └─> vendor_cards (12 cols)
        ├─> vendor_contacts
        ├─> vendor_warehouses (14 cols)
        │     ├─> vendor_warehouse_documents
        │     ├─> warehouse_contacts
        │     ├─> warehouse_photos
        │     ├─> warehouse_capacities
        │     ├─> warehouse_commercials
        │     ├─> warehouse_profiles
        │     ├─> project_codes (FK: vendor_warehouse_code)
        │     └─> operations_projectcard (FK: vendor_warehouse_code)
        └─> vendor_warehouse_documents
```

### Billing Flow

```
project_codes
  ├─> operations_projectcard (rate card)
  │     └─> monthly_billings (references project_card_used_id)
  │           └─> tallysync_voucher (erp_monthly_billing_id)
  │                 └─> tallysync_variance_alert (tally vs ERP comparison)
  │
  └─> operations_adhocbillingentry
        ├─> operations_adhocbillinglineitem
        ├─> operations_adhocbillingattachment
        └─> tallysync_voucher (erp_adhoc_billing_id)
              └─> tallysync_variance_alert
```

### Tally Integration Flow

```
tallysync_company
  ├─> tallysync_cost_centre
  │     ├─> tallysync_project_mapping (maps to project_codes)
  │     └─> tallysync_cost_allocation
  │
  ├─> tallysync_group
  │     └─> tallysync_ledger
  │           └─> tallysync_voucher_ledger_entry
  │
  ├─> tallysync_voucher (sales/purchase vouchers)
  │     ├─> tallysync_voucher_ledger_entry
  │     │     ├─> tallysync_cost_allocation
  │     │     └─> tallysync_bill_reference
  │     └─> tallysync_variance_alert
  │
  └─> tallysync_log (sync history)
```

---

## KEY COLUMNS BY TABLE

### monthly_billings (THE CORE BILLING TABLE)
- **id** (bigint, PK)
- **project_id** (varchar(20), FK -> project_codes)
- **project_card_used_id** (bigint, FK -> operations_projectcard)
- **service_month** (date) - The billing month
- **status** (varchar(50), FK -> master_monthly_billing_statuses)
- **created_by_id**, **submitted_by_id** (bigint, FK -> users)
- **controller_reviewed_by_id**, **finance_reviewed_by_id** (bigint, FK -> users)
- **controller_action**, **finance_action** (varchar(50), FK -> master_approval_actions)

**Storage fields:**
- storage_unit_type (FK -> master_storage_units)
- client_storage_sqft, vendor_storage_sqft (numeric)
- client_storage_rate, vendor_storage_rate (numeric)
- client_storage_amount, vendor_storage_amount (numeric)

**Handling IN fields:**
- handling_in_unit_type (FK -> master_handling_units)
- handling_in_base_type (FK -> master_handling_base_types)
- handling_in_channel (FK -> master_sales_channels)
- client_handling_in_qty, vendor_handling_in_qty (numeric)
- client_handling_in_rate, vendor_handling_in_rate (numeric)
- client_handling_in_amount, vendor_handling_in_amount (numeric)

**Handling OUT fields:**
- handling_out_unit_type, handling_out_base_type, handling_out_channel
- client_handling_out_qty, vendor_handling_out_qty (numeric)
- client_handling_out_rate, vendor_handling_out_rate (numeric)
- client_handling_out_amount, vendor_handling_out_amount (numeric)

**Transport fields:**
- client_transport_vehicle_type, vendor_transport_vehicle_type (FK -> master_vehicle_types)
- client_transport_charges, vendor_transport_charges (numeric)

**VAS fields:**
- vas_service_type (FK -> master_vas_service_types)
- vas_unit (FK -> master_vas_units)
- client_vas_charges, vendor_vas_charges (numeric)

**Infrastructure fields:**
- client_infrastructure_charges, vendor_infrastructure_charges (numeric)

**Totals:**
- client_total_amount, vendor_total_amount (numeric 15,2)
- margin_amount (numeric 15,2)
- margin_percentage (numeric 5,2)

**Document uploads:**
- client_invoice_upload, vendor_invoice_upload (varchar 100)
- mis_upload, pod_upload, other_supporting_docs (varchar 100)

### operations_projectcard (RATE CARD)
- **id** (bigint, PK)
- **project_id** (varchar(20), FK -> project_codes)
- **client_card_code** (varchar(20), FK -> client_cards)
- **vendor_warehouse_code** (varchar(30), FK -> vendor_warehouses)
- **version** (integer) - Version tracking
- **valid_from**, **valid_to** (date) - Validity period
- **is_active** (boolean)
- **superseded_by_id** (bigint, FK -> self) - Version chain
- **agreement_start_date**, **agreement_end_date** (date)
- **billing_start_date**, **operation_start_date** (date)
- **storage_payment_days**, **handling_payment_days** (integer)
- **escalation_terms** (varchar 20)
- **has_fixed_escalation** (boolean)
- **annual_escalation_percent** (numeric 5,2)
- **yearly_escalation_date** (date)
- **security_deposit** (numeric 12,2)
- **created_by_id**, **last_modified_by_id** (FK -> users)

### project_codes (PROJECT MASTER)
- **project_id** (varchar(20), PK)
- **project_name** (varchar 200)
- **client_card_code** (varchar 20, FK -> client_cards)
- **vendor_warehouse_code** (varchar 30, FK -> vendor_warehouses)
- **project_status** (varchar 50)
- **agreement_date**, **closure_date** (date)
- **is_active** (boolean)
- **location**, **city**, **state** (varchar)
- **project_manager**, **sales_manager** (varchar 100)
- **notice_period_duration** (varchar 50)
- **contract_area_sqft** (numeric 10,2)
- **operation_mode** (varchar 50)

### operations_adhocbillingentry
- **id** (bigint, PK)
- **project_id** (varchar 20, FK -> project_codes)
- **event_date** (date)
- **service_month** (date)
- **status** (varchar 50, FK -> dropdown_adhoc_billing_statuses)
- **total_client_amount**, **total_vendor_amount** (numeric 15,2)
- **billing_remarks** (text)
- **created_by_id** (bigint, FK -> users)

### operations_dailyspaceutilization
- **id** (bigint, PK)
- **project_id** (varchar 20, FK -> project_codes)
- **entry_date** (date)
- **space_utilized** (numeric 10,2)
- **unit** (varchar 50, FK -> master_storage_units)
- **inventory_value**, **gw_inventory** (numeric 15,2)
- **entered_by_id**, **last_modified_by_id** (FK -> users)

### operations_disputelog
- **dispute_id** (integer, PK)
- **project_id** (varchar 20, FK -> project_codes)
- **title** (varchar 200)
- **category** (varchar 50, FK -> dropdown_dispute_categories)
- **status** (varchar 50, FK -> master_dispute_statuses)
- **priority** (varchar 50, FK -> master_priorities)
- **severity** (varchar 50, FK -> master_severity_levels)
- **dispute_type** (varchar 30)
- **disputed_amount** (numeric 15,2)
- **dispute_date**, **resolution_date** (date)
- **raised_by_id**, **assigned_to_id**, **handled_by_id**, **resolved_by_id** (FK -> users)

---

## NULLABLE vs NOT NULL ANALYSIS

### Critical NOT NULL Constraints

**monthly_billings:**
- project_id, service_month, status (MUST have values)
- created_by_id, created_at, updated_at (audit trail)

**operations_projectcard:**
- project_id, version, valid_from, is_active, escalation_terms
- has_fixed_escalation (boolean)

**project_codes:**
- project_id, project_name, is_active

**operations_adhocbillingentry:**
- project_id, event_date, status
- total_client_amount, total_vendor_amount

**users:**
- email, username, is_active, date_joined

### Key NULLABLE Fields (Potential Data Issues)

**monthly_billings:**
- project_card_used_id (NULL) - May not reference a project card
- All client_* and vendor_* amount fields (NULL) - Sparse data
- controller_reviewed_by_id, finance_reviewed_by_id (NULL) - Not yet reviewed
- Document upload fields (NULL) - Documents not uploaded

**operations_projectcard:**
- agreement_start_date, agreement_end_date (NULL)
- billing_start_date, operation_start_date (NULL)
- storage_payment_days, handling_payment_days (NULL)
- annual_escalation_percent (NULL)

**project_codes:**
- agreement_date, closure_date (NULL)
- project_manager, sales_manager (NULL) - Assignment pending

---

## MASTER DATA CODE REFERENCES

All master_* and dropdown_* tables use **code** as the primary key (varchar 50).
These codes are referenced throughout the system.

### Critical Master Tables:
- **master_monthly_billing_statuses**: DRAFT, SUBMITTED, APPROVED, REJECTED, etc.
- **master_approval_actions**: APPROVE, REJECT, RETURN, etc.
- **master_storage_units**: SQFT, PALLET, CBM, etc.
- **master_handling_units**: KG, MT, CBM, PALLET, CASE, etc.
- **master_handling_base_types**: PER_KG, PER_MT, PER_CASE, LUMPSUM, etc.
- **master_vehicle_types**: 14_FT, 17_FT, 19_FT, 20_FT, 22_FT, 32_FT, etc.
- **master_vas_service_types**: LABELLING, PACKING, QC, LOADING, UNLOADING, etc.
- **master_dispute_statuses**: OPEN, IN_PROGRESS, RESOLVED, CLOSED, etc.

---

## AUDIT CHECKLIST

### Data Integrity Checks
1. Verify all FK constraints are valid (no orphaned records)
2. Check for NULL values in critical NOT NULL fields
3. Validate date ranges (valid_from <= valid_to)
4. Check for duplicate entries (project_id + service_month combinations)
5. Verify amount calculations (totals match sum of components)

### Business Logic Validation
1. monthly_billings must reference a valid project_card_used_id
2. Project cards must have valid_from dates and version numbers
3. Rate cards must be active within billing period
4. Escalation calculations must follow project card terms
5. Approval workflow must be followed (draft -> submitted -> approved)

### Reconciliation Points
1. monthly_billings vs tallysync_voucher (erp_monthly_billing_id)
2. operations_adhocbillingentry vs tallysync_voucher (erp_adhoc_billing_id)
3. tallysync_variance_alert for mismatches
4. operations_dailyspaceutilization vs monthly_billings storage data
5. project_codes vs tallysync_cost_centre mappings

---

## QUICK REFERENCE: Key FK Relationships

```
users.id <- ALL tables with *_by_id fields

project_codes.project_id <-
  - monthly_billings.project_id
  - operations_projectcard.project_id
  - operations_adhocbillingentry.project_id
  - operations_dailyspaceutilization.project_id
  - operations_disputelog.project_id
  - tallysync_cost_centre.erp_project_id

operations_projectcard.id <-
  - monthly_billings.project_card_used_id
  - operations_storagerate.project_card_id
  - operations_handlingrate.project_card_id
  - operations_transportrate.project_card_id
  - operations_valueaddedservice.project_card_id

monthly_billings.id <-
  - tallysync_voucher.erp_monthly_billing_id
  - tallysync_variance_alert.erp_monthly_billing_id

operations_adhocbillingentry.id <-
  - operations_adhocbillinglineitem.entry_id
  - operations_adhocbillingattachment.entry_id
  - tallysync_voucher.erp_adhoc_billing_id

client_cards.client_code <-
  - project_codes.client_card_code
  - operations_projectcard.client_card_code
  - client_contacts.client_code_id
  - client_gst.client_code_id

vendor_warehouses.warehouse_code <-
  - project_codes.vendor_warehouse_code
  - operations_projectcard.vendor_warehouse_code
  - warehouse_contacts.warehouse_code_id
  - vendor_warehouse_documents.warehouse_code_id
```

---

**END OF SCHEMA AUDIT SUMMARY**

For detailed column information, refer to:
- schema_audit_reference.txt
- schema_fk_relationships.txt
- schema_quick_lookup.txt
