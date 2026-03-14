"""
Management command to create test quotations covering all vendor-commercial
and margin-validation scenarios.

Usage:
    python manage.py create_test_quotation
    python manage.py create_test_quotation --user admin

Creates three quotations:
  Q1 — Good margin (≥22%), both client + vendor filled, status: draft
  Q2 — Low margin (<22%), pending director approval, status: pending_approval
  Q3 — Low margin (<22%), already director-approved, status: draft
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


def _margin(client, vendor):
    if client == 0:
        return None
    return ((client - vendor) / client) * 100


class Command(BaseCommand):
    help = 'Create 3 test quotations covering all vendor-commercial + margin scenarios'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            default=None,
            help='Username to assign as created_by (defaults to first admin user)',
        )

    def handle(self, *args, **options):
        from projects.models_quotation import Quotation, QuotationLocation, QuotationItem, QuotationProduct
        from projects.services.quotation_audit import QuotationAuditService

        # ------------------------------------------------------------------ #
        # Resolve creator user                                                #
        # ------------------------------------------------------------------ #
        username = options.get('user')
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"User '{username}' not found."))
                return
        else:
            user = (
                User.objects.filter(role='admin').first()
                or User.objects.filter(is_superuser=True).first()
                or User.objects.first()
            )

        if not user:
            self.stderr.write(self.style.ERROR(
                "No users found. Run 'python manage.py create_roles' first."
            ))
            return

        # Try to find a director for the approval scenario
        director = (
            User.objects.filter(role='director').first()
            or User.objects.filter(is_superuser=True).first()
            or user
        )

        self.stdout.write(f"Creating test quotations as: {user.username} ({user.role})")
        self.stdout.write(f"Director approver:          {director.username} ({director.role})")
        self.stdout.write('')

        # ================================================================== #
        # SCENARIO 1 — Good margin (≥22%), draft                             #
        # Client total: ₹7,60,000  Vendor total: ₹5,70,000  Margin: 25%     #
        # ================================================================== #
        self._create_good_margin_quotation(user, QuotationLocation, QuotationItem, QuotationProduct, QuotationAuditService)

        # ================================================================== #
        # SCENARIO 2 — Low margin (<22%), pending director approval           #
        # Client total: ₹2,25,000  Vendor total: ₹2,02,500  Margin: 10%     #
        # ================================================================== #
        self._create_pending_approval_quotation(user, QuotationLocation, QuotationItem, QuotationProduct, QuotationAuditService)

        # ================================================================== #
        # SCENARIO 3 — Low margin (<22%), already director-approved           #
        # Client total: ₹1,50,000  Vendor total: ₹1,32,000  Margin: 12%     #
        # ================================================================== #
        self._create_director_approved_quotation(user, director, QuotationLocation, QuotationItem, QuotationProduct, QuotationAuditService)

    # ---------------------------------------------------------------------- #
    # SCENARIO 1 HELPERS                                                      #
    # ---------------------------------------------------------------------- #
    def _create_good_margin_quotation(self, user, QuotationLocation, QuotationItem, QuotationProduct, QuotationAuditService):
        from projects.models_quotation import Quotation

        self.stdout.write(self.style.HTTP_INFO('─' * 60))
        self.stdout.write(self.style.HTTP_INFO('Scenario 1 — Good Margin (≥22%), Status: Draft'))
        self.stdout.write(self.style.HTTP_INFO('─' * 60))

        q = Quotation(
            client_name='Priya Sharma',
            client_company='FreshMart Distribution Pvt. Ltd.',
            client_email='priya.sharma@freshmart.com',
            client_phone='+91 98100 11111',
            billing_address='Unit 5, Bhiwandi Logistics Park, Thane - 421302',
            shipping_address='Same as billing',
            client_gst_number='27AABCF5678G1Z2',
            validity_period=30,
            point_of_contact='Annand Aryamane',
            poc_phone='9820504595',
            operational_total_boxes=Decimal('10000'),
            operational_variance_pct=Decimal('30.00'),
            company_tagline='Comprehensive Warehousing & Logistics Services',
            for_godamwale_signatory=f'{user.get_full_name() or user.username}',
            status='draft',
            created_by=user,
        )
        q.save()
        self.stdout.write(f"  Quotation number: {q.quotation_number}")

        # Mumbai location — 5 items, all with vendor costs, margin ~25%
        loc = QuotationLocation.objects.create(
            quotation=q, location_name='Bhiwandi (Main DC)', order=0
        )
        QuotationItem.objects.bulk_create([
            QuotationItem(
                location=loc, item_description='storage_per_pallet',
                unit_cost='1200', quantity='500', storage_unit_type='pallet',
                vendor_unit_cost='900', vendor_quantity='500',   # margin 25%
                order=0,
            ),
            QuotationItem(
                location=loc, item_description='inbound_handling',
                unit_cost='8', quantity='10000', storage_unit_type='unit',
                vendor_unit_cost='6', vendor_quantity='10000',   # margin 25%
                order=1,
            ),
            QuotationItem(
                location=loc, item_description='outbound_handling',
                unit_cost='10', quantity='8000', storage_unit_type='unit',
                vendor_unit_cost='7.5', vendor_quantity='8000',  # margin 25%
                order=2,
            ),
            QuotationItem(
                location=loc, item_description='pick_pack',
                unit_cost='15', quantity='5000',
                vendor_unit_cost='11', vendor_quantity='5000',   # margin 26.7%
                order=3,
            ),
            QuotationItem(
                location=loc, item_description='transport',
                unit_cost='at actual', quantity='as applicable',
                vendor_unit_cost='at actual', vendor_quantity='as applicable',  # non-numeric
                order=4,
            ),
        ])
        self.stdout.write(f"  Location: {loc.location_name} — 5 items (1 at actual)")

        # Product SKU rows
        QuotationProduct.objects.create(
            quotation=q, product_name='FMCG Cartons', type_of_business='B2B',
            type_of_operation='box_in_box_out', packaging_type='Carton',
            avg_weight_kg=Decimal('12.5'),
            dim_l=Decimal('45'), dim_w=Decimal('30'), dim_h=Decimal('25'), dim_unit='CM',
            share_pct=Decimal('60.00'), order=0,
        )
        QuotationProduct.objects.create(
            quotation=q, product_name='Pharma Units', type_of_business='B2B',
            type_of_operation='box_in_piece_out', packaging_type='Polybag',
            avg_weight_kg=Decimal('2.0'),
            dim_l=Decimal('20'), dim_w=Decimal('15'), dim_h=Decimal('10'), dim_unit='CM',
            share_pct=Decimal('40.00'), order=1,
        )
        self.stdout.write(f"  Products: 2 SKUs (FMCG 60%, Pharma 40%)")

        QuotationAuditService.log_action(
            quotation=q, user=user, action='created',
            metadata={'source': 'create_test_quotation', 'scenario': '1_good_margin'}
        )

        client_sub = q.subtotal
        vendor_sub = q.vendor_subtotal
        margin = _margin(client_sub, vendor_sub)
        billable = q.billable_storage_area_sqft
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('  ✓ Created successfully'))
        self.stdout.write(f"  Client subtotal: ₹{client_sub:,.2f}")
        self.stdout.write(f"  Vendor subtotal: ₹{vendor_sub:,.2f}")
        self.stdout.write(f"  Margin:          {margin:.1f}%  ← above 22% ✓")
        self.stdout.write(f"  Billable Area:   {int(billable):,} sq.ft" if billable else "  Billable Area:   —")
        self.stdout.write(f"  Status:          {q.status}")
        self.stdout.write(f"  View at: /projects/quotations/{q.quotation_id}/")
        self.stdout.write('')

    # ---------------------------------------------------------------------- #
    # SCENARIO 2 HELPERS                                                      #
    # ---------------------------------------------------------------------- #
    def _create_pending_approval_quotation(self, user, QuotationLocation, QuotationItem, QuotationProduct, QuotationAuditService):
        from projects.models_quotation import Quotation

        self.stdout.write(self.style.HTTP_INFO('─' * 60))
        self.stdout.write(self.style.HTTP_INFO('Scenario 2 — Low Margin (<22%), Pending Director Approval'))
        self.stdout.write(self.style.HTTP_INFO('─' * 60))

        q = Quotation(
            client_name='Suresh Mehta',
            client_company='QuickMove Freight Services',
            client_email='suresh.mehta@quickmove.in',
            client_phone='+91 98200 22222',
            billing_address='Plot 88, Taloja MIDC, Navi Mumbai - 410208',
            client_gst_number='27AABCQ9999H1Z5',
            validity_period=30,
            point_of_contact='Annand Aryamane',
            poc_phone='9820504595',
            company_tagline='Comprehensive Warehousing & Logistics Services',
            for_godamwale_signatory=f'{user.get_full_name() or user.username}',
            # Low margin — director approval requested
            status='pending_approval',
            margin_override_requested=True,
            created_by=user,
        )
        q.save()
        self.stdout.write(f"  Quotation number: {q.quotation_number}")

        # Items with squeezed margin ~10%
        loc = QuotationLocation.objects.create(
            quotation=q, location_name='Navi Mumbai (Taloja)', order=0
        )
        QuotationItem.objects.bulk_create([
            QuotationItem(
                location=loc, item_description='storage_per_pallet',
                unit_cost='800', quantity='200', storage_unit_type='pallet',
                vendor_unit_cost='730', vendor_quantity='200',   # margin 8.75%
                order=0,
            ),
            QuotationItem(
                location=loc, item_description='inbound_handling',
                unit_cost='5', quantity='5000', storage_unit_type='unit',
                vendor_unit_cost='4.5', vendor_quantity='5000',  # margin 10%
                order=1,
            ),
            QuotationItem(
                location=loc, item_description='outbound_handling',
                unit_cost='6', quantity='5000', storage_unit_type='unit',
                vendor_unit_cost='5.4', vendor_quantity='5000',  # margin 10%
                order=2,
            ),
            QuotationItem(
                location=loc, item_description='pick_pack',
                unit_cost='10', quantity='2000',
                vendor_unit_cost='9', vendor_quantity='2000',    # margin 10%
                order=3,
            ),
            QuotationItem(
                location=loc, item_description='transport',
                unit_cost='at actual', quantity='as applicable',
                vendor_unit_cost='at actual', vendor_quantity='as applicable',
                order=4,
            ),
        ])
        self.stdout.write(f"  Location: {loc.location_name} — 5 items (1 at actual)")

        QuotationProduct.objects.create(
            quotation=q, product_name='Freight Goods', type_of_business='B2B',
            type_of_operation='pallet_in_box_out', packaging_type='Pallet',
            dim_l=Decimal('100'), dim_w=Decimal('80'), dim_h=Decimal('120'), dim_unit='CM',
            share_pct=Decimal('100.00'), order=0,
        )
        q.operational_total_boxes = Decimal('5000')
        q.save(update_fields=['operational_total_boxes'])

        QuotationAuditService.log_action(
            quotation=q, user=user, action='created',
            metadata={'source': 'create_test_quotation', 'scenario': '2_pending_approval',
                      'margin_pct': '10.0'}
        )

        client_sub = q.subtotal
        vendor_sub = q.vendor_subtotal
        margin = _margin(client_sub, vendor_sub)
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('  ⚠ Created with low margin — pending approval'))
        self.stdout.write(f"  Client subtotal: ₹{client_sub:,.2f}")
        self.stdout.write(f"  Vendor subtotal: ₹{vendor_sub:,.2f}")
        self.stdout.write(f"  Margin:          {margin:.1f}%  ← below 22% — awaiting director ✗")
        self.stdout.write(f"  Status:          {q.status}")
        self.stdout.write(f"  Send email:      BLOCKED until director approves")
        self.stdout.write(f"  View at: /projects/quotations/{q.quotation_id}/")
        self.stdout.write('')

    # ---------------------------------------------------------------------- #
    # SCENARIO 3 HELPERS                                                      #
    # ---------------------------------------------------------------------- #
    def _create_director_approved_quotation(self, user, director, QuotationLocation, QuotationItem, QuotationProduct, QuotationAuditService):
        from projects.models_quotation import Quotation

        self.stdout.write(self.style.HTTP_INFO('─' * 60))
        self.stdout.write(self.style.HTTP_INFO('Scenario 3 — Low Margin (<22%), Director Approved'))
        self.stdout.write(self.style.HTTP_INFO('─' * 60))

        approved_at = timezone.now()
        q = Quotation(
            client_name='Kavita Joshi',
            client_company='MegaStore Retail Chain',
            client_email='kavita.joshi@megastore.in',
            client_phone='+91 98300 33333',
            billing_address='Survey 44, Chakan Industrial Area, Pune - 410501',
            client_gst_number='27AABCM3456K1Z8',
            validity_period=45,
            point_of_contact='Annand Aryamane',
            poc_phone='9820504595',
            company_tagline='Comprehensive Warehousing & Logistics Services',
            for_godamwale_signatory=f'{user.get_full_name() or user.username}',
            # Low margin — but director has approved the exception
            status='draft',
            margin_override_requested=True,
            margin_override_approved=True,
            margin_override_approved_by=director,
            margin_override_approved_at=approved_at,
            created_by=user,
        )
        q.save()
        self.stdout.write(f"  Quotation number: {q.quotation_number}")

        # Items — margin ~12%
        loc = QuotationLocation.objects.create(
            quotation=q, location_name='Pune (Chakan)', order=0
        )
        QuotationItem.objects.bulk_create([
            QuotationItem(
                location=loc, item_description='storage_per_pallet',
                unit_cost='1000', quantity='150', storage_unit_type='pallet',
                vendor_unit_cost='890', vendor_quantity='150',   # margin 11%
                order=0,
            ),
            QuotationItem(
                location=loc, item_description='inbound_handling',
                unit_cost='6', quantity='4000', storage_unit_type='unit',
                vendor_unit_cost='5.3', vendor_quantity='4000',  # margin 11.7%
                order=1,
            ),
            QuotationItem(
                location=loc, item_description='outbound_handling',
                unit_cost='7', quantity='4000', storage_unit_type='unit',
                vendor_unit_cost='6.1', vendor_quantity='4000',  # margin 12.9%
                order=2,
            ),
            QuotationItem(
                location=loc, item_description='wms_access',
                unit_cost='40', quantity='150', storage_unit_type='pallet',
                vendor_unit_cost='35', vendor_quantity='150',    # margin 12.5%
                order=3,
            ),
            QuotationItem(
                location=loc, item_description='transport',
                unit_cost='at actual', quantity='as applicable',
                vendor_unit_cost='at actual', vendor_quantity='as applicable',
                order=4,
            ),
        ])
        self.stdout.write(f"  Location: {loc.location_name} — 5 items (1 at actual)")

        QuotationProduct.objects.create(
            quotation=q, product_name='Retail Apparel', type_of_business='B2C',
            type_of_operation='box_in_piece_out', packaging_type='Polybag',
            dim_l=Decimal('50'), dim_w=Decimal('40'), dim_h=Decimal('30'), dim_unit='CM',
            share_pct=Decimal('100.00'), order=0,
        )
        q.operational_total_boxes = Decimal('7500')
        q.save(update_fields=['operational_total_boxes'])

        QuotationAuditService.log_action(
            quotation=q, user=user, action='created',
            metadata={'source': 'create_test_quotation', 'scenario': '3_director_approved',
                      'margin_pct': '12.0'}
        )
        QuotationAuditService.log_action(
            quotation=q, user=director, action='status_changed',
            changes={'from': 'pending_approval', 'to': 'draft',
                     'reason': 'director margin approval (test data)'},
        )

        client_sub = q.subtotal
        vendor_sub = q.vendor_subtotal
        margin = _margin(client_sub, vendor_sub)
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('  ✓ Created and director-approved'))
        self.stdout.write(f"  Client subtotal: ₹{client_sub:,.2f}")
        self.stdout.write(f"  Vendor subtotal: ₹{vendor_sub:,.2f}")
        self.stdout.write(f"  Margin:          {margin:.1f}%  ← below 22%, but approved by director ✓")
        self.stdout.write(f"  Approved by:     {director.get_full_name() or director.username}")
        self.stdout.write(f"  Approved at:     {approved_at.strftime('%d %b %Y %H:%M')}")
        self.stdout.write(f"  Status:          {q.status}  ← can now be sent to client")
        self.stdout.write(f"  View at: /projects/quotations/{q.quotation_id}/")
        self.stdout.write('')
