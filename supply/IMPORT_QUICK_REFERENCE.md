# Warehouse Import - Quick Reference

## Commands

### Test Import (Dry Run)
```bash
# Activate environment
source venv/bin/activate

# Test detailed dataset (21 columns)
python manage.py import_warehouses path/to/file.csv --dataset-type=detailed --dry-run

# Test basic dataset (8 columns)
python manage.py import_warehouses path/to/file.csv --dataset-type=basic --dry-run
```

### Actual Import
```bash
# Import detailed dataset
python manage.py import_warehouses path/to/file.csv --dataset-type=detailed

# Import basic dataset
python manage.py import_warehouses path/to/file.csv --dataset-type=basic
```

## Dataset Types

### Basic Dataset (8 columns)
```
Vendor Name, Agreement Start Date, Agreement End Date, State, City, Location, Warehouse Address, SLA Status
```

**Required:** Vendor Name, State, City, Location

### Detailed Dataset (21 columns)
```
Vendor Partner, Warehouse Grade, Type of Business, State, City, Area,
Type of Property, Total Sq Ft, Available, Type, 3PL rates,
Handling Rates /MT, Handling Rates /20 KG, Remarks, Sales Person,
Number, Location POC, Address, Google Location, SLA, Photos
```

**Required:** Vendor Partner, State, City, Area

## Valid Values

### Warehouse Grade
- `Grade-A`, `Grade-B`, `Grade-C`
- Case insensitive

### Business Type
- `B2B`, `B2C`, `Both`
- Case insensitive

### Property Type
- `In Shed`, `Open`, `Covered`, `Temperature Controlled`
- Case insensitive, handles `In-Shed`, `in shed`, etc.

### SLA Status
- `Signed`, `Not Signed`, `Not Signed Yet`, `Under Negotiation`, `Expired`
- Case insensitive
- Default: `Not Signed`

### Storage Type
- `Sq Ft`, `Pallet`, `Unit`, `Order`
- Case insensitive
- Default: `Sq Ft`

## Rate Formats

The import handles various rate formats:
- `36/-` → `36.00`
- `36` → `36.00`
- `5.50` → `5.50`

## Date Formats

Supported date formats:
- `2024-01-15` (YYYY-MM-DD)
- `15-01-2024` (DD-MM-YYYY)
- `15/01/2024` (DD/MM/YYYY)
- `15-Jan-2024` (DD-Mon-YYYY)

## Sample Files

Sample CSV files are available in the `supply/` directory:
- `sample_warehouse_import_basic.csv` - Basic format example
- `sample_warehouse_import_detailed.csv` - Detailed format example

## Common Workflows

### 1. First Time Import
```bash
# 1. Test with dry run
python manage.py import_warehouses data.csv --dataset-type=detailed --dry-run

# 2. Review errors in output

# 3. Fix data in CSV

# 4. Run actual import
python manage.py import_warehouses data.csv --dataset-type=detailed
```

### 2. Update Existing Data
```bash
# Same command - existing warehouses will be updated based on vendor + location
python manage.py import_warehouses updated_data.csv --dataset-type=detailed
```

### 3. Import Multiple Files
```bash
# Import basic agreement data
python manage.py import_warehouses agreements.csv --dataset-type=basic

# Then import detailed warehouse profiles
python manage.py import_warehouses warehouse_details.csv --dataset-type=detailed
```

## Error Handling

| Exit Behavior | Meaning |
|--------------|---------|
| ✅ Row X: Created... | Successfully created new warehouse |
| ✅ Row X: Updated... | Successfully updated existing warehouse |
| ⏭️  Row X: Skipped... | Row skipped due to missing optional data |
| ❌ Row X: Error... | Row failed validation or import |

## Tips

1. **Always test first** with `--dry-run` flag
2. **Check vendor names** are consistent (same spelling)
3. **Ensure UTF-8 encoding** for special characters
4. **Remove empty rows** from CSV before import
5. **Review import summary** for errors
6. **Keep backup** of CSV file before making changes

## Getting Help

```bash
# Show command help
python manage.py import_warehouses --help

# Show all available commands
python manage.py help
```

---

**Files:**
- Command: `supply/management/commands/import_warehouses.py`
- Full Guide: `supply/WAREHOUSE_IMPORT_GUIDE.md`
- Samples: `supply/sample_warehouse_import_*.csv`
