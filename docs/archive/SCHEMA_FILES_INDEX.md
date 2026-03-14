# Database Schema Documentation - Files Index

Generated: 2026-01-27

## Overview
Complete database schema extraction from `db_schema_local.json` (19,641 lines).

**Database Statistics:**
- Total Tables: 120 (excluding Django built-in tables)
- Total Columns: 1,312
- Total Foreign Keys: 211

---

## Generated Files

### 1. SCHEMA_AUDIT_SUMMARY.md
**Purpose:** Executive summary and audit reference guide
**Format:** Markdown
**Contents:**
- Table overview organized by module
- Critical foreign key relationships with diagrams
- Key columns by major tables
- Nullable vs NOT NULL analysis
- Master data code references
- Audit checklist
- Quick reference guide

**Use this for:** Understanding the overall schema architecture and audit planning

---

### 2. schema_audit_reference.txt
**Purpose:** Complete table-by-table schema reference
**Format:** Plain text (3,327+ lines)
**Contents:**
- All 120 tables in alphabetical order
- Complete column definitions with data types
- Nullable status for each column
- Primary keys
- Foreign key relationships with ON DELETE/UPDATE actions

**Use this for:** Looking up specific table structures and column details

---

### 3. schema_quick_lookup.txt
**Purpose:** Quick index organized by module/app
**Format:** Plain text
**Contents:**
- Tables grouped by prefix (bigin_, operations_, master_, etc.)
- Column count and FK count for each table
- Easy scanning format

**Use this for:** Finding which tables belong to which module

---

### 4. schema_fk_relationships.txt
**Purpose:** Complete foreign key relationship map
**Format:** Plain text
**Contents:**
- All 211 FK relationships listed by source table
- Reverse lookup showing what references each table
- ON DELETE/UPDATE actions
- Visual relationship groupings

**Use this for:** Understanding data dependencies and cascading effects

---

### 5. schema_map_complete.txt
**Purpose:** Detailed full schema with all metadata
**Format:** Plain text (3,328 lines)
**Contents:**
- Complete schema with default values
- All constraints and indexes
- Most comprehensive format

**Use this for:** Deep technical reference

---

### 6. schema_clean_export.json
**Purpose:** Clean JSON export for programmatic access
**Format:** JSON (335KB)
**Contents:**
- All tables with columns, primary keys, and foreign keys
- Clean, structured format
- Easy to parse with scripts

**Use this for:** Building tools, scripts, or automated checks

---

### 7. schema_stats.json
**Purpose:** Statistical summary
**Format:** JSON
**Contents:**
```json
{
  "total_tables": 120,
  "total_columns": 1312,
  "total_foreign_keys": 211,
  "tables_by_prefix": {
    "master": 44,
    "operations": 22,
    "tallysync": 14,
    "warehouse": 5,
    "client": 4,
    "vendor": 4,
    ...
  }
}
```

**Use this for:** Quick stats and module sizing

---

## Tables by Module

### Master Data (44 tables)
Reference/dropdown tables with standard structure (code, label, description, is_active, display_order)

### Operations (22 tables)
Core operational tables including:
- Project cards and rate tables
- Daily space utilization
- Dispute management
- Escalation tracking
- Agreement renewal tracking
- Ad-hoc billing

### Tally Integration (14 tables)
- Companies, cost centres, ledgers
- Vouchers and ledger entries
- Variance alerts
- Financial snapshots
- Project mappings

### Warehouse Management (5 tables)
- Profiles, capacities, commercials
- Contacts, photos

### Client & Vendor (8 tables)
- Client cards (4 tables)
- Vendor cards (4 tables)
- Contacts, GST, documents

### Project Management (4 tables)
- Project codes master
- Documents, change logs

### Dropdown Data (4 tables)
- App-specific reference tables

### Other Modules
- Bigin CRM (2 tables)
- Billing (1 table: monthly_billings with 92 columns)
- Disputes (2 tables)
- Users (2 tables)
- System/support (7 tables)
- Reference data (4 tables)

---

## Critical Tables for Audit

### Top Priority
1. **monthly_billings** (92 cols, 20 FKs) - Primary billing table
2. **operations_projectcard** (25 cols, 6 FKs) - Rate cards/contract terms
3. **project_codes** (26 cols, 2 FKs) - Project master
4. **operations_adhocbillingentry** (11 cols, 3 FKs) - Ad-hoc billing

### High Priority
5. **operations_dailyspaceutilization** (12 cols, 4 FKs) - Daily operations data
6. **operations_disputelog** (27 cols, 10 FKs) - Dispute tracking
7. **tallysync_voucher** (33 cols, 3 FKs) - Tally integration
8. **tallysync_variance_alert** (18 cols, 5 FKs) - Reconciliation alerts

### Supporting Tables
9. **client_cards**, **vendor_cards**, **vendor_warehouses** - Master data
10. All **master_*** tables - Reference data
11. **operations_storagerate**, **operations_handlingrate** - Rate definitions

---

## Key Relationships to Verify

### Billing Flow
```
project_codes
  -> operations_projectcard (rate card)
    -> monthly_billings (billing entry)
      -> tallysync_voucher (tally reconciliation)
        -> tallysync_variance_alert (if mismatch)
```

### Rate Card Versioning
```
operations_projectcard
  - version field
  - valid_from / valid_to dates
  - superseded_by_id (self-referencing FK)
  - is_active flag
```

### User Tracking
```
users.id is referenced by:
  - All *_by_id fields (created_by, updated_by, submitted_by, etc.)
  - Total references: ~100+ FK relationships
```

---

## Recommended Usage

**For Quick Lookups:**
1. Start with `schema_quick_lookup.txt` to find the module
2. Check `SCHEMA_AUDIT_SUMMARY.md` for business context
3. Use `schema_audit_reference.txt` for detailed column info

**For Relationship Analysis:**
1. Open `schema_fk_relationships.txt`
2. Search for table name to see all relationships
3. Use "BY REFERENCED TABLE" section to find dependencies

**For Programmatic Access:**
1. Load `schema_clean_export.json`
2. Parse with Python/JavaScript/etc.
3. Use `schema_stats.json` for metadata

**For Auditing:**
1. Read `SCHEMA_AUDIT_SUMMARY.md` first
2. Follow the audit checklist
3. Cross-reference with specific table files as needed

---

## File Locations

All files are located in:
```
/Users/apple/Documents/DataScienceProjects/ERP/
```

Generated from source:
```
/Users/apple/Documents/DataScienceProjects/ERP/db_schema_local.json
```

---

## Notes

- Django built-in tables (auth_*, django_*) are excluded from all exports
- All column data types include precision/scale where applicable
- Foreign key ON DELETE/UPDATE actions are documented
- Nullable status is clearly indicated for all columns
- Primary keys are identified for all tables

---

**End of Index**
