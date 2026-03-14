#!/usr/bin/env python3
"""
Database Schema Comparator
Compares schemas between local and production databases.
Only requires psycopg2 (no Django dependencies).

SETUP FOR PRODUCTION:
    In one terminal, start Cloud SQL proxy:
    cloud-sql-proxy saral-erp-479508:asia-south1:saral-erp-db --port=5433

    Then in another terminal, run this script:
    python .ci/schema_comparator.py --local --production

USAGE:
    python .ci/schema_comparator.py --local --production
    python .ci/schema_comparator.py --local --production --table operations_monthlybilling
    python .ci/schema_comparator.py --local --production --generate-sql
"""

import sys
import argparse
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict
import getpass


# Database configurations
DB_CONFIGS = {
    'local': {
        'host': 'localhost',
        'port': 5432,
        'database': 'erp',
        'user': 'admin',
        'password': 'admin'
    },
    'production': {
        'host': 'localhost',
        'port': 5433,  # Cloud SQL proxy port
        'database': 'erp',
        'user': 'admin',
        'password': None  # Will prompt
    }
}


def get_schema_info(conn, table_name=None):
    """
    Get comprehensive schema information from database.

    Returns dict with:
    - tables: {table_name: {columns: {...}, indexes: {...}, constraints: {...}}}
    """
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    schema_info = defaultdict(lambda: {
        'columns': {},
        'indexes': {},
        'constraints': {}
    })

    # Build table filter
    table_filter = ""
    if table_name:
        table_filter = f"AND table_name = '{table_name}'"

    # Get column information
    cursor.execute(f"""
        SELECT
            table_name,
            column_name,
            data_type,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
        {table_filter}
        ORDER BY table_name, ordinal_position
    """)

    for row in cursor.fetchall():
        table = row['table_name']
        col_name = row['column_name']

        col_info = {
            'type': row['data_type'],
            'nullable': row['is_nullable'] == 'YES',
            'default': row['column_default']
        }

        # Add length/precision info
        if row['character_maximum_length']:
            col_info['length'] = row['character_maximum_length']
        if row['numeric_precision']:
            col_info['precision'] = row['numeric_precision']
        if row['numeric_scale']:
            col_info['scale'] = row['numeric_scale']

        schema_info[table]['columns'][col_name] = col_info

    # Get constraints (PK, FK, UNIQUE)
    cursor.execute(f"""
        SELECT
            tc.table_name,
            tc.constraint_name,
            tc.constraint_type,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        LEFT JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.table_schema = 'public'
        {table_filter.replace('table_name', 'tc.table_name') if table_filter else ''}
        ORDER BY tc.table_name, tc.constraint_name
    """)

    for row in cursor.fetchall():
        table = row['table_name']
        const_name = row['constraint_name']

        const_info = {
            'type': row['constraint_type'],
            'column': row['column_name']
        }

        if row['foreign_table_name']:
            const_info['references'] = f"{row['foreign_table_name']}({row['foreign_column_name']})"

        schema_info[table]['constraints'][const_name] = const_info

    # Get indexes
    cursor.execute(f"""
        SELECT
            t.relname AS table_name,
            i.relname AS index_name,
            a.attname AS column_name,
            ix.indisunique AS is_unique,
            ix.indisprimary AS is_primary
        FROM pg_class t
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
        {table_filter.replace('table_name', 't.relname') if table_filter else ''}
        ORDER BY t.relname, i.relname
    """)

    for row in cursor.fetchall():
        table = row['table_name']
        idx_name = row['index_name']

        idx_info = {
            'column': row['column_name'],
            'unique': row['is_unique'],
            'primary': row['is_primary']
        }

        schema_info[table]['indexes'][idx_name] = idx_info

    cursor.close()
    return dict(schema_info)


def connect_to_db(config, db_name):
    """Connect to database with given configuration."""
    conn_config = config.copy()

    if conn_config['password'] is None:
        conn_config['password'] = getpass.getpass(f"Enter password for {db_name}: ")

    try:
        conn = psycopg2.connect(**conn_config)
        return conn
    except psycopg2.Error as e:
        print(f"❌ Connection failed to {db_name}: {e}")
        if 'production' in db_name.lower() and 'Connection refused' in str(e):
            print("💡 Make sure Cloud SQL proxy is running:")
            print("   cloud-sql-proxy saral-erp-479508:asia-south1:saral-erp-db --port=5433")
        return None


def compare_schemas(schema1, schema2, name1, name2):
    """
    Compare two schemas and return differences.

    Returns dict with:
    - tables_only_in_1: []
    - tables_only_in_2: []
    - table_differences: {table_name: {...}}
    """
    differences = {
        'tables_only_in_1': [],
        'tables_only_in_2': [],
        'table_differences': {}
    }

    tables1 = set(schema1.keys())
    tables2 = set(schema2.keys())

    differences['tables_only_in_1'] = sorted(tables1 - tables2)
    differences['tables_only_in_2'] = sorted(tables2 - tables1)

    common_tables = tables1 & tables2

    for table in sorted(common_tables):
        table_diff = compare_table(schema1[table], schema2[table])
        if table_diff:
            differences['table_differences'][table] = table_diff

    return differences


