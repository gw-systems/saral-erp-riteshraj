from django.core.management.base import BaseCommand

from ...integrations.errors import ShipdaakIntegrationError
from ...models import Order
from ...services import ShipdaakLifecycleService


class Command(BaseCommand):
    help = (
        "Sync live Shipdaak tracking statuses for active shipments "
        "(booked/manifested/picked_up/out_for_delivery)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Optional max number of orders to scan in one run.",
        )

    def handle(self, *args, **options):
        limit = int(options.get("limit") or 0)
        queryset = (
            Order.objects.filter(status__in=ShipdaakLifecycleService.ACTIVE_SYNC_STATUSES)
            .exclude(awb_number__isnull=True)
            .exclude(awb_number="")
            .order_by("id")
        )
        if limit > 0:
            queryset = queryset[:limit]

        scanned = 0
        updated = 0
        unchanged = 0
        failed = 0

        for order in queryset.iterator():
            scanned += 1
            try:
                result = ShipdaakLifecycleService.sync_order_status(order)
                if result["status_updated"]:
                    updated += 1
                else:
                    unchanged += 1
            except (ShipdaakIntegrationError, ValueError) as exc:
                failed += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"Failed to sync order {order.order_number} (id={order.id}): {exc}"
                    )
                )
            except Exception as exc:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"Unexpected error syncing order {order.order_number} (id={order.id}): {exc}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Shipdaak sync summary: scanned={scanned}, updated={updated}, "
                f"unchanged={unchanged}, failed={failed}"
            )
        )
