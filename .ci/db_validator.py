#!/usr/bin/env python3
"""
Saral ERP - Database Schema Validator for CI/CD
Compares local and production databases to prevent deployment issues.

Usage:
    python .ci/db_validator.py --quick    # Fast check (migrations only)
    python .ci/db_validator.py --full     # Complete validation
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict
import argparse

# ANSI Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

class DatabaseValidator:
    """Validates database schema consistency between local and production"""
    
    def __init__(self):
        self.local_conn = None
        self.prod_conn = None
        self.issues = []
        self.warnings = []
        self.successes = []
        
    def connect_databases(self):
        """Establish connections to both databases"""
        print(f"\n{BLUE}{'='*80}{RESET}")
        print(f"{BOLD}🔌 Connecting to Databases...{RESET}")
        print(f"{BLUE}{'='*80}{RESET}\n")
        
        try:
            # Local database
            print(f"📍 Connecting to LOCAL database...")
            self.local_conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=os.getenv('DB_PORT', '5432'),
                database=os.getenv('DB_NAME', 'erp'),
                user=os.getenv('DB_USER', 'admin'),
                password=os.getenv('DB_PASSWORD', '')
            )
            print(f"{GREEN}✓ Local database connected{RESET}")
            
            # Production database via Cloud SQL Proxy
            print(f"📍 Connecting to PRODUCTION database (via Cloud SQL Proxy on port 5433)...")
            
            # In CI/CD, password comes from environment
            prod_password = os.getenv('PROD_DB_PASSWORD')
            if not prod_password:
                # For manual runs, prompt for password
                prod_password = input("Enter production admin password: ")
            
            self.prod_conn = psycopg2.connect(
                host='127.0.0.1',
                port='5433',
                database='erp',
                user='admin',
                password=prod_password
            )
            print(f"{GREEN}✓ Production database connected{RESET}\n")
            
        except Exception as e:
            print(f"{RED}✗ Connection failed: {str(e)}{RESET}")
            print(f"\n{YELLOW}Make sure Cloud SQL Proxy is running:{RESET}")
            print(f"  ./cloud-sql-proxy saral-erp-479508:asia-south1:saral-erp-db --port 5433")
            sys.exit(1)
    
    def get_migrations(self, conn) -> dict:
        """Get all applied migrations from django_migrations table"""
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("""
            SELECT app, name, applied 
            FROM django_migrations 
            ORDER BY app, id
        """)
        
        migrations = defaultdict(list)
        for row in cursor.fetchall():
            migrations[row['app']].append(row['name'])
        
        cursor.close()
        return dict(migrations)
    
    def compare_migrations(self):
        """Compare migration states between local and production"""
        print(f"\n{BLUE}{'='*80}{RESET}")
        print(f"{BOLD}📋 Comparing Migration States...{RESET}")
        print(f"{BLUE}{'='*80}{RESET}\n")
        
        local_migrations = self.get_migrations(self.local_conn)
        prod_migrations = self.get_migrations(self.prod_conn)
        
        all_apps = sorted(set(local_migrations.keys()) | set(prod_migrations.keys()))
        
        migration_issues = []
        
        for app in all_apps:
            local_migs = local_migrations.get(app, [])
            prod_migs = prod_migrations.get(app, [])
            
            local_count = len(local_migs)
            prod_count = len(prod_migs)
            
            if local_count == prod_count:
                print(f"{GREEN}✓{RESET} {app:20s} - {local_count} migrations (SYNCED)")
            else:
                print(f"{RED}✗{RESET} {app:20s} - Local: {local_count}, Prod: {prod_count} (MISMATCH)")
                
                # Find differences
                local_set = set(local_migs)
                prod_set = set(prod_migs)
                
                missing_in_prod = local_set - prod_set
                missing_in_local = prod_set - local_set
                
                if missing_in_prod:
                    issue = f"App '{app}': {len(missing_in_prod)} migration(s) in LOCAL but NOT in PRODUCTION:\n"
                    for mig in sorted(missing_in_prod):
                        issue += f"    - {mig}\n"
                    migration_issues.append(issue)
                    self.issues.append(issue)
                
                if missing_in_local:
                    issue = f"App '{app}': {len(missing_in_local)} migration(s) in PRODUCTION but NOT in LOCAL:\n"
                    for mig in sorted(missing_in_local):
                        issue += f"    - {mig}\n"
                    migration_issues.append(issue)
                    self.issues.append(issue)
        
        if not migration_issues:
            msg = "All migrations are synchronized! ✓"
            print(f"\n{GREEN}{BOLD}{msg}{RESET}")
            self.successes.append(msg)
        else:
            print(f"\n{RED}{BOLD}Migration mismatches found!{RESET}")
            for issue in migration_issues:
                print(f"\n{YELLOW}{issue}{RESET}")
    
    def get_all_tables(self, conn) -> list:
        """Get list of all tables in public schema"""
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            AND table_name NOT LIKE 'pg_%'
            AND table_name NOT LIKE 'sql_%'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return tables
    
    def compare_table_counts(self):
        """Quick comparison of table counts"""
        print(f"\n{BLUE}{'='*80}{RESET}")
        print(f"{BOLD}🗂️  Comparing Table Counts...{RESET}")
        print(f"{BLUE}{'='*80}{RESET}\n")
        
        local_tables = set(self.get_all_tables(self.local_conn))
        prod_tables = set(self.get_all_tables(self.prod_conn))
        
        only_local = local_tables - prod_tables
        only_prod = prod_tables - local_tables
        
        print(f"Local tables: {len(local_tables)}")
        print(f"Production tables: {len(prod_tables)}")
        print(f"Common tables: {len(local_tables & prod_tables)}")
        
        if only_local:
            issue = f"Tables in LOCAL only ({len(only_local)}): {', '.join(sorted(only_local))}"
            print(f"\n{YELLOW}⚠ {issue}{RESET}")
            self.warnings.append(issue)
        
        if only_prod:
            issue = f"Tables in PRODUCTION only ({len(only_prod)}): {', '.join(sorted(only_prod))}"
            print(f"\n{YELLOW}⚠ {issue}{RESET}")
            self.warnings.append(issue)
        
        if not only_local and not only_prod:
            msg = "Table counts match! ✓"
            print(f"\n{GREEN}{BOLD}{msg}{RESET}")
            self.successes.append(msg)
    
    def generate_report(self):
        """Generate final validation report"""
        print(f"\n\n{BLUE}{'='*80}{RESET}")
        print(f"{BOLD}📊 VALIDATION REPORT{RESET}")
        print(f"{BLUE}{'='*80}{RESET}\n")
        
        print(f"{GREEN}{BOLD}Successes: {len(self.successes)}{RESET}")
        for success in self.successes:
            print(f"  {GREEN}✓{RESET} {success}")
        
        if self.warnings:
            print(f"\n{YELLOW}{BOLD}Warnings: {len(self.warnings)}{RESET}")
            for warning in self.warnings:
                print(f"  {YELLOW}⚠{RESET} {warning}")
        
        if self.issues:
            print(f"\n{RED}{BOLD}Issues: {len(self.issues)}{RESET}")
            for issue in self.issues:
                print(f"  {RED}✗{RESET} {issue}")
        
        print(f"\n{BLUE}{'='*80}{RESET}")
        
        if self.issues:
            print(f"\n{RED}{BOLD}❌ VALIDATION FAILED - DEPLOYMENT BLOCKED{RESET}")
            print(f"{YELLOW}Fix all issues above before deploying.{RESET}\n")
            return False
        elif self.warnings:
            print(f"\n{YELLOW}{BOLD}⚠️  VALIDATION PASSED WITH WARNINGS{RESET}")
            print(f"{YELLOW}Review warnings before deploying.{RESET}\n")
            return True
        else:
            print(f"\n{GREEN}{BOLD}✅ VALIDATION PASSED - SAFE TO DEPLOY{RESET}\n")
            return True
    
    def close_connections(self):
        """Close database connections"""
        if self.local_conn:
            self.local_conn.close()
        if self.prod_conn:
            self.prod_conn.close()
    
    def run_validation(self, quick=False):
        """Run validation"""
        try:
            self.connect_databases()
            
            # Always check migrations
            self.compare_migrations()
            
            if not quick:
                # Full table comparison
                self.compare_table_counts()
            
            # Generate report
            is_safe = self.generate_report()
            
            return is_safe
            
        except KeyboardInterrupt:
            print(f"\n\n{YELLOW}Validation interrupted by user.{RESET}")
            return False
        except Exception as e:
            print(f"\n{RED}Validation failed with error: {str(e)}{RESET}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.close_connections()


def main():
    parser = argparse.ArgumentParser(description='Saral ERP Database Validator')
    parser.add_argument('--full', action='store_true', help='Run full validation (default)')
    parser.add_argument('--quick', action='store_true', help='Quick validation (migrations only)')
    
    args = parser.parse_args()
    
    print(f"\n{BOLD}{BLUE}")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║                   SARAL ERP - DATABASE VALIDATOR                           ║")
    print("║                    Production Safety Verification                          ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print(f"{RESET}\n")
    
    validator = DatabaseValidator()
    
    is_safe = validator.run_validation(quick=args.quick)
    
    sys.exit(0 if is_safe else 1)


if __name__ == '__main__':
    main()