def compare_table(table1, table2):
    """Compare two table schemas."""
    diff = {}

    # Compare columns
    cols1 = set(table1['columns'].keys())
    cols2 = set(table2['columns'].keys())

    cols_only_1 = cols1 - cols2
    cols_only_2 = cols2 - cols1

    if cols_only_1:
        diff['columns_only_in_1'] = sorted(cols_only_1)
    if cols_only_2:
        diff['columns_only_in_2'] = sorted(cols_only_2)

    # Compare common columns
    common_cols = cols1 & cols2
    col_differences = {}

    for col in sorted(common_cols):
        col_diff = compare_column(table1['columns'][col], table2['columns'][col])
        if col_diff:
            col_differences[col] = col_diff

    if col_differences:
        diff['column_differences'] = col_differences

    # Compare constraints
    const1 = set(table1['constraints'].keys())
    const2 = set(table2['constraints'].keys())

    if const1 != const2:
        diff['constraints_only_in_1'] = sorted(const1 - const2)
        diff['constraints_only_in_2'] = sorted(const2 - const1)

    # Compare indexes
    idx1 = set(table1['indexes'].keys())
    idx2 = set(table2['indexes'].keys())

    if idx1 != idx2:
        diff['indexes_only_in_1'] = sorted(idx1 - idx2)
        diff['indexes_only_in_2'] = sorted(idx2 - idx1)

    return diff if diff else None


def compare_column(col1, col2):
    """Compare two column definitions."""
    diff = {}

    if col1['type'] != col2['type']:
        diff['type'] = {'1': col1['type'], '2': col2['type']}

    if col1['nullable'] != col2['nullable']:
        diff['nullable'] = {'1': col1['nullable'], '2': col2['nullable']}

    if col1.get('default') != col2.get('default'):
        diff['default'] = {'1': col1.get('default'), '2': col2.get('default')}

    if col1.get('length') != col2.get('length'):
        diff['length'] = {'1': col1.get('length'), '2': col2.get('length')}

    return diff if diff else None


def print_differences(differences, name1, name2):
    """Pretty print schema differences."""
    print(f"\n{'='*80}")
    print(f"Schema Comparison: {name1} vs {name2}")
    print(f"{'='*80}\n")

    has_diff = False

    if differences['tables_only_in_1']:
        has_diff = True
        print(f"📋 Tables only in {name1}:")
        for table in differences['tables_only_in_1']:
            print(f"  - {table}")
        print()

    if differences['tables_only_in_2']:
        has_diff = True
        print(f"📋 Tables only in {name2}:")
        for table in differences['tables_only_in_2']:
            print(f"  - {table}")
        print()

    if differences['table_differences']:
        has_diff = True
        print(f"⚠️  Tables with differences:\n")

        for table, table_diff in differences['table_differences'].items():
            print(f"  📊 {table}:")

            if 'columns_only_in_1' in table_diff:
                print(f"    Columns only in {name1}: {', '.join(table_diff['columns_only_in_1'])}")

            if 'columns_only_in_2' in table_diff:
                print(f"    Columns only in {name2}: {', '.join(table_diff['columns_only_in_2'])}")

            if 'column_differences' in table_diff:
                print(f"    Column differences:")
                for col, col_diff in table_diff['column_differences'].items():
                    print(f"      • {col}:")
                    for attr, vals in col_diff.items():
                        print(f"        - {attr}: {name1}={vals['1']} | {name2}={vals['2']}")

            if 'constraints_only_in_1' in table_diff:
                print(f"    Constraints only in {name1}: {', '.join(table_diff['constraints_only_in_1'])}")

            if 'constraints_only_in_2' in table_diff:
                print(f"    Constraints only in {name2}: {', '.join(table_diff['constraints_only_in_2'])}")

            if 'indexes_only_in_1' in table_diff:
                print(f"    Indexes only in {name1}: {', '.join(table_diff['indexes_only_in_1'])}")

            if 'indexes_only_in_2' in table_diff:
                print(f"    Indexes only in {name2}: {', '.join(table_diff['indexes_only_in_2'])}")

            print()

    if not has_diff:
        print("✅ No schema differences found!")

    print(f"{'='*80}\n")


