"""
Production-grade database schema comparison tool.
Compares Local vs Staging vs Production databases.
Identifies breaking changes, missing items, and generates fix SQL.
"""
import json
from django.core.management.base import BaseCommand
from django.db import connection
import psycopg2
from urllib.parse import urlparse


class Command(BaseCommand):
    help = 'Compare database schemas across Local, Staging, and Production'

    def add_arguments(self, parser):
        parser.add_argument('--staging-url', type=str, help='Staging DB URL')
        parser.add_argument('--staging-password', type=str, help='Staging DB password')
        parser.add_argument('--prod-url', type=str, help='Production DB URL')
        parser.add_argument('--prod-password', type=str, help='Production DB password')
        parser.add_argument('--output', type=str, help='Output file for report')
        parser.add_argument('--json', action='store_true', help='Output as JSON')
        parser.add_argument('--fix-sql', action='store_true', help='Generate fix SQL')

    def handle(self, *args, **options):
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('🔍 DATABASE SCHEMA COMPARISON TOOL'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write('')

        # Collect schemas
        schemas = {}
        
        # Local (Django default)
        self.stdout.write('📡 Connecting to LOCAL database...')
        schemas['local'] = self.get_schema(connection)
        self.stdout.write(self.style.SUCCESS('  ✓ Local connected'))

        # Staging
        if options['staging_url']:
            self.stdout.write('📡 Connecting to STAGING database...')
            try:
                staging_conn = self.connect_from_url(options['staging_url'], options.get('staging_password'))
                schemas['staging'] = self.get_schema(staging_conn)
                staging_conn.close()
                self.stdout.write(self.style.SUCCESS('  ✓ Staging connected'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Staging connection failed: {e}'))

        # Production
        if options['prod_url']:
            self.stdout.write('📡 Connecting to PRODUCTION database...')
            try:
                prod_conn = self.connect_from_url(options['prod_url'], options.get('prod_password'))
                schemas['prod'] = self.get_schema(prod_conn)
                prod_conn.close()
                self.stdout.write(self.style.SUCCESS('  ✓ Production connected'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Production connection failed: {e}'))

        self.stdout.write('')

        # Compare schemas
        differences = self.compare_schemas(schemas)
        
        # Output report
        if options['json']:
            self.output_json(differences, options.get('output'))
        else:
            self.output_report(differences, schemas)

        # Generate fix SQL
        if options['fix_sql'] and 'prod' in schemas:
            self.generate_fix_sql(differences, schemas)

        # Summary
        self.output_summary(differences)

    def connect_from_url(self, url, password_override=None):
        parsed = urlparse(url)
        conn = psycopg2.connect(
            dbname=parsed.path[1:],
            user=parsed.username,
            password=password_override or parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432
        )
        return conn

    def get_schema(self, conn):
        """Extract complete schema information"""
        # Handle both Django connection and psycopg2 connection
        if hasattr(conn, 'cursor'):
            cursor = conn.cursor()
            is_django = hasattr(cursor, 'db')
        else:
            cursor = conn.cursor()
            is_django = False

        schema = {
            'tables': {},
            'migrations': []
        }

        # Get all tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            schema['tables'][table] = {
                'columns': self.get_columns(cursor, table),
                'primary_keys': self.get_primary_keys(cursor, table),
                'foreign_keys': self.get_foreign_keys(cursor, table),
                'indexes': self.get_indexes(cursor, table),
                'constraints': self.get_constraints(cursor, table),
                'row_count': self.get_row_count(cursor, table)
            }

        # Get applied migrations
        try:
            cursor.execute("""
                SELECT app, name, applied 
                FROM django_migrations 
                ORDER BY app, name
            """)
            schema['migrations'] = [
                {'app': row[0], 'name': row[1], 'applied': str(row[2])}
                for row in cursor.fetchall()
            ]
        except:
            pass

        if not is_django:
            cursor.close()

        return schema

    def get_columns(self, cursor, table):
        """Get column details"""
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                column_default,
                udt_name
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, [table])
        
        columns = {}
        for row in cursor.fetchall():
            columns[row[0]] = {
                'data_type': row[1],
                'max_length': row[2],
                'precision': row[3],
                'scale': row[4],
                'nullable': row[5] == 'YES',
                'default': row[6],
                'udt_name': row[7]
            }
        return columns

    def get_primary_keys(self, cursor, table):
        """Get primary key columns"""
        cursor.execute("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass AND i.indisprimary
        """, [table])
        return [row[0] for row in cursor.fetchall()]

    def get_foreign_keys(self, cursor, table):
        """Get foreign key relationships"""
        cursor.execute("""
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column,
                tc.constraint_name,
                rc.update_rule,
                rc.delete_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
            JOIN information_schema.referential_constraints rc
                ON rc.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = %s
        """, [table])
        
        fks = {}
        for row in cursor.fetchall():
            fks[row[0]] = {
                'foreign_table': row[1],
                'foreign_column': row[2],
                'constraint_name': row[3],
                'on_update': row[4],
                'on_delete': row[5]
            }
        return fks

    def get_indexes(self, cursor, table):
        """Get indexes"""
        cursor.execute("""
            SELECT 
                indexname,
                indexdef,
                idx.indisunique
            FROM pg_indexes pgi
            JOIN pg_class cls ON cls.relname = pgi.indexname
            JOIN pg_index idx ON idx.indexrelid = cls.oid
            WHERE pgi.tablename = %s
            AND pgi.indexname NOT LIKE '%%_pkey'
        """, [table])
        
        indexes = {}
        for row in cursor.fetchall():
            indexes[row[0]] = {
                'definition': row[1],
                'unique': row[2]
            }
        return indexes

    def get_constraints(self, cursor, table):
        """Get check and unique constraints"""
        cursor.execute("""
            SELECT 
                tc.constraint_name,
                tc.constraint_type,
                cc.check_clause
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.check_constraints cc
                ON cc.constraint_name = tc.constraint_name
            WHERE tc.table_name = %s
            AND tc.constraint_type IN ('CHECK', 'UNIQUE')
        """, [table])
        
        constraints = {}
        for row in cursor.fetchall():
            constraints[row[0]] = {
                'type': row[1],
                'check_clause': row[2]
            }
        return constraints

    def get_row_count(self, cursor, table):
        """Get approximate row count"""
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            return cursor.fetchone()[0]
        except:
            return None

    def compare_schemas(self, schemas):
        """Compare schemas and identify differences"""
        differences = {
            'missing_tables': {'staging': [], 'prod': []},
            'extra_tables': {'staging': [], 'prod': []},
            'missing_columns': {'staging': {}, 'prod': {}},
            'extra_columns': {'staging': {}, 'prod': {}},
            'column_changes': {'staging': {}, 'prod': {}},
            'missing_indexes': {'staging': {}, 'prod': {}},
            'missing_fks': {'staging': {}, 'prod': {}},
            'missing_constraints': {'staging': {}, 'prod': {}},
            'migration_diff': {'staging': [], 'prod': []}
        }

        local = schemas.get('local', {})
        local_tables = set(local.get('tables', {}).keys())
        local_migrations = {(m['app'], m['name']) for m in local.get('migrations', [])}

        for env in ['staging', 'prod']:
            if env not in schemas:
                continue

            env_schema = schemas[env]
            env_tables = set(env_schema.get('tables', {}).keys())
            env_migrations = {(m['app'], m['name']) for m in env_schema.get('migrations', [])}

            # Missing tables (in local but not in env)
            differences['missing_tables'][env] = list(local_tables - env_tables)
            
            # Extra tables (in env but not in local)
            differences['extra_tables'][env] = list(env_tables - local_tables)

            # Missing migrations
            differences['migration_diff'][env] = [
                f"{app}.{name}" for app, name in (local_migrations - env_migrations)
            ]

            # Compare columns for common tables
            common_tables = local_tables & env_tables
            for table in common_tables:
                local_cols = local['tables'][table]['columns']
                env_cols = env_schema['tables'][table]['columns']

                # Missing columns
                missing = set(local_cols.keys()) - set(env_cols.keys())
                if missing:
                    differences['missing_columns'][env][table] = list(missing)

                # Extra columns
                extra = set(env_cols.keys()) - set(local_cols.keys())
                if extra:
                    differences['extra_columns'][env][table] = list(extra)

                # Column changes (type, nullable, etc.)
                common_cols = set(local_cols.keys()) & set(env_cols.keys())
                for col in common_cols:
                    changes = []
                    local_col = local_cols[col]
                    env_col = env_cols[col]

                    if local_col['data_type'] != env_col['data_type']:
                        changes.append(f"type: {env_col['data_type']} → {local_col['data_type']}")
                    if local_col['nullable'] != env_col['nullable']:
                        changes.append(f"nullable: {env_col['nullable']} → {local_col['nullable']}")
                    if local_col['max_length'] != env_col['max_length']:
                        changes.append(f"max_length: {env_col['max_length']} → {local_col['max_length']}")

                    if changes:
                        if table not in differences['column_changes'][env]:
                            differences['column_changes'][env][table] = {}
                        differences['column_changes'][env][table][col] = changes

                # Missing indexes
                local_idx = local['tables'][table]['indexes']
                env_idx = env_schema['tables'][table]['indexes']
                missing_idx = set(local_idx.keys()) - set(env_idx.keys())
                if missing_idx:
                    differences['missing_indexes'][env][table] = list(missing_idx)

                # Missing foreign keys
                local_fks = local['tables'][table]['foreign_keys']
                env_fks = env_schema['tables'][table]['foreign_keys']
                missing_fks = set(local_fks.keys()) - set(env_fks.keys())
                if missing_fks:
                    differences['missing_fks'][env][table] = list(missing_fks)

                # Missing constraints
                local_cons = local['tables'][table]['constraints']
                env_cons = env_schema['tables'][table]['constraints']
                missing_cons = set(local_cons.keys()) - set(env_cons.keys())
                if missing_cons:
                    differences['missing_constraints'][env][table] = list(missing_cons)

        return differences

    def output_report(self, differences, schemas):
        """Output human-readable report"""
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('📊 SCHEMA COMPARISON REPORT'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))

        for env in ['staging', 'prod']:
            if env not in schemas:
                continue

            env_label = 'STAGING' if env == 'staging' else 'PRODUCTION'
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(f'━━━ {env_label} vs LOCAL ━━━'))
            self.stdout.write('')

            has_issues = False

            # Missing tables
            if differences['missing_tables'][env]:
                has_issues = True
                self.stdout.write(self.style.ERROR(f"🔴 MISSING TABLES ({len(differences['missing_tables'][env])}):"))
                for table in sorted(differences['missing_tables'][env]):
                    self.stdout.write(f"     - {table}")
                self.stdout.write('')

            # Missing columns
            if differences['missing_columns'][env]:
                has_issues = True
                self.stdout.write(self.style.ERROR(f"🔴 MISSING COLUMNS:"))
                for table, cols in sorted(differences['missing_columns'][env].items()):
                    for col in sorted(cols):
                        col_info = schemas['local']['tables'][table]['columns'][col]
                        self.stdout.write(f"     - {table}.{col} ({col_info['data_type']})")
                self.stdout.write('')

            # Column changes
            if differences['column_changes'][env]:
                has_issues = True
                self.stdout.write(self.style.WARNING(f"🟡 COLUMN TYPE CHANGES:"))
                for table, cols in sorted(differences['column_changes'][env].items()):
                    for col, changes in sorted(cols.items()):
                        self.stdout.write(f"     - {table}.{col}: {', '.join(changes)}")
                self.stdout.write('')

            # Missing indexes
            if differences['missing_indexes'][env]:
                has_issues = True
                self.stdout.write(self.style.WARNING(f"🟡 MISSING INDEXES:"))
                for table, idxs in sorted(differences['missing_indexes'][env].items()):
                    for idx in sorted(idxs):
                        self.stdout.write(f"     - {table}: {idx}")
                self.stdout.write('')

            # Missing foreign keys
            if differences['missing_fks'][env]:
                has_issues = True
                self.stdout.write(self.style.WARNING(f"🟡 MISSING FOREIGN KEYS:"))
                for table, fks in sorted(differences['missing_fks'][env].items()):
                    for fk in sorted(fks):
                        self.stdout.write(f"     - {table}.{fk}")
                self.stdout.write('')

            # Missing migrations
            if differences['migration_diff'][env]:
                has_issues = True
                self.stdout.write(self.style.ERROR(f"🔴 UNAPPLIED MIGRATIONS ({len(differences['migration_diff'][env])}):"))
                for mig in sorted(differences['migration_diff'][env]):
                    self.stdout.write(f"     - {mig}")
                self.stdout.write('')

            # Extra tables (in env but not local - usually safe)
            if differences['extra_tables'][env]:
                self.stdout.write(self.style.SUCCESS(f"🟢 EXTRA TABLES (safe to ignore):"))
                for table in sorted(differences['extra_tables'][env]):
                    self.stdout.write(f"     - {table}")
                self.stdout.write('')

            if not has_issues:
                self.stdout.write(self.style.SUCCESS(f"  ✅ {env_label} matches LOCAL perfectly!"))
                self.stdout.write('')

    def generate_fix_sql(self, differences, schemas):
        """Generate SQL to fix production"""
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('🔧 FIX SQL FOR PRODUCTION'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write('')

        sql_statements = []

        # Create missing tables
        for table in differences['missing_tables'].get('prod', []):
            sql_statements.append(f"-- TODO: Create table {table}")
            sql_statements.append(f"-- Run: python manage.py sqlmigrate <app> <migration>")
            sql_statements.append('')

        # Add missing columns
        for table, cols in differences['missing_columns'].get('prod', {}).items():
            for col in cols:
                col_info = schemas['local']['tables'][table]['columns'][col]
                sql = self.generate_add_column_sql(table, col, col_info)
                sql_statements.append(sql)

        # Output SQL
        if sql_statements:
            self.stdout.write("-- Production Fix SQL")
            self.stdout.write("-- Review carefully before executing!")
            self.stdout.write("-- " + "-" * 50)
            self.stdout.write('')
            for sql in sql_statements:
                self.stdout.write(sql)
        else:
            self.stdout.write(self.style.SUCCESS("No fixes needed for production!"))

    def generate_add_column_sql(self, table, column, col_info):
        """Generate ALTER TABLE ADD COLUMN SQL"""
        data_type = col_info['udt_name'] or col_info['data_type']
        
        # Handle type with precision
        if col_info['max_length']:
            type_sql = f"{data_type}({col_info['max_length']})"
        elif col_info['precision']:
            if col_info['scale']:
                type_sql = f"NUMERIC({col_info['precision']},{col_info['scale']})"
            else:
                type_sql = f"NUMERIC({col_info['precision']})"
        else:
            type_sql = data_type

        # Nullable
        null_sql = "NULL" if col_info['nullable'] else "NOT NULL"
        
        # Default
        default_sql = ""
        if col_info['default']:
            default_sql = f" DEFAULT {col_info['default']}"
        elif not col_info['nullable']:
            # Need default for NOT NULL columns
            if 'int' in data_type:
                default_sql = " DEFAULT 0"
            elif 'numeric' in data_type or 'decimal' in data_type:
                default_sql = " DEFAULT 0"
            elif 'bool' in data_type:
                default_sql = " DEFAULT false"
            elif 'text' in data_type or 'char' in data_type:
                default_sql = " DEFAULT ''"

        return f"ALTER TABLE {table} ADD COLUMN {column} {type_sql} {null_sql}{default_sql};"

    def output_json(self, differences, output_file):
        """Output as JSON"""
        json_output = json.dumps(differences, indent=2, default=str)
        
        if output_file:
            with open(output_file, 'w') as f:
                f.write(json_output)
            self.stdout.write(self.style.SUCCESS(f"JSON output written to {output_file}"))
        else:
            self.stdout.write(json_output)

    def output_summary(self, differences):
        """Output final summary"""
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write(self.style.HTTP_INFO('📋 SUMMARY'))
        self.stdout.write(self.style.HTTP_INFO('=' * 70))
        self.stdout.write('')

        for env in ['staging', 'prod']:
            env_label = 'STAGING' if env == 'staging' else 'PRODUCTION'
            
            issues = []
            if differences['missing_tables'].get(env):
                issues.append(f"{len(differences['missing_tables'][env])} missing tables")
            if differences['missing_columns'].get(env):
                col_count = sum(len(cols) for cols in differences['missing_columns'][env].values())
                issues.append(f"{col_count} missing columns")
            if differences['column_changes'].get(env):
                change_count = sum(len(cols) for cols in differences['column_changes'][env].values())
                issues.append(f"{change_count} column changes")
            if differences['migration_diff'].get(env):
                issues.append(f"{len(differences['migration_diff'][env])} unapplied migrations")

            if issues:
                self.stdout.write(self.style.ERROR(f"🔴 {env_label}: {', '.join(issues)}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"✅ {env_label}: No issues found"))

        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO('=' * 70))