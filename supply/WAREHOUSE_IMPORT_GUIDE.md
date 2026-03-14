# Warehouse Data Import Guide

This guide explains how to import warehouse data from CSV files into the ERP system.

## Overview

The import command supports two dataset formats:

1. **Basic Dataset** (8 columns): Vendor agreements and location data
2. **Detailed Dataset** (21 columns): Complete warehouse profiles with capacity, rates, and contacts

## Prerequisites

### Master Data Codes

All required master data codes are already configured in your database:

✅ **Warehouse Grades**: `grade_a`, `grade_b`, `grade_c`
✅ **Business Types**: `b2b`, `b2c`, `both`
✅ **Property Types**: `in_shed`, `open`, `covered`, `temperature_controlled`
✅ **SLA Statuses**: `signed`, `not_signed`, `under_negotiation`, `expired`
✅ **Storage Units**: `sqft`, `pallet`, `unit`, `order`, `lumpsum`

## CSV Format Requirements

### Dataset 1: Basic (8 columns)

```csv
Vendor Name,Agreement Start Date,Agreement End Date,State,City,Location,Warehouse Address,SLA Status
Newcon,2024-01-01,2025-12-31,Maharashtra,Pune,Chakan,Gate no 117,Signed
NTL LOGISTICS,,,Tamil Nadu,Salem,Salem City,,Not Signed Yet
```

**Required columns:**
- Vendor Name ✓
- State ✓
- City ✓
- Location ✓

**Optional columns:**
- Agreement Start Date (format: YYYY-MM-DD or DD-MM-YYYY)
- Agreement End Date
- Warehouse Address
- SLA Status (values: Signed, Not Signed, Under Negotiation, Expired)

### Dataset 2: Detailed (21 columns)

```csv
Vendor Partner,Warehouse Grade,Type of Business,State,City,Area,Type of Property,Total Sq Ft,Available,Type,3PL rates,Handling Rates /MT,Handling Rates /20 KG,Remarks,Sales Person,Number,Location POC,Address,Google Location,SLA,Photos
Newcon,Grade-B,B2B,Maharashtra,Pune,Chakan,In Shed,10000,5000,Sq Ft,36/-,,5/-,,Madhukar,755 934 1414,Madhukar only,Wh no 2 Gate no 117,https://maps.app.goo.gl/xyz,Signed,https://drive.google.com/...
```

**Required columns:**
- Vendor Partner ✓
- State ✓
- City ✓
- Area ✓

**Optional columns:** (all other columns)

## Data Normalization

The import tool automatically handles various formats:

| CSV Value | Normalized Code |
|-----------|----------------|
| `Grade-B`, `grade-b` | `grade_b` |
| `B2B`, `b2b` | `b2b` |
| `In Shed`, `in-shed` | `in_shed` |
| `Signed` | `signed` |
| `Not Signed Yet` | `not_signed` |
| `Sq Ft`, `sqft` | `sqft` |
| `36/-`, `36` | `36.00` |

## Usage

### 1. Prepare Your CSV File

Ensure your CSV file:
- Has UTF-8 encoding
- Has column headers matching the formats above
- Contains at least the required columns

### 2. Test Import (Dry Run)

Always test first to validate your data:

```bash
source venv/bin/activate
python manage.py import_warehouses path/to/your/file.csv --dataset-type=detailed --dry-run
```

This will validate all data without making any changes to the database.

### 3. Run Actual Import

Once validation passes, run the actual import:

**For Detailed Dataset (21 columns):**
```bash
python manage.py import_warehouses path/to/detailed_data.csv --dataset-type=detailed
```

**For Basic Dataset (8 columns):**
```bash
python manage.py import_warehouses path/to/basic_data.csv --dataset-type=basic
```

## Import Behavior

### Creating vs Updating

The import tool intelligently handles duplicates:

- **Key**: Vendor + State + City + Location/Area
- **If exists**: Updates existing warehouse record
- **If new**: Creates new warehouse with auto-generated warehouse_code

### Auto-Generated Fields

The following fields are automatically generated:

