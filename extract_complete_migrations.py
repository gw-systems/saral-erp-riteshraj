#!/usr/bin/env python3
"""
Complete Migration Extractor and Analyzer
Extracts all migrations with full content, dependencies, and creates a comprehensive report.
"""

import os
import re
from pathlib import Path
from collections import defaultdict
import json
from datetime import datetime

class MigrationExtractor:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.migrations = defaultdict(list)
        self.analysis = {
            'apps': {},
            'dependencies': [],
            'cross_app_deps': [],
            'model_operations': defaultdict(list),
            'fk_references': [],
            'data_migrations': [],
            'issues': []
        }
    
    def find_migrations(self):
        """Find all migration files in the project."""
        print("🔍 Scanning for migration files...")
        
        for app_dir in self.base_dir.iterdir():
            if not app_dir.is_dir():
                continue
            
            migrations_dir = app_dir / 'migrations'
            if not migrations_dir.exists():
                continue
            
            app_name = app_dir.name
            
            for migration_file in sorted(migrations_dir.glob('*.py')):
                if migration_file.name == '__init__.py':
                    continue
                
                if migration_file.name.startswith('__pycache__'):
                    continue
                
                try:
                    with open(migration_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    migration_info = self.parse_migration(app_name, migration_file.name, content)
                    self.migrations[app_name].append(migration_info)
                    
                except Exception as e:
                    print(f"   ⚠️  Error reading {app_name}/{migration_file.name}: {e}")
        
        print(f"   Found {sum(len(v) for v in self.migrations.values())} migrations across {len(self.migrations)} apps\n")
    
    def parse_migration(self, app_name, filename, content):
        """Parse a migration file and extract all relevant information."""
        info = {
            'app': app_name,
            'filename': filename,
            'number': self.extract_migration_number(filename),
            'content': content,
            'dependencies': [],
            'operations': {},
            'models_created': [],
            'models_deleted': [],
            'models_renamed': [],
            'fields_added': [],
            'fields_removed': [],
            'fields_altered': [],
            'fk_references': [],
            'is_data_migration': False,
            'has_runpython': False,
            'has_runsql': False,
            'line_count': len(content.split('\n'))
        }
        
        # Extract dependencies
        deps_match = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if deps_match:
            deps_content = deps_match.group(1)
            for match in re.finditer(r'\([\'"](\w+)[\'"],\s*[\'"]([^\'\"]+)[\'"]\)', deps_content):
                dep_app, dep_mig = match.group(1), match.group(2)
                info['dependencies'].append({'app': dep_app, 'migration': dep_mig})
                
                # Track cross-app dependencies
                if dep_app != app_name:
                    self.analysis['cross_app_deps'].append({
                        'from_app': app_name,
                        'from_migration': filename,
                        'to_app': dep_app,
                        'to_migration': dep_mig
                    })
        
        # Extract operations
        operations_count = {
            'CreateModel': len(re.findall(r'migrations\.CreateModel', content)),
            'DeleteModel': len(re.findall(r'migrations\.DeleteModel', content)),
            'RenameModel': len(re.findall(r'migrations\.RenameModel', content)),
            'AlterModelTable': len(re.findall(r'migrations\.AlterModelTable', content)),
            'AlterUniqueTogether': len(re.findall(r'migrations\.AlterUniqueTogether', content)),
            'AlterIndexTogether': len(re.findall(r'migrations\.AlterIndexTogether', content)),
            'AlterModelOptions': len(re.findall(r'migrations\.AlterModelOptions', content)),
            'AddField': len(re.findall(r'migrations\.AddField', content)),
            'RemoveField': len(re.findall(r'migrations\.RemoveField', content)),
            'AlterField': len(re.findall(r'migrations\.AlterField', content)),
            'RenameField': len(re.findall(r'migrations\.RenameField', content)),
            'AddIndex': len(re.findall(r'migrations\.AddIndex', content)),
            'RemoveIndex': len(re.findall(r'migrations\.RemoveIndex', content)),
            'AddConstraint': len(re.findall(r'migrations\.AddConstraint', content)),
            'RemoveConstraint': len(re.findall(r'migrations\.RemoveConstraint', content)),
            'RunPython': len(re.findall(r'migrations\.RunPython', content)),
            'RunSQL': len(re.findall(r'migrations\.RunSQL', content)),
        }
        info['operations'] = {k: v for k, v in operations_count.items() if v > 0}
        
        # Detect data migrations
        if operations_count['RunPython'] > 0 or operations_count['RunSQL'] > 0:
            info['is_data_migration'] = True
            info['has_runpython'] = operations_count['RunPython'] > 0
            info['has_runsql'] = operations_count['RunSQL'] > 0
            self.analysis['data_migrations'].append({
                'app': app_name,
                'migration': filename
            })
        
        # Extract model creations
        for match in re.finditer(r'CreateModel\s*\(\s*name=[\'"](\w+)[\'"]', content):
            model_name = match.group(1)
            info['models_created'].append(model_name)
            self.analysis['model_operations'][model_name].append({
                'operation': 'CREATE',
                'app': app_name,
                'migration': filename
            })
        
        # Extract model deletions
        for match in re.finditer(r'DeleteModel\s*\(\s*name=[\'"](\w+)[\'"]', content):
            model_name = match.group(1)
            info['models_deleted'].append(model_name)
            self.analysis['model_operations'][model_name].append({
                'operation': 'DELETE',
                'app': app_name,
                'migration': filename
            })
        
        # Extract model renames
        for match in re.finditer(r'RenameModel\s*\(\s*old_name=[\'"](\w+)[\'"],\s*new_name=[\'"](\w+)[\'"]', content):
            old_name, new_name = match.group(1), match.group(2)
            info['models_renamed'].append({'old': old_name, 'new': new_name})
            self.analysis['model_operations'][old_name].append({
                'operation': 'RENAME',
                'to': new_name,
                'app': app_name,
                'migration': filename
            })
        
        # Extract FK references
        for match in re.finditer(r"to=['\"](\w+)\.(\w+)['\"]", content):
            target_app, target_model = match.group(1), match.group(2)
            info['fk_references'].append({
                'target_app': target_app,
                'target_model': target_model
            })
            self.analysis['fk_references'].append({
                'from_app': app_name,
                'from_migration': filename,
                'to_app': target_app,
                'to_model': target_model
            })
        
        # Extract field operations
        for match in re.finditer(r'AddField\s*\(\s*model_name=[\'"](\w+)[\'"],\s*name=[\'"](\w+)[\'"]', content):
            model, field = match.group(1), match.group(2)
            info['fields_added'].append({'model': model, 'field': field})
        
        for match in re.finditer(r'RemoveField\s*\(\s*model_name=[\'"](\w+)[\'"],\s*name=[\'"](\w+)[\'"]', content):
            model, field = match.group(1), match.group(2)
            info['fields_removed'].append({'model': model, 'field': field})
        
        for match in re.finditer(r'RenameField\s*\(\s*model_name=[\'"](\w+)[\'"],\s*old_name=[\'"](\w+)[\'"],\s*new_name=[\'"](\w+)[\'"]', content):
            model, old, new = match.group(1), match.group(2), match.group(3)
            info['fields_altered'].append({'model': model, 'old_name': old, 'new_name': new, 'type': 'RENAME'})
        
        return info
    
    def extract_migration_number(self, filename):
        """Extract the migration number from filename."""
        match = re.search(r'^(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    def analyze_dependencies(self):
        """Analyze migration dependencies for issues."""
        print("🔗 Analyzing dependencies...")
        
        # Check for circular dependencies
        graph = defaultdict(set)
        for dep in self.analysis['cross_app_deps']:
            graph[dep['from_app']].add(dep['to_app'])
        
        # Simple cycle detection
        def has_cycle(node, visited, rec_stack):
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, visited, rec_stack):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        visited = set()
        for node in graph:
            if node not in visited:
                rec_stack = set()
                if has_cycle(node, visited, rec_stack):
                    self.analysis['issues'].append({
                        'type': 'CIRCULAR_DEPENDENCY',
                        'app': node,
                        'message': f'Circular dependency detected involving {node}'
                    })
        
        # Check for FK references to models that don't exist
        all_models = set()
        for model, operations in self.analysis['model_operations'].items():
            for op in operations:
                if op['operation'] == 'CREATE':
                    all_models.add((op['app'], model))
        
        for fk_ref in self.analysis['fk_references']:
            target = (fk_ref['to_app'], fk_ref['to_model'])
            if target not in all_models and fk_ref['to_app'] not in ['auth', 'contenttypes']:
                self.analysis['issues'].append({
                    'type': 'MISSING_FK_TARGET',
                    'from_app': fk_ref['from_app'],
                    'from_migration': fk_ref['from_migration'],
                    'to_app': fk_ref['to_app'],
                    'to_model': fk_ref['to_model'],
                    'message': f"FK reference to {fk_ref['to_app']}.{fk_ref['to_model']} but model creation not found"
                })
        
        print(f"   Found {len(self.analysis['issues'])} potential issues\n")
    
    def generate_report(self, output_file):
        """Generate a comprehensive markdown report."""
        print("📝 Generating comprehensive report...")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# COMPLETE MIGRATION ANALYSIS REPORT\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Base Directory:** {self.base_dir}\n\n")
            
            f.write("---\n\n")
            
            # Summary
            f.write("## 📊 SUMMARY\n\n")
            f.write(f"- **Total Apps:** {len(self.migrations)}\n")
            f.write(f"- **Total Migrations:** {sum(len(v) for v in self.migrations.values())}\n")
            f.write(f"- **Cross-App Dependencies:** {len(self.analysis['cross_app_deps'])}\n")
            f.write(f"- **Data Migrations:** {len(self.analysis['data_migrations'])}\n")
            f.write(f"- **Potential Issues:** {len(self.analysis['issues'])}\n\n")
            
            # App Overview
            f.write("## 📦 APPS OVERVIEW\n\n")
            f.write("| App | Migrations | First | Last | Data Migrations |\n")
            f.write("|-----|------------|-------|------|----------------|\n")
            
            for app_name in sorted(self.migrations.keys()):
                migs = self.migrations[app_name]
                data_mig_count = sum(1 for m in migs if m['is_data_migration'])
                first = migs[0]['filename'] if migs else 'N/A'
                last = migs[-1]['filename'] if migs else 'N/A'
                f.write(f"| {app_name} | {len(migs)} | {first} | {last} | {data_mig_count} |\n")
            
            f.write("\n")
            
            # Issues
            if self.analysis['issues']:
                f.write("## 🚨 POTENTIAL ISSUES\n\n")
                for issue in self.analysis['issues']:
                    f.write(f"### {issue['type']}\n")
                    f.write(f"**Message:** {issue['message']}\n")
                    for key, value in issue.items():
                        if key not in ['type', 'message']:
                            f.write(f"- **{key}:** {value}\n")
                    f.write("\n")
            
            # Cross-App Dependencies
            f.write("## 🔗 CROSS-APP DEPENDENCIES\n\n")
            if self.analysis['cross_app_deps']:
                f.write("```\n")
                for dep in self.analysis['cross_app_deps']:
                    f.write(f"{dep['from_app']}.{dep['from_migration']} -> {dep['to_app']}.{dep['to_migration']}\n")
                f.write("```\n\n")
            else:
                f.write("No cross-app dependencies found.\n\n")
            
            # Model Operations Timeline
            f.write("## 📋 MODEL OPERATIONS TIMELINE\n\n")
            for model_name in sorted(self.analysis['model_operations'].keys()):
                ops = self.analysis['model_operations'][model_name]
                f.write(f"### {model_name}\n")
                for op in ops:
                    f.write(f"- **{op['operation']}** in `{op['app']}/{op['migration']}`")
                    if 'to' in op:
                        f.write(f" → renamed to `{op['to']}`")
                    f.write("\n")
                f.write("\n")
            
            # Complete Migration Listing
            f.write("## 📄 COMPLETE MIGRATION FILES\n\n")
            f.write("---\n\n")
            
            for app_name in sorted(self.migrations.keys()):
                f.write(f"# APP: {app_name.upper()}\n\n")
                f.write("=" * 80 + "\n\n")
                
                for mig in self.migrations[app_name]:
                    f.write(f"## {mig['filename']}\n\n")
                    
                    # Metadata
                    f.write(f"**Migration Number:** {mig['number']}\n")
                    f.write(f"**Lines:** {mig['line_count']}\n")
                    if mig['is_data_migration']:
                        f.write(f"**⚠️ DATA MIGRATION**")
                        if mig['has_runpython']:
                            f.write(f" (RunPython)")
                        if mig['has_runsql']:
                            f.write(f" (RunSQL)")
                        f.write("\n")
                    f.write("\n")
                    
                    # Dependencies
                    if mig['dependencies']:
                        f.write("**Dependencies:**\n")
                        for dep in mig['dependencies']:
                            marker = "🔗" if dep['app'] != app_name else "↪️"
                            f.write(f"- {marker} `{dep['app']}.{dep['migration']}`\n")
                        f.write("\n")
                    
                    # Operations Summary
                    if mig['operations']:
                        f.write("**Operations:**\n")
                        for op, count in mig['operations'].items():
                            f.write(f"- {op}: {count}\n")
                        f.write("\n")
                    
                    # Models Created
                    if mig['models_created']:
                        f.write("**Models Created:** ")
                        f.write(", ".join(f"`{m}`" for m in mig['models_created']))
                        f.write("\n\n")
                    
                    # Models Deleted
                    if mig['models_deleted']:
                        f.write("**Models Deleted:** ")
                        f.write(", ".join(f"`{m}`" for m in mig['models_deleted']))
                        f.write("\n\n")
                    
                    # Models Renamed
                    if mig['models_renamed']:
                        f.write("**Models Renamed:**\n")
                        for rename in mig['models_renamed']:
                            f.write(f"- `{rename['old']}` → `{rename['new']}`\n")
                        f.write("\n")
                    
                    # FK References
                    if mig['fk_references']:
                        f.write("**Foreign Key References:**\n")
                        fk_targets = defaultdict(list)
                        for fk in mig['fk_references']:
                            fk_targets[fk['target_app']].append(fk['target_model'])
                        for app, models in fk_targets.items():
                            f.write(f"- To `{app}`: {', '.join(set(models))}\n")
                        f.write("\n")
                    
                    # Complete File Content
                    f.write("**Complete File Content:**\n\n")
                    f.write("```python\n")
                    f.write(mig['content'])
                    f.write("\n```\n\n")
                    f.write("-" * 80 + "\n\n")
                
                f.write("\n" + "=" * 80 + "\n\n")
        
        print(f"   ✅ Report saved to: {output_file}\n")
    
    def generate_json_analysis(self, output_file):
        """Generate JSON analysis file."""
        print("📊 Generating JSON analysis...")
        
        json_data = {
            'summary': {
                'total_apps': len(self.migrations),
                'total_migrations': sum(len(v) for v in self.migrations.values()),
                'cross_app_deps': len(self.analysis['cross_app_deps']),
                'data_migrations': len(self.analysis['data_migrations']),
                'issues': len(self.analysis['issues'])
            },
            'apps': {
                app: [
                    {
                        'filename': m['filename'],
                        'number': m['number'],
                        'dependencies': m['dependencies'],
                        'operations': m['operations'],
                        'is_data_migration': m['is_data_migration'],
                        'models_created': m['models_created'],
                        'models_deleted': m['models_deleted'],
                        'fk_references': m['fk_references']
                    }
                    for m in migs
                ]
                for app, migs in self.migrations.items()
            },
            'cross_app_dependencies': self.analysis['cross_app_deps'],
            'data_migrations': self.analysis['data_migrations'],
            'model_operations': dict(self.analysis['model_operations']),
            'issues': self.analysis['issues']
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)
        
        print(f"   ✅ JSON saved to: {output_file}\n")


def main():
    import sys
    
    # Get base directory from argument or use current directory
    if len(sys.argv) > 1:
        base_dir = sys.argv[1]
    else:
        base_dir = os.getcwd()
    
    print("=" * 80)
    print("🔍 COMPLETE MIGRATION EXTRACTOR AND ANALYZER")
    print("=" * 80)
    print()
    print(f"📁 Scanning: {base_dir}")
    print()
    
    extractor = MigrationExtractor(base_dir)
    
    # Extract migrations
    extractor.find_migrations()
    
    # Analyze
    extractor.analyze_dependencies()
    
    # Generate outputs
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    report_file = f'COMPLETE_MIGRATIONS_REPORT_{timestamp}.md'
    json_file = f'migrations_analysis_{timestamp}.json'
    
    extractor.generate_report(report_file)
    extractor.generate_json_analysis(json_file)
    
    print("=" * 80)
    print("✅ EXTRACTION COMPLETE")
    print("=" * 80)
    print()
    print(f"📄 Markdown Report: {report_file}")
    print(f"📊 JSON Analysis: {json_file}")
    print()
    print("Share the markdown report for complete analysis!")
    print()


if __name__ == '__main__':
    main()