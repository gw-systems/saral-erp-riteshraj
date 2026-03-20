"""
Diagnostic management command.
Run: python manage.py diagnose_import "data/RapidShyp Rate Card 28_02_2026.xlsx"
"""
import io
import pandas as pd
from django.core.management.base import BaseCommand
from ...models import Courier

OUTPUT_FILE = r"c:\tmp\diagnose_output.txt"


class Command(BaseCommand):
    help = 'Diagnose why import_rates is silently skipping rows'

    def add_arguments(self, parser):
        parser.add_argument('excel_path', type=str)

    def _log(self, msg, style=None):
        """Write msg to both stdout and a log file, stripping non-ASCII for stdout safety."""
        safe = msg.encode('ascii', errors='replace').decode('ascii')
        if style:
            self.stdout.write(style(safe))
        else:
            self.stdout.write(safe)
        if hasattr(self, '_logfile') and self._logfile:
            self._logfile.write(msg + "\n")

    def handle(self, *args, **kwargs):
        self._logfile = open(OUTPUT_FILE, 'w', encoding='utf-8')
        try:
            self._run(kwargs['excel_path'])
        finally:
            self._logfile.close()
            self.stdout.write(f"Full output saved to: {OUTPUT_FILE}")

    def _run(self, excel_path):
        xls = pd.ExcelFile(excel_path)
        
        self._log(f"Sheets in file: {xls.sheet_names}")
        
        valid_agg_choices = [c[0] for c in Courier.Aggregator.choices]
        self._log(f"Valid Aggregator choices in DB: {valid_agg_choices}")

        # ---- Master Configuration ----
        self._log("\n" + "=" * 60)
        self._log("[Master Configuration]")
        if 'Master Configuration' not in xls.sheet_names:
            self._log("ERROR: 'Master Configuration' sheet NOT FOUND!", self.style.ERROR)
            return
        
        df = pd.read_excel(xls, sheet_name='Master Configuration')
        self._log(f"Shape: {df.shape}")
        self._log(f"Columns ({len(df.columns)}):")
        for i, col in enumerate(df.columns):
            self._log(f"  [{i}] {repr(col)}")

        self._log("\nFirst 5 rows:")
        for index, row in df.head(5).iterrows():
            self._log(f"  row {index}: {str({k: str(v) for k, v in dict(row).items()})[:300]}")

        self._log("\n--- Row-by-row trace ---")
        rows_processed = 0
        rows_skipped_nan = 0
        rows_create = 0
        rows_update = 0

        for index, row in df.iterrows():
            courier_name_raw = row.get('Courier Name')
            if pd.isna(courier_name_raw):
                rows_skipped_nan += 1
                continue
            courier_name = str(courier_name_raw).strip()
            if not courier_name or courier_name == 'nan':
                rows_skipped_nan += 1
                continue
            
            rows_processed += 1
            agg_raw = row.get('Aggregator')
            if pd.isna(agg_raw):
                agg_display = "(missing, defaults to Shipdaak)"
                agg_ok = True
            else:
                agg_display = repr(str(agg_raw).strip())
                agg_ok = str(agg_raw).strip() in valid_agg_choices
            
            # DB check
            try:
                c = Courier.objects.get(name=courier_name)
                db_status = f"EXISTS (id={c.id})"
                rows_update += 1
            except Courier.DoesNotExist:
                db_status = "NOT in DB -> CREATE"
                rows_create += 1
            
            agg_warn = "" if agg_ok else f" *** INVALID AGG (not in choices) ***"
            self._log(
                f"  Row {index}: name={repr(courier_name)} | agg={agg_display}{agg_warn} | {db_status}"
            )

        self.stdout.write(
            f"\nSummary: {rows_processed} processable rows "
            f"({rows_create} create, {rows_update} update), "
            f"{rows_skipped_nan} skipped (NaN name)"
        )

        # ---- Standard Zone Rates ----
        self.stdout.write("\n" + "=" * 60)
        zone_sheet = next((s for s in xls.sheet_names if s.strip().lower() == 'standard zone rates'), None)
        if zone_sheet:
            df_zones = pd.read_excel(xls, sheet_name=zone_sheet)
            raw_cols = list(df_zones.columns)
            df_zones.columns = [str(c).strip().lower() for c in df_zones.columns]
            self._log(f"\n[{zone_sheet}] Raw columns: {raw_cols}")
            self._log(f"Lowercased: {list(df_zones.columns)}")
            self._log(f"Shape: {df_zones.shape}")

            zone_cols = [c for c in df_zones.columns if c.startswith('z_')]
            self._log(f"Zone columns: {zone_cols}")

            if 'carrier' in df_zones.columns:
                carriers = df_zones['carrier'].dropna().unique().tolist()
                self._log(f"Unique 'carrier' values: {carriers}")

                # Cross-check with Master Config courier names
                if 'Master Configuration' in xls.sheet_names:
                    df_master = pd.read_excel(xls, sheet_name='Master Configuration')
                    master_names = set(
                        str(n).strip() for n in df_master['Courier Name'].dropna()
                        if str(n).strip() and str(n).strip() != 'nan'
                    )
                    self._log(f"\nMaster Config names: {sorted(master_names)}")
                    carrier_names_lower = set(str(c).strip() for c in carriers)
                    unmatched = carrier_names_lower - master_names
                    if unmatched:
                        self._log(f"Zone carriers NOT found in Master Config: {unmatched}", self.style.WARNING)
                    else:
                        self._log("All zone carriers match Master Config names!", self.style.SUCCESS)
            else:
                self._log(f"'carrier' column NOT found! Columns: {list(df_zones.columns)}", self.style.ERROR)
        else:
            self._log("'Standard Zone Rates' sheet NOT FOUND!", self.style.ERROR)
        
        self._log("\n=== Diagnostic Complete ===")
