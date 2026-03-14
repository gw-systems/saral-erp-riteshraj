from django.core.management.base import BaseCommand
from projects.models import ProjectCode
from supply.models import VendorCard


class Command(BaseCommand):
    help = 'Migrate unique vendor names from ProjectCode to VendorCard'

    # Exclusion list - these names will NOT be migrated to VendorCard
    EXCLUDED_NAMES = [
        '23 North',
        'Ashwathama WH (RK)',
        'Black Eagle',
        'Brahma Shankar',
        'Cross Dock',
        'Gowardhan',
        'Grandhi',
        'Hussian Zulfiqar',
        'IT Expenses',
        'Marketing/Sales',
        'Nileshkumar Patel',
        'Office Expenses',
        'Santosh Devi',
        'Sesaram',
    ]

    def handle(self, *args, **options):
        # Get unique vendor names from ProjectCode
        vendor_names = ProjectCode.objects.exclude(
            vendor_name__isnull=True
        ).exclude(
            vendor_name=''
        ).values_list('vendor_name', flat=True).distinct().order_by('vendor_name')

        created_count = 0
        skipped_count = 0
        excluded_count = 0

        self.stdout.write(f"Found {len(vendor_names)} unique vendor names")
        self.stdout.write("-" * 80)

        for vendor_name in vendor_names:
            # Check if vendor is in exclusion list
            if vendor_name in self.EXCLUDED_NAMES:
                self.stdout.write(
                    self.style.ERROR(
                        f"EXCLUDE: '{vendor_name}' (in exclusion list)"
                    )
                )
                excluded_count += 1
                continue
            # Check if VendorCard already exists using sanitize_name logic
            sanitized = VendorCard.sanitize_name(vendor_name)

            # Check all existing vendors
            exists = False
            for existing_vendor in VendorCard.objects.all():
                if VendorCard.sanitize_name(existing_vendor.vendor_legal_name) == sanitized:
                    exists = True
                    self.stdout.write(
                        self.style.WARNING(
                            f"SKIP: '{vendor_name}' (matches existing: {existing_vendor.vendor_code} - {existing_vendor.vendor_short_name})"
                        )
                    )
                    skipped_count += 1
                    break

            if not exists:
                # Create new VendorCard
                vendor_card = VendorCard.objects.create(
                    vendor_legal_name=vendor_name,
                    vendor_short_name=vendor_name  # Set both to same value
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"CREATE: '{vendor_name}' → {vendor_card.vendor_code}"
                    )
                )
                created_count += 1

        self.stdout.write("-" * 80)
        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Created: {created_count} | Skipped: {skipped_count} | Excluded: {excluded_count}"
            )
        )
