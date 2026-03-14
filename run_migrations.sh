#!/bin/bash
#
# Production-safe migration script
# Ensures supply app tables are created before running regular migrations
#

set -e  # Exit on error

echo "🗃️ Starting database migration process..."
echo ""

# Step 1: Create supply tables if they don't exist
echo "Step 1: Checking and creating supply app tables..."
python manage.py create_supply_tables
echo ""

# Step 2: Run regular migrations
echo "Step 2: Running standard migrations..."
python manage.py migrate
echo ""

# Step 3: Create database cache table (idempotent - safe to run multiple times)
echo "Step 3: Creating database cache table..."
python manage.py createcachetable
echo ""

echo "✅ All migrations completed successfully"
