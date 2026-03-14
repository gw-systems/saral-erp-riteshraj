"""
READ-ONLY LOCAL DATABASE SCHEMA DUMP

• Extracts complete PostgreSQL schema
• No comparisons
• No SQL generation
• No migrations logic
• Safe for production-like databases
• Output is pure JSON (machine + human readable)

Use this as the SINGLE SOURCE OF TRUTH.
"""

import json
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Dump complete LOCAL database schema to JSON (read-only)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="db_schema_local.json",
            help="Output JSON file name (default: db_schema_local.json)",
        )

    def handle(self, *args, **options):
        output_file = options["output"]
        cursor = connection.cursor()

        schema = {
            "database": connection.settings_dict.get("NAME"),
            "engine": connection.settings_dict.get("ENGINE"),
            "tables": {},
        }

        # ------------------------------------------------------------------
        # TABLE LIST
        # ------------------------------------------------------------------
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            schema["tables"][table] = {
                "columns": {},
                "primary_key": [],
                "foreign_keys": {},
                "indexes": {},
                "constraints": {},
            }

            # --------------------------------------------------------------
            # COLUMNS
            # --------------------------------------------------------------
            cursor.execute("""
                SELECT
                    column_name,
                    data_type,
                    udt_name,
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position;
            """, [table])

            for row in cursor.fetchall():
                schema["tables"][table]["columns"][row[0]] = {
                    "data_type": row[1],
                    "udt_name": row[2],
                    "max_length": row[3],
                    "precision": row[4],
                    "scale": row[5],
                    "nullable": row[6] == "YES",
                    "default": row[7],
                }

            # --------------------------------------------------------------
            # PRIMARY KEY
            # --------------------------------------------------------------
            cursor.execute("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a
                  ON a.attrelid = i.indrelid
                 AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass
                  AND i.indisprimary;
            """, [table])

            schema["tables"][table]["primary_key"] = [
                row[0] for row in cursor.fetchall()
            ]

            # --------------------------------------------------------------
            # FOREIGN KEYS
            # --------------------------------------------------------------
            cursor.execute("""
                SELECT
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table,
                    ccu.column_name AS foreign_column,
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
                  AND tc.table_name = %s;
            """, [table])

            for row in cursor.fetchall():
                schema["tables"][table]["foreign_keys"][row[0]] = {
                    "column": row[1],
                    "references": f"{row[2]}.{row[3]}",
                    "on_update": row[4],
                    "on_delete": row[5],
                }

            # --------------------------------------------------------------
            # INDEXES
            # --------------------------------------------------------------
            cursor.execute("""
                SELECT
                    idx.relname AS index_name,
                    i.indisunique,
                    pg_get_indexdef(i.indexrelid)
                FROM pg_index i
                JOIN pg_class tbl ON tbl.oid = i.indrelid
                JOIN pg_class idx ON idx.oid = i.indexrelid
                WHERE tbl.relname = %s
                  AND NOT i.indisprimary;
            """, [table])

            for row in cursor.fetchall():
                schema["tables"][table]["indexes"][row[0]] = {
                    "unique": row[1],
                    "definition": row[2],
                }

            # --------------------------------------------------------------
            # CHECK & UNIQUE CONSTRAINTS
            # --------------------------------------------------------------
            cursor.execute("""
                SELECT
                    tc.constraint_name,
                    tc.constraint_type,
                    cc.check_clause
                FROM information_schema.table_constraints tc
                LEFT JOIN information_schema.check_constraints cc
                  ON cc.constraint_name = tc.constraint_name
                WHERE tc.table_name = %s
                  AND tc.constraint_type IN ('CHECK', 'UNIQUE');
            """, [table])

            for row in cursor.fetchall():
                schema["tables"][table]["constraints"][row[0]] = {
                    "type": row[1],
                    "definition": row[2],
                }

        cursor.close()

        # ------------------------------------------------------------------
        # WRITE OUTPUT
        # ------------------------------------------------------------------
        with open(output_file, "w") as f:
            json.dump(schema, f, indent=2, default=str)

        self.stdout.write(self.style.SUCCESS(
            f"✅ Database schema dumped successfully → {output_file}"
        ))
