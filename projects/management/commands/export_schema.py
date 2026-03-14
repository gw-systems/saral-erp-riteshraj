import os
from django.core.management.base import BaseCommand
from django.db import connection
from datetime import datetime


class Command(BaseCommand):
    help = 'Export complete database schema to beautifully formatted markdown file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='database_schema.md',
            help='Output filename (default: database_schema.md)'
        )
        parser.add_argument(
            '--tables',
            type=str,
            help='Comma-separated list of specific tables to export (optional)'
        )

    def handle(self, *args, **options):
        output_file = options['output']
        specific_tables = options.get('tables', '').split(',') if options.get('tables') else None
        
        self.stdout.write(self.style.SUCCESS(f'🚀 Exporting database schema to {output_file}...'))
        
        with connection.cursor() as cursor:
            self.export_beautiful_markdown(cursor, output_file, specific_tables)
        
        self.stdout.write(self.style.SUCCESS(f'✅ Schema exported successfully to {output_file}'))
        self.stdout.write(self.style.SUCCESS(f'📄 Open the file to view beautiful documentation!'))

    def export_beautiful_markdown(self, cursor, output_file, specific_tables=None):
        """Export schema as beautifully formatted markdown"""
        
        # Get all tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        all_tables = [row[0] for row in cursor.fetchall()]
        
        # Filter tables if specific ones requested
        if specific_tables:
            tables = [t for t in all_tables if t in specific_tables]
        else:
            tables = all_tables
        
        with open(output_file, 'w', encoding='utf-8') as f:
            # Header with emoji and styling
            f.write("# 🗄️ Database Schema Documentation\n\n")
            f.write("---\n\n")
            
            # Metadata box
            f.write("## 📊 Schema Information\n\n")
            f.write("| Property | Value |\n")
            f.write("|----------|-------|\n")
            f.write(f"| **Generated** | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |\n")
            f.write(f"| **Total Tables** | {len(tables)} |\n")
            f.write(f"| **Database** | {connection.settings_dict.get('NAME', 'N/A')} |\n")
            f.write("\n---\n\n")
            
            # Beautiful Table of Contents with categories
            f.write("## 📑 Table of Contents\n\n")
            
            # Categorize tables
            categories = self.categorize_tables(tables)
            
            for category, table_list in categories.items():
                if table_list:
                    f.write(f"### {category}\n\n")
                    for table in table_list:
                        # Get row count for preview
                        try:
                            cursor.execute(f"SELECT COUNT(*) FROM {table};")
                            count = cursor.fetchone()[0]
                            count_str = f"({count:,} rows)"
                        except:
                            count_str = ""
                        
                        f.write(f"- [{self.prettify_table_name(table)}](#{table.replace('_', '-')}) {count_str}\n")
                    f.write("\n")
            
            f.write("---\n\n")
            
            # Detailed schema for each table
            for table in tables:
                self.write_beautiful_table(cursor, f, table)

    def categorize_tables(self, tables):
        """Categorize tables for better organization"""
        categories = {
            "👥 User & Authentication": [],
            "📦 Projects & Clients": [],
            "🏢 Vendors & Warehouses": [],
            "⚙️ Operations": [],
            "💰 Finance & Billing": [],
            "🔧 System & Configuration": [],
            "📋 Other": []
        }
        
        for table in tables:
            if 'user' in table or 'auth' in table or 'account' in table:
                categories["👥 User & Authentication"].append(table)
            elif 'project' in table or 'client' in table:
                categories["📦 Projects & Clients"].append(table)
            elif 'vendor' in table or 'warehouse' in table:
                categories["🏢 Vendors & Warehouses"].append(table)
            elif 'operation' in table or 'daily' in table or 'mis' in table or 'dispute' in table:
                categories["⚙️ Operations"].append(table)
            elif 'billing' in table or 'invoice' in table or 'payment' in table or 'adhoc' in table:
                categories["💰 Finance & Billing"].append(table)
            elif 'setting' in table or 'config' in table or 'location' in table or 'gst' in table or 'city' in table:
                categories["🔧 System & Configuration"].append(table)
            else:
                categories["📋 Other"].append(table)
        
        # Remove empty categories
        return {k: v for k, v in categories.items() if v}

    def prettify_table_name(self, table_name):
        """Convert table_name to Pretty Table Name"""
        return ' '.join(word.capitalize() for word in table_name.split('_'))

    def write_beautiful_table(self, cursor, f, table_name):
        """Write beautifully formatted table schema"""
        
        # Table header with icon
        icon = self.get_table_icon(table_name)
        f.write(f"## {icon} {self.prettify_table_name(table_name)}\n\n")
        f.write(f"> **Database Table:** `{table_name}`\n\n")
        
        # Get columns with enhanced information
        cursor.execute(f"""
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                column_default,
                col_description((table_schema||'.'||table_name)::regclass::oid, ordinal_position) as description
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position;
        """)
        
        columns = cursor.fetchall()
        
        # Column details with beautiful formatting
        f.write("### 📋 Columns\n\n")
        f.write("| # | Column | Type | Constraints | Default | Description |\n")
        f.write("|---|--------|------|-------------|---------|-------------|\n")
        
        for idx, col in enumerate(columns, 1):
            col_name = f"`{col[0]}`"
            data_type = col[1]
            
            # Format data type with length/precision
            if col[2]:  # character_maximum_length
                data_type = f"{data_type}({col[2]})"
            elif col[3]:  # numeric_precision
                if col[4]:  # numeric_scale
                    data_type = f"{data_type}({col[3]},{col[4]})"
                else:
                    data_type = f"{data_type}({col[3]})"
            
            # Constraints badges
            constraints = []
            if col[5] == 'NO':
                constraints.append("🔴 NOT NULL")
            else:
                constraints.append("⚪ NULLABLE")
            
            constraint_str = "<br>".join(constraints)
            default = f"`{col[6]}`" if col[6] else "—"
            description = col[7] if col[7] else "—"
            
            f.write(f"| {idx} | {col_name} | `{data_type}` | {constraint_str} | {default} | {description} |\n")
        
        # Get primary key with styling
        cursor.execute(f"""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = '{table_name}'::regclass AND i.indisprimary;
        """)
        pk = cursor.fetchall()
        if pk:
            pk_cols = ', '.join([f"`{p[0]}`" for p in pk])
            f.write(f"\n> 🔑 **Primary Key:** {pk_cols}\n\n")
        
        # Get foreign keys with beautiful formatting
        cursor.execute(f"""
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = '{table_name}';
        """)
        fks = cursor.fetchall()
        if fks:
            f.write("### 🔗 Foreign Keys\n\n")
            f.write("| Column | References | Constraint |\n")
            f.write("|--------|------------|------------|\n")
            for fk in fks:
                f.write(f"| `{fk[1]}` | `{fk[2]}`.`{fk[3]}` | `{fk[0]}` |\n")
            f.write("\n")
        
        # Get indexes with beautiful formatting
        cursor.execute(f"""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = '{table_name}'
            AND indexname NOT LIKE '%pkey%'
            ORDER BY indexname;
        """)
        indexes = cursor.fetchall()
        if indexes:
            f.write("### ⚡ Indexes\n\n")
            for idx_name, idx_def in indexes:
                f.write(f"**`{idx_name}`**\n")
                f.write(f"```sql\n{idx_def}\n```\n\n")
        
        # Get row count with formatting
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            count = cursor.fetchone()[0]
            
            # Add emoji based on count
            if count == 0:
                count_emoji = "📭"
            elif count < 100:
                count_emoji = "📊"
            elif count < 1000:
                count_emoji = "📈"
            else:
                count_emoji = "💾"
            
            f.write(f"> {count_emoji} **Total Rows:** {count:,}\n\n")
        except:
            f.write("> ⚠️ **Row Count:** Unable to determine\n\n")
        
        # Sample data preview (first 3 rows)
        try:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 3;")
            sample_rows = cursor.fetchall()
            if sample_rows:
                f.write("### 👁️ Sample Data Preview\n\n")
                f.write("<details>\n<summary>Click to view sample rows</summary>\n\n")
                
                # Column headers
                col_names = [col[0] for col in columns]
                f.write("| " + " | ".join(col_names) + " |\n")
                f.write("|" + "|".join(["---" for _ in col_names]) + "|\n")
                
                # Rows
                for row in sample_rows:
                    row_values = [str(val)[:50] if val is not None else "NULL" for val in row]
                    f.write("| " + " | ".join(row_values) + " |\n")
                
                f.write("\n</details>\n\n")
        except:
            pass
        
        f.write("---\n\n")

    def get_table_icon(self, table_name):
        """Get appropriate emoji icon for table"""
        icons = {
            'user': '👤',
            'project': '📁',
            'client': '🤝',
            'vendor': '🏭',
            'warehouse': '🏢',
            'billing': '💰',
            'invoice': '🧾',
            'payment': '💳',
            'operation': '⚙️',
            'daily': '📅',
            'location': '📍',
            'contact': '📞',
            'document': '📄',
            'photo': '📸',
            'rate': '💵',
            'agreement': '📜',
            'dispute': '⚠️',
            'notification': '🔔',
            'log': '📝',
        }
        
        for keyword, icon in icons.items():
            if keyword in table_name:
                return icon
        
        return '📋'