def generate_sql_fixes(differences, name1, name2):
    """
    Generate SQL statements to sync schemas.
    Always generates SQL to make production match local.
    """
    print(f"\n{'='*80}")
    print(f"SQL Statements to Sync Production with Local")
    print(f"{'='*80}\n")

    sql_statements = []

    # Handle table differences
    for table, table_diff in differences.get('table_differences', {}).items():

        # Fix column differences
        if 'column_differences' in table_diff:
            for col, col_diff in table_diff['column_differences'].items():

                if 'nullable' in col_diff:
                    # Production should match local
                    local_nullable = col_diff['nullable']['1']  # name1 is local

                    if local_nullable:
                        sql = f"ALTER TABLE {table} ALTER COLUMN {col} DROP NOT NULL;"
                        print(f"-- Make {table}.{col} nullable (to match local)")
                        print(sql)
                        sql_statements.append(sql)
                    else:
                        sql = f"ALTER TABLE {table} ALTER COLUMN {col} SET NOT NULL;"
                        print(f"-- Make {table}.{col} NOT NULL (to match local)")
                        print(sql)
                        sql_statements.append(sql)
                    print()

                if 'type' in col_diff:
                    # Production should match local
                    local_type = col_diff['type']['1']

                    sql = f"ALTER TABLE {table} ALTER COLUMN {col} TYPE {local_type};"
                    print(f"-- Change {table}.{col} type to match local")
                    print(sql)
                    sql_statements.append(sql)
                    print()

                if 'default' in col_diff:
                    local_default = col_diff['default']['1']

                    if local_default:
                        sql = f"ALTER TABLE {table} ALTER COLUMN {col} SET DEFAULT {local_default};"
                        print(f"-- Set {table}.{col} default to match local")
                        print(sql)
                        sql_statements.append(sql)
                    else:
                        sql = f"ALTER TABLE {table} ALTER COLUMN {col} DROP DEFAULT;"
                        print(f"-- Drop {table}.{col} default to match local")
                        print(sql)
                        sql_statements.append(sql)
                    print()

    if not sql_statements:
        print("✅ No SQL fixes needed!")

    print(f"{'='*80}\n")

    return sql_statements


def main():
    parser = argparse.ArgumentParser(
        description='Compare database schemas',
        epilog='Remember to start Cloud SQL proxy before running:\n'
               '  cloud-sql-proxy saral-erp-479508:asia-south1:saral-erp-db --port=5433'
    )
    parser.add_argument('--local', action='store_true', help='Include local database')
    parser.add_argument('--production', action='store_true', help='Include production database')
    parser.add_argument('--table', type=str, help='Specific table to compare (optional)')
    parser.add_argument('--generate-sql', action='store_true', help='Generate SQL fix statements')
    parser.add_argument('--output', type=str, default='schema_comparison.txt', help='Output file path (default: schema_comparison.txt)')

    args = parser.parse_args()

    if not (args.local and args.production):
        print("❌ Must specify both --local and --production")
        parser.print_help()
        sys.exit(1)

    # Redirect output to file
    import io
    from contextlib import redirect_stdout

    output_buffer = io.StringIO()

    with redirect_stdout(output_buffer):
        # Connect and get schemas
        schemas = {}

        for db_name in ['local', 'production']:
            # Print to terminal (not captured)
            print(f"🔌 Connecting to {db_name} database...", file=sys.stderr)
            conn = connect_to_db(DB_CONFIGS[db_name], db_name)
            if not conn:
                sys.exit(1)

            print(f"📊 Fetching schema from {db_name}...", file=sys.stderr)
            schemas[db_name] = get_schema_info(conn, args.table)
            conn.close()
            print(f"✅ {db_name}: {len(schemas[db_name])} tables found\n", file=sys.stderr)

        # Compare schemas (output goes to buffer)
        differences = compare_schemas(schemas['local'], schemas['production'], 'local', 'production')
        print_differences(differences, 'local', 'production')

        if args.generate_sql and differences.get('table_differences'):
            generate_sql_fixes(differences, 'local', 'production')

    # Write to file
    output_content = output_buffer.getvalue()
    with open(args.output, 'w') as f:
        f.write(output_content)

    # Print summary to terminal
    print(f"\n{'='*80}")
    print(f"Schema Comparison Complete")
    print(f"{'='*80}\n")

    # Count differences
    num_tables_diff = len(differences.get('table_differences', {}))
    num_tables_only_local = len(differences.get('tables_only_in_1', []))
    num_tables_only_prod = len(differences.get('tables_only_in_2', []))

    if num_tables_diff == 0 and num_tables_only_local == 0 and num_tables_only_prod == 0:
        print("✅ No schema differences found!")
    else:
        print(f"⚠️  Found differences:")
        if num_tables_only_local > 0:
            print(f"   📋 {num_tables_only_local} tables only in local")
        if num_tables_only_prod > 0:
            print(f"   📋 {num_tables_only_prod} tables only in production")
        if num_tables_diff > 0:
            print(f"   📊 {num_tables_diff} tables with differences")

            # Count column differences
            total_col_diffs = 0
            for table_diff in differences['table_differences'].values():
                if 'column_differences' in table_diff:
                    total_col_diffs += len(table_diff['column_differences'])

            if total_col_diffs > 0:
                print(f"   🔧 {total_col_diffs} column differences found")

    print(f"\n📄 Full report saved to: {args.output}")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    main()