1. **vendor_code**: Auto-generated using hash of vendor name
2. **vendor_short_name**: Extracted from vendor legal name
3. **warehouse_code**: Format `STATE-CITY-LOCATION-001`

### Data Validation

The import performs these validations:

✓ Required fields present
✓ Master data codes valid
✓ Numeric values parseable
✓ Dates in valid format
✓ No duplicate warehouse entries

## Import Report

After import, you'll see a detailed report:

```
============================================================
📊 IMPORT SUMMARY
============================================================
Total rows processed: 150
✅ Successful: 142
⏭️  Skipped: 5
❌ Failed: 3

⚠️  ERRORS:
  • Row 45: Missing required location fields (State, City)
  • Row 67: Invalid SLA Status: xyz
  • Row 89: Missing Vendor Partner - skipping empty row
```

## Handling Errors

### Common Issues

| Error | Solution |
|-------|----------|
| "Missing required location fields" | Ensure State and City are filled |
| "Missing Vendor Partner" | Fill vendor name or remove empty row |
| "Invalid SLA Status" | Use: Signed, Not Signed, Under Negotiation, Expired |
| "Invalid Warehouse Grade" | Use: Grade-A, Grade-B, or Grade-C |

### Skipped Rows

Rows are skipped (not imported) when:
- Missing vendor name (empty row)
- Missing location/area (incomplete data)

This allows you to have incomplete data in your sheet without causing errors.

## Tips for Clean Import

### 1. Data Preparation

- Remove completely empty rows
- Ensure vendor names are consistent (same spelling)
- Use consistent date formats (prefer YYYY-MM-DD)
- Remove special characters from phone numbers

### 2. Handling Photos/Links

For Google Drive photo links:
- Keep the full URL in the Photos column
- Multiple URLs can be comma-separated
- Links are stored but not automatically downloaded

### 3. Handling Multiple Contacts

If a warehouse has multiple contacts:
- Import the primary contact first
- Add additional contacts manually via admin panel

### 4. Batch Processing

For large datasets:
- Split into smaller CSV files (500-1000 rows each)
- Import one file at a time
- Review import report after each batch

## After Import

### Verify Data

1. Check warehouse list in admin panel
2. Verify warehouse_codes generated correctly
3. Check location data (state/city/area combinations)
4. Verify rates and capacity data

### Data Cleanup

After import, you may want to:
- Update missing vendor PAN/GSTIN details
- Add vendor contact information
- Upload warehouse photos manually
- Add additional contacts

## Examples

### Example 1: Import Detailed Warehouse Data

```bash
# Test first
python manage.py import_warehouses ~/Downloads/warehouse_data_detailed.csv --dataset-type=detailed --dry-run

# Import for real
python manage.py import_warehouses ~/Downloads/warehouse_data_detailed.csv --dataset-type=detailed
```

### Example 2: Import Basic Agreement Data

```bash
# Import vendor agreements
python manage.py import_warehouses ~/Downloads/vendor_agreements.csv --dataset-type=basic
```

### Example 3: Update Existing Warehouses

```bash
# Same command - existing warehouses will be updated
python manage.py import_warehouses ~/Downloads/updated_rates.csv --dataset-type=detailed
```

## Troubleshooting

### Import Fails with Database Error

```bash
# Check if tables exist
python manage.py migrate supply

# Check if master data exists
python manage.py shell -c "from dropdown_master_data.models import WarehouseGrade; print(WarehouseGrade.objects.count())"
```

### Encoding Issues

If you see garbled text:
```bash
# Convert CSV to UTF-8
iconv -f ISO-8859-1 -t UTF-8 input.csv > output_utf8.csv
```

### Permission Errors

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Check you're in the correct directory
pwd  # Should show: .../ERP
```

## Support

For issues or questions:
1. Check error messages in import report
2. Review this guide's "Common Issues" section
3. Use `--dry-run` flag to validate data
4. Contact system administrator with error details

---

**Last Updated**: 2026-01-29
**Command Location**: `supply/management/commands/import_warehouses.py`
