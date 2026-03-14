# Quotation Module Overhaul — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Overhaul the quotation module with separated cost/client pricing tables, new status workflow, versioning, expiry alerts, cloning, client acceptance links, and a win/loss dashboard.

**Architecture:** Keep the existing `QuotationItem` model fields (`vendor_unit_cost/vendor_quantity` = cost side, `unit_cost/quantity` = client side). Add 2 fields to `Quotation`, 2 new models (`QuotationRevision`, `QuotationAcceptanceToken`), 2 new statuses (`voided`, `expired`), 7 new views, and a fully redesigned frontend form with dual cost+client tables and live markup calculation.

**Tech Stack:** Django 4.x, PostgreSQL, Tailwind CSS, vanilla JS (no new libraries), python-docx (existing), Gmail API (existing).

**Reference repo JS patterns (MUST preserve):**
- `gw-systems/Quotation-Generator` — auto-populate 8 items per location, triplet logic (rate+qty+total any two derive third), storage_unit_type dropdown only for `storage_charges`, template-clone pattern, `updateItemManagementForm` on every add/remove.

---

## Phase 1: Models + Migration

### Task 1: Add fields to `Quotation`, add new models, update STATUS_CHOICES

**Files:**
- Modify: `projects/models_quotation.py`
- Create: `projects/migrations/0040_quotation_overhaul.py` (auto-generated, run makemigrations)

**Step 1: Add `commercial_type`, `default_markup_pct`, `expiry_notified` fields to `Quotation` model**

In `projects/models_quotation.py`, after the `status` field (line ~85), add:

```python
COMMERCIAL_TYPE_CHOICES = [
    ('vendor', 'Vendor Commercial'),
    ('market_rate', 'Market Rate'),
]
commercial_type = models.CharField(
    max_length=20,
    choices=COMMERCIAL_TYPE_CHOICES,
    default='vendor',
    help_text='Type of cost input used for this quotation'
)
default_markup_pct = models.DecimalField(
    max_digits=5,
    decimal_places=2,
    default=Decimal('26.00'),
    help_text='Default markup % applied to cost to derive client price'
)
expiry_notified = models.BooleanField(
    default=False,
    help_text='True once expiry management command has processed this quotation'
)
```

**Step 2: Add `voided` and `expired` to `STATUS_CHOICES` on `Quotation`**

Replace the existing `STATUS_CHOICES` list:

```python
STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('pending_approval', 'Pending Approval'),
    ('sent', 'Sent'),
    ('accepted', 'Accepted'),
    ('rejected', 'Rejected'),
    ('voided', 'Voided'),
    ('expired', 'Expired'),
]
```

**Step 3: Update `margin_pct` property to use markup formula**

Replace the existing `margin_pct` property on `Quotation`:

```python
@property
def margin_pct(self):
    """Gross markup percentage: (client - cost) / cost * 100.
    Returns None if cost subtotal is zero (markup undefined)."""
    client = self.subtotal
    vendor = self.vendor_subtotal
    if vendor == 0:
        return None
    return ((client - vendor) / vendor) * Decimal('100')
```

**Step 4: Add `QuotationRevision` model at the bottom of `projects/models_quotation.py`**

```python
class QuotationRevision(models.Model):
    """Snapshot of quotation state before a significant edit."""
    revision_id = models.AutoField(primary_key=True)
    quotation = models.ForeignKey(
        'Quotation',
        on_delete=models.CASCADE,
        related_name='revisions'
    )
    revision_number = models.IntegerField()
    snapshot = models.JSONField(
        help_text='Full snapshot: quotation fields + all locations/items at time of revision'
    )
    reason = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'quotation_revision'
        unique_together = [['quotation', 'revision_number']]
        ordering = ['-revision_number']

    def __str__(self):
        return f"{self.quotation.quotation_number} Rev {self.revision_number}"
```

**Step 5: Add `QuotationAcceptanceToken` model**

```python
import uuid as _uuid

class QuotationAcceptanceToken(models.Model):
    """Secure token for client to accept/reject quotation without login."""
    token_id = models.AutoField(primary_key=True)
    quotation = models.OneToOneField(
        'Quotation',
        on_delete=models.CASCADE,
        related_name='acceptance_token'
    )
    token = models.UUIDField(default=_uuid.uuid4, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    accepted = models.BooleanField(null=True, blank=True)  # None=pending, True=accepted, False=rejected
    client_remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'quotation_acceptance_token'

    def __str__(self):
        return f"{self.quotation.quotation_number} — token {self.token}"

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    @property
    def is_used(self):
        return self.used_at is not None
```

**Step 6: Add `QuotationAudit` action choices for new actions**

In `QuotationAudit.ACTION_CHOICES`, add:
```python
('cloned', 'Cloned'),
('expired', 'Expired'),
('acceptance_link_sent', 'Acceptance Link Sent'),
('client_responded', 'Client Responded'),
```

**Step 7: Run migrations**

```bash
cd /Users/apple/Documents/DataScienceProjects/ERP
source venv/bin/activate
python manage.py makemigrations projects --name quotation_overhaul
python manage.py migrate
```

Expected: migration `0040_quotation_overhaul.py` created and applied cleanly.

---

## Phase 2: Backend — Views, URLs, Management Command

### Task 2: Update margin logic constants and `_compute_margin_from_post`

**Files:**
- Modify: `projects/views_quotation.py`

**Step 1: Replace constants at top of views file**

Find lines:
```python
# Minimum margin percentage required to save/send a quotation without director approval.
MINIMUM_MARGIN_PCT = Decimal('22.00')
```

Replace with:
```python
# Markup thresholds (markup = (client - cost) / cost * 100)
MINIMUM_MARKUP_PCT = Decimal('26.00')   # below this → pending_approval
AUTO_REJECT_MARKUP_PCT = Decimal('15.00')  # below this → hard block, no director review
```

**Step 2: Update `_compute_margin_from_post` to use markup formula**

Replace the function body's margin calculation line:

Old:
```python
margin_pct = None
if client_total > 0:
    margin_pct = ((client_total - vendor_total) / client_total) * Decimal('100')
```

New:
```python
markup_pct = None
if vendor_total > 0:
    markup_pct = ((client_total - vendor_total) / vendor_total) * Decimal('100')
```

Return signature change — return `markup_pct` instead of `margin_pct`:
```python
return client_total, vendor_total, markup_pct
```

**Step 3: Update `quotation_create` margin enforcement block**

Find the block starting `if all_valid:` and replace margin enforcement:

```python
client_total, vendor_total, markup_pct = _compute_margin_from_post(request)
requesting_approval = request.POST.get('_request_approval') == '1'

# Hard block: below 15% — don't bother directors
if markup_pct is not None and markup_pct < AUTO_REJECT_MARKUP_PCT:
    messages.error(
        request,
        f"Markup is {markup_pct:.1f}%, which is below the minimum 15%. "
        "This quotation cannot be saved. Please increase client pricing."
    )
    existing_items_json = _build_items_json_from_post(request)
    context = {
        'form': form,
        'location_formset': location_formset,
        'product_formset': product_formset,
        'item_choices': QuotationItem.ITEM_DESCRIPTION_CHOICES,
        'storage_unit_choices': QuotationItem.STORAGE_UNIT_CHOICES,
        'existing_items_json': existing_items_json,
        'existing_products_json': _build_products_json_from_post(request),
        'title': 'Create Quotation',
        'markup_pct': float(markup_pct),
        'min_markup_pct': float(MINIMUM_MARKUP_PCT),
        'auto_reject_pct': float(AUTO_REJECT_MARKUP_PCT),
        **_product_context(),
    }
    return render(request, 'projects/quotations/quotation_create.html', context)

quotation = form.save(commit=False)
quotation.created_by = request.user

# Auto-route to pending_approval if 15% ≤ markup < 26%
if markup_pct is not None and markup_pct < MINIMUM_MARKUP_PCT:
    quotation.status = 'pending_approval'
    quotation.margin_override_requested = True
```

Apply the same pattern in `quotation_edit` (same block, same replacement).

**Step 4: Update audit metadata to use `markup_pct`**

In both `quotation_create` and `quotation_edit`, update the `QuotationAuditService.log_action` metadata key:
```python
metadata={'markup_pct': str(markup_pct) if markup_pct is not None else None}
```

**Step 5: Update `quotation_approve_margin` message to reference 26% not 22%**

Find:
```python
"The creator must revise pricing to achieve ≥22% margin."
```
Replace with:
```python
"The creator must revise pricing to achieve ≥26% markup."
```

### Task 3: Add `quotation_transition` view

**Files:**
- Modify: `projects/views_quotation.py` (add after `quotation_approve_margin`)

**Step 1: Add the view**

```python
@login_required
def quotation_transition(request, quotation_id):
    """
    Handle status transitions from detail page action buttons.
    Transitions:
      sent → accepted       (any staff)
      sent → rejected       (any staff)
      accepted → draft      (director/admin only)
      rejected → draft      (director/admin only)
      draft → voided        (director/admin only)
    """
    if request.method != 'POST':
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)
    action = request.POST.get('action', '').strip()

    is_director = (
        request.user.is_superuser
        or (hasattr(request.user, 'role') and request.user.role in ('director', 'admin'))
    )

    ALLOWED_TRANSITIONS = {
        'mark_accepted': ('sent', 'accepted', False),    # (from, to, director_only)
        'mark_rejected': ('sent', 'rejected', False),
        'reopen_draft':  (('accepted', 'rejected'), 'draft', True),
        'void':          ('draft', 'voided', True),
    }

    if action not in ALLOWED_TRANSITIONS:
        messages.error(request, "Invalid action.")
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    from_status, to_status, director_only = ALLOWED_TRANSITIONS[action]

    # Director check
    if director_only and not is_director:
        messages.error(request, "Only directors can perform this action.")
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    # Status check
    valid_from = from_status if isinstance(from_status, tuple) else (from_status,)
    if quotation.status not in valid_from:
        messages.error(request, f"Cannot perform '{action}' from status '{quotation.get_status_display()}'.")
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    old_status = quotation.status
    quotation.status = to_status
    quotation.save(update_fields=['status', 'updated_at'])

    QuotationAuditService.log_action(
        quotation=quotation,
        user=request.user,
        action='status_changed',
        changes={'from': old_status, 'to': to_status, 'action': action},
        ip_address=QuotationAuditService.get_client_ip(request),
    )

    STATUS_MESSAGES = {
        'mark_accepted': f"{quotation.quotation_number} marked as Accepted.",
        'mark_rejected': f"{quotation.quotation_number} marked as Rejected.",
        'reopen_draft': f"{quotation.quotation_number} reopened as Draft.",
        'void': f"{quotation.quotation_number} has been voided.",
    }
    messages.success(request, STATUS_MESSAGES[action])
    return redirect('projects:quotation_detail', quotation_id=quotation_id)
```

### Task 4: Add `quotation_clone` view

**Files:**
- Modify: `projects/views_quotation.py`

**Step 1: Add the view after `quotation_transition`**

```python
@login_required
@transaction.atomic
def quotation_clone(request, quotation_id):
    """
    Clone a quotation: new quotation number, all locations/items/products copied, status=draft.
    Redirects to edit page of the new clone.
    """
    if request.method != 'POST':
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    original = get_object_or_404(
        Quotation.objects.prefetch_related('locations__items', 'products'),
        quotation_id=quotation_id
    )

    # Clone the quotation header
    new_q = Quotation(
        client_name=original.client_name,
        client_company=original.client_company,
        client_email=original.client_email,
        client_phone=original.client_phone,
        billing_address=original.billing_address,
        shipping_address=original.shipping_address,
        client_gst_number=original.client_gst_number,
        point_of_contact=original.point_of_contact,
        poc_phone=original.poc_phone,
        validity_period=original.validity_period,
        gst_rate=original.gst_rate,
        status='draft',
        commercial_type=original.commercial_type,
        default_markup_pct=original.default_markup_pct,
        payment_terms=original.payment_terms,
        sla_terms=original.sla_terms,
        contract_terms=original.contract_terms,
        liability_terms=original.liability_terms,
        company_tagline=original.company_tagline,
        for_godamwale_signatory=original.for_godamwale_signatory,
        operational_total_boxes=original.operational_total_boxes,
        operational_variance_pct=original.operational_variance_pct,
        operational_pallet_l=original.operational_pallet_l,
        operational_pallet_w=original.operational_pallet_w,
        operational_pallet_h=original.operational_pallet_h,
        created_by=request.user,
    )
    new_q.save()  # triggers auto quotation_number generation

    # Clone locations and items
    for loc in original.locations.all():
        new_loc = QuotationLocation(
            quotation=new_q,
            location_name=loc.location_name,
            order=loc.order,
        )
        new_loc.save()
        for item in loc.items.all():
            QuotationItem(
                location=new_loc,
                item_description=item.item_description,
                custom_description=item.custom_description,
                unit_cost=item.unit_cost,
                quantity=item.quantity,
                vendor_unit_cost=item.vendor_unit_cost,
                vendor_quantity=item.vendor_quantity,
                storage_unit_type=item.storage_unit_type,
                order=item.order,
            ).save()

    # Clone products
    for prod in original.products.all():
        QuotationProduct(
            quotation=new_q,
            product_name=prod.product_name,
            type_of_business=prod.type_of_business,
            type_of_operation=prod.type_of_operation,
            packaging_type=prod.packaging_type,
            avg_weight_kg=prod.avg_weight_kg,
            dim_l=prod.dim_l,
            dim_w=prod.dim_w,
            dim_h=prod.dim_h,
            dim_unit=prod.dim_unit,
            share_pct=prod.share_pct,
            order=prod.order,
        ).save()

    QuotationAuditService.log_action(
        quotation=new_q,
        user=request.user,
        action='cloned',
        ip_address=QuotationAuditService.get_client_ip(request),
        metadata={'cloned_from': original.quotation_number}
    )

    messages.success(
        request,
        f"Quotation cloned as {new_q.quotation_number}. You are now editing the clone."
    )
    return redirect('projects:quotation_edit', quotation_id=new_q.quotation_id)
```

### Task 5: Add versioning snapshot helper + revision logic in `quotation_edit`

**Files:**
- Modify: `projects/views_quotation.py`

**Step 1: Add `_snapshot_quotation` helper near other helpers at top of file**

```python
def _snapshot_quotation(quotation):
    """
    Serialize a quotation + all child records into a dict for revision storage.
    Called before overwriting a sent/accepted quotation.
    """
    data = {
        'quotation_id': quotation.quotation_id,
        'quotation_number': quotation.quotation_number,
        'status': quotation.status,
        'client_name': quotation.client_name,
        'client_company': quotation.client_company,
        'client_email': quotation.client_email,
        'client_phone': quotation.client_phone,
        'billing_address': quotation.billing_address,
        'gst_rate': str(quotation.gst_rate),
        'commercial_type': quotation.commercial_type,
        'default_markup_pct': str(quotation.default_markup_pct),
        'validity_period': quotation.validity_period,
        'date': quotation.date.isoformat(),
        'locations': []
    }
    for loc in quotation.locations.prefetch_related('items').all():
        loc_data = {
            'location_name': loc.location_name,
            'order': loc.order,
            'items': []
        }
        for item in loc.items.all():
            loc_data['items'].append({
                'item_description': item.item_description,
                'custom_description': item.custom_description,
                'unit_cost': item.unit_cost,
                'quantity': item.quantity,
                'vendor_unit_cost': item.vendor_unit_cost,
                'vendor_quantity': item.vendor_quantity,
                'storage_unit_type': item.storage_unit_type or '',
                'order': item.order,
            })
        data['locations'].append(loc_data)
    return data
```

**Step 2: Add revision creation in `quotation_edit` view before saving**

At the start of the `if all_valid:` block in `quotation_edit`, before computing margin, add:

```python
# Create revision snapshot if editing a sent/accepted quotation
from projects.models_quotation import QuotationRevision
needs_revision = quotation.status in ('sent', 'accepted')
if needs_revision:
    rev_num = quotation.revisions.count() + 1
    QuotationRevision.objects.create(
        quotation=quotation,
        revision_number=rev_num,
        snapshot=_snapshot_quotation(quotation),
        reason=request.POST.get('revision_reason', '').strip(),
        created_by=request.user,
    )
    # Editing a sent/accepted quote resets it to draft
    # (form.save() will handle status; force draft unless margin triggers approval)
```

After `quotation = form.save(commit=False)` and before `quotation.save()`, add:

```python
if needs_revision and quotation.status in ('sent', 'accepted'):
    quotation.status = 'draft'
```

### Task 6: Add `quotation_revision_view` view

**Files:**
- Modify: `projects/views_quotation.py`

```python
@login_required
def quotation_revision_view(request, quotation_id, revision_number):
    """Read-only view of a historical revision snapshot."""
    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)
    from projects.models_quotation import QuotationRevision
    revision = get_object_or_404(
        QuotationRevision,
        quotation=quotation,
        revision_number=revision_number
    )
    context = {
        'quotation': quotation,
        'revision': revision,
        'snapshot': revision.snapshot,
    }
    return render(request, 'projects/quotations/quotation_revision.html', context)
```

### Task 7: Add client acceptance link views

**Files:**
- Modify: `projects/views_quotation.py`

```python
@login_required
def quotation_generate_acceptance_link(request, quotation_id):
    """
    Generate (or regenerate) a client acceptance link for a sent quotation.
    Returns JSON with the link URL.
    """
    if request.method != 'POST':
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    quotation = get_object_or_404(Quotation, quotation_id=quotation_id)

    if quotation.status != 'sent':
        messages.error(request, "Acceptance links can only be generated for 'Sent' quotations.")
        return redirect('projects:quotation_detail', quotation_id=quotation_id)

    from projects.models_quotation import QuotationAcceptanceToken
    from django.utils import timezone
    import datetime

    # Delete any existing unused token
    QuotationAcceptanceToken.objects.filter(quotation=quotation, used_at__isnull=True).delete()

    expires_at = timezone.make_aware(
        datetime.datetime.combine(quotation.validity_date, datetime.time(23, 59, 59))
    )
    token_obj = QuotationAcceptanceToken.objects.create(
        quotation=quotation,
        expires_at=expires_at,
    )

    link = request.build_absolute_uri(
        f"/projects/quotations/accept/{token_obj.token}/"
    )

    QuotationAuditService.log_action(
        quotation=quotation,
        user=request.user,
        action='acceptance_link_sent',
        ip_address=QuotationAuditService.get_client_ip(request),
        metadata={'link': link}
    )

    messages.success(request, f"Acceptance link generated. Copy it below.")
    # Store link in session to show on detail page after redirect
    request.session[f'acceptance_link_{quotation_id}'] = link
    return redirect('projects:quotation_detail', quotation_id=quotation_id)


def quotation_accept_public(request, token):
    """
    Public (no login required) client-facing page to accept or reject a quotation.
    """
    from projects.models_quotation import QuotationAcceptanceToken
    from django.utils import timezone

    token_obj = get_object_or_404(QuotationAcceptanceToken, token=token)
    quotation = token_obj.quotation

    if token_obj.is_used:
        return render(request, 'projects/quotations/quotation_accept_public.html', {
            'already_responded': True,
            'accepted': token_obj.accepted,
            'quotation': quotation,
        })

    if token_obj.is_expired:
        return render(request, 'projects/quotations/quotation_accept_public.html', {
            'expired': True,
            'quotation': quotation,
        })

    if request.method == 'POST':
        action = request.POST.get('action')
        remarks = request.POST.get('remarks', '').strip()

        if action not in ('accept', 'reject'):
            return render(request, 'projects/quotations/quotation_accept_public.html', {
                'quotation': quotation,
                'token': token_obj,
                'error': 'Invalid action. Please click Accept or Reject.',
            })

        token_obj.accepted = (action == 'accept')
        token_obj.client_remarks = remarks
        token_obj.used_at = timezone.now()
        token_obj.save()

        new_status = 'accepted' if action == 'accept' else 'rejected'
        old_status = quotation.status
        quotation.status = new_status
        quotation.save(update_fields=['status', 'updated_at'])

        QuotationAuditService.log_action(
            quotation=quotation,
            user=None,
            action='client_responded',
            changes={'from': old_status, 'to': new_status},
            metadata={'via': 'client_link', 'remarks': remarks}
        )

        return render(request, 'projects/quotations/quotation_accept_public.html', {
            'thank_you': True,
            'accepted': token_obj.accepted,
            'quotation': quotation,
        })

    # GET
    return render(request, 'projects/quotations/quotation_accept_public.html', {
        'quotation': quotation,
        'token': token_obj,
        'locations': quotation.locations.prefetch_related('items').all(),
    })
```

### Task 8: Add win/loss dashboard view

**Files:**
- Modify: `projects/views_quotation.py`

```python
@login_required
def quotation_dashboard(request):
    """Win/loss analytics dashboard. Director/admin only."""
    is_director = (
        request.user.is_superuser
        or (hasattr(request.user, 'role') and request.user.role in ('director', 'admin'))
    )
    if not is_director:
        messages.error(request, "Dashboard is restricted to directors and admins.")
        return redirect('projects:quotation_list')

    from django.db.models import Count, Sum, Q
    from django.utils import timezone
    import datetime

    today = timezone.now().date()
    month_start = today.replace(day=1)
    week_end = today + datetime.timedelta(days=7)

    qs = Quotation.objects.all()

    # This month stats
    monthly = qs.filter(date__gte=month_start)
    monthly_sent = monthly.filter(status__in=['sent', 'accepted', 'rejected', 'expired']).count()
    monthly_won = monthly.filter(status='accepted').count()
    monthly_lost = monthly.filter(status='rejected').count()

    # Pending actions
    pending_approval_count = qs.filter(status='pending_approval').count()
    expiring_soon_count = qs.filter(
        status='sent',
        date__lte=today - datetime.timedelta(days=1)
    ).extra(
        where=["date + validity_period * INTERVAL '1 day' <= %s"],
        params=[str(today + datetime.timedelta(days=7))]
    ).count()

    from projects.models_quotation import QuotationAcceptanceToken
    sent_with_token_ids = QuotationAcceptanceToken.objects.values_list('quotation_id', flat=True)
    awaiting_response = qs.filter(status='sent').exclude(quotation_id__in=sent_with_token_ids).count()

    # Top clients by accepted value (client subtotal is a property, not DB field — use annotation workaround)
    # We sum item totals using annotation; only include calculated (numeric) items
    # Simpler: just list top accepted quotations
    top_accepted = (
        qs.filter(status='accepted')
        .select_related('created_by')
        .prefetch_related('locations__items')
        .order_by('-created_at')[:10]
    )

    context = {
        'monthly_sent': monthly_sent,
        'monthly_won': monthly_won,
        'monthly_lost': monthly_lost,
        'win_rate': round((monthly_won / monthly_sent * 100) if monthly_sent else 0, 1),
        'pending_approval_count': pending_approval_count,
        'expiring_soon_count': expiring_soon_count,
        'awaiting_response': awaiting_response,
        'top_accepted': top_accepted,
        'today': today,
        'month_start': month_start,
    }
    return render(request, 'projects/quotations/quotation_dashboard.html', context)
```

### Task 9: Add management command for expiry

**Files:**
- Create: `projects/management/commands/check_quotation_expiry.py`

```python
from django.core.management.base import BaseCommand
from django.utils import timezone
from projects.models_quotation import Quotation
from projects.services.quotation_audit import QuotationAuditService


class Command(BaseCommand):
    help = 'Mark sent quotations as expired when validity_date has passed.'

    def handle(self, *args, **options):
        today = timezone.now().date()
        expired_qs = Quotation.objects.filter(
            status='sent',
            expiry_notified=False,
        )

        count = 0
        for q in expired_qs:
            if q.validity_date < today:
                q.status = 'expired'
                q.expiry_notified = True
                q.save(update_fields=['status', 'expiry_notified', 'updated_at'])
                QuotationAuditService.log_action(
                    quotation=q,
                    user=None,
                    action='expired',
                    changes={'from': 'sent', 'to': 'expired'},
                    metadata={'expired_on': today.isoformat()}
                )
                count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Marked {count} quotation(s) as expired.')
        )
```

**Step 2: Verify command runs**

```bash
python manage.py check_quotation_expiry
```

Expected output: `Marked 0 quotation(s) as expired.` (or N if any are genuinely expired).

### Task 10: Register all new URLs

**Files:**
- Modify: `projects/urls.py`

**Step 1: Add imports at top of urls.py** (if not already present)

Verify `views_quotation` is imported. It should be — check existing import lines.

**Step 2: Replace the quotations URL block (lines ~140–154)**

```python
# Quotations
path('quotations/', views_quotation.quotation_list, name='quotation_list'),
path('quotations/create/', views_quotation.quotation_create, name='quotation_create'),
path('quotations/settings/', views_quotation.quotation_settings, name='quotation_settings'),
path('quotations/dashboard/', views_quotation.quotation_dashboard, name='quotation_dashboard'),
path('quotations/accept/<uuid:token>/', views_quotation.quotation_accept_public, name='quotation_accept_public'),
path('quotations/<int:quotation_id>/', views_quotation.quotation_detail, name='quotation_detail'),
path('quotations/<int:quotation_id>/edit/', views_quotation.quotation_edit, name='quotation_edit'),
path('quotations/<int:quotation_id>/download-docx/', views_quotation.download_docx, name='quotation_download_docx'),
path('quotations/<int:quotation_id>/download-pdf/', views_quotation.download_pdf, name='quotation_download_pdf'),
path('quotations/<int:quotation_id>/send-email/', views_quotation.send_email, name='quotation_send_email'),
path('quotations/<int:quotation_id>/approve-margin/', views_quotation.quotation_approve_margin, name='quotation_approve_margin'),
path('quotations/<int:quotation_id>/transition/', views_quotation.quotation_transition, name='quotation_transition'),
path('quotations/<int:quotation_id>/clone/', views_quotation.quotation_clone, name='quotation_clone'),
path('quotations/<int:quotation_id>/acceptance-link/', views_quotation.quotation_generate_acceptance_link, name='quotation_acceptance_link'),
path('quotations/<int:quotation_id>/revisions/<int:revision_number>/', views_quotation.quotation_revision_view, name='quotation_revision_view'),
```

**Step 3: Verify Django can find URLs**

```bash
python manage.py show_urls | grep quotation
```

Expected: all 15 quotation URL names listed.

---

## Phase 3: Forms Update

### Task 11: Add `commercial_type` and `default_markup_pct` to `QuotationForm`

**Files:**
- Modify: `projects/forms_quotation.py`

**Step 1: Add fields to `QuotationForm.Meta.fields`**

After `'status'`, add:
```python
'commercial_type',
'default_markup_pct',
```

**Step 2: Add widgets for new fields**

```python
'commercial_type': forms.RadioSelect(attrs={
    'class': 'sr-only'  # Hidden — styled by JS toggle buttons in template
}),
'default_markup_pct': forms.NumberInput(attrs={
    'class': INPUT_CLASSES,
    'step': '0.01',
    'min': '15',
    'max': '100',
    'id': 'id_default_markup_pct',
}),
```

---

## Phase 4: Frontend — Complete Form Redesign

### Task 12: Redesign `quotation_create.html` with dual cost+client tables

**Files:**
- Modify: `templates/projects/quotations/quotation_create.html`

This is the most significant frontend task. The page must have:

1. **Quotation header section** — unchanged (client info, quotation details, T&C, operational scope)
2. **Commercial type toggle** — rendered once at form level (applies to all locations)
3. **Per-location blocks**, each containing:
   - Location name + remove button
   - **COST TABLE** — labeled "Vendor Commercial" or "Market Rate" per toggle
     - 8 pre-populated rows (same 8 item types as reference repo)
     - Columns: Service | Storage Unit (for storage only) | Rate (₹) | Qty | Total
     - Triplet logic on cost table too
   - **Markup % input** — `[26]%` — single value applies to all rows in this location
   - **CLIENT PRICING TABLE** — auto-calculated, editable
     - Columns: Service | Rate (₹) | Qty | Total | Markup%
     - Triplet logic on client table
     - Per-row markup % shown (read-only, auto-calculated)
   - Location summary: Subtotal + GST + Grand Total
   - Markup health badge: green/amber/red
4. **Overall markup badge** at form bottom
5. **Submit buttons**: "Save Draft" and "Request Approval" (shown conditionally)

**Step 1: Replace the Locations & Items card in the template**

The full HTML block for locations replaces what's currently inside the `<!-- Locations & Items -->` card. Key structure:

```html
<!-- Commercial Type Toggle (top-level, applies to all locations) -->
<div class="bg-white rounded-xl border border-gray-200 shadow-sm p-4 mb-6">
  <div class="flex items-center gap-4">
    <span class="text-sm font-semibold text-gray-700">Cost Input Type:</span>
    <div class="flex rounded-lg border border-gray-300 overflow-hidden">
      <button type="button" id="toggle-vendor" data-type="vendor"
        class="commercial-toggle px-4 py-2 text-sm font-medium transition-colors bg-blue-600 text-white">
        Vendor Commercial
      </button>
      <button type="button" id="toggle-market" data-type="market_rate"
        class="commercial-toggle px-4 py-2 text-sm font-medium transition-colors bg-white text-gray-700">
        Market Rate
      </button>
    </div>
    <input type="hidden" name="commercial_type" id="id_commercial_type" value="{{ form.commercial_type.value|default:'vendor' }}">
  </div>
</div>

<!-- Default Markup % -->
<div class="flex items-center gap-3 mb-4">
  <label class="text-sm font-medium text-gray-700">Default Markup %:</label>
  <input type="number" id="id_default_markup_pct" name="default_markup_pct"
    value="{{ form.default_markup_pct.value|default:'26.00' }}"
    min="15" max="200" step="0.01"
    class="w-24 px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
  <span class="text-sm text-gray-500">% (auto-applied to all cost rows → client pricing)</span>
</div>

<!-- Locations container -->
<div id="locations-container">
  {% for location_form in location_formset %}
  <div class="location-group bg-white rounded-xl border border-gray-200 shadow-sm mb-6"
       data-location-index="{{ forloop.counter0 }}">

    <!-- Location header -->
    <div class="flex items-center gap-3 p-4 border-b border-gray-100">
      <span class="font-medium text-gray-700 text-sm whitespace-nowrap">Location:</span>
      {{ location_form.location_name }}
      {{ location_form.order }}
      {{ location_form.id }}
      {{ location_form.DELETE }}
      <button type="button" class="remove-location-btn ml-auto text-red-500 hover:text-red-700 text-sm">
        Remove
      </button>
    </div>

    <!-- COST TABLE -->
    <div class="p-4">
      <div class="flex items-center justify-between mb-2">
        <h4 class="text-sm font-semibold text-gray-600 uppercase tracking-wide cost-table-label">
          Vendor Commercial
        </h4>
      </div>

      <!-- Management form for items -->
      <input type="hidden" name="locations-{{ forloop.counter0 }}-items-TOTAL_FORMS"
             id="id_locations-{{ forloop.counter0 }}-items-TOTAL_FORMS" value="0">
      <input type="hidden" name="locations-{{ forloop.counter0 }}-items-INITIAL_FORMS"
             id="id_locations-{{ forloop.counter0 }}-items-INITIAL_FORMS" value="0">
      <input type="hidden" name="locations-{{ forloop.counter0 }}-items-MIN_NUM_FORMS"
             id="id_locations-{{ forloop.counter0 }}-items-MIN_NUM_FORMS" value="0">
      <input type="hidden" name="locations-{{ forloop.counter0 }}-items-MAX_NUM_FORMS"
             id="id_locations-{{ forloop.counter0 }}-items-MAX_NUM_FORMS" value="1000">

      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-2 pr-3 text-gray-600 font-medium w-48">Service</th>
              <th class="text-left py-2 pr-3 text-gray-600 font-medium w-32 storage-unit-header">Unit</th>
              <th class="text-right py-2 pr-3 text-gray-600 font-medium w-28">Cost Rate (₹)</th>
              <th class="text-right py-2 pr-3 text-gray-600 font-medium w-24">Qty</th>
              <th class="text-right py-2 text-gray-600 font-medium w-28">Cost Total</th>
            </tr>
          </thead>
          <tbody class="items-container cost-rows" data-location-index="{{ forloop.counter0 }}">
            <!-- Hidden template row (cloned by JS) -->
            <tr class="item-row item-template" style="display:none;" data-row-index="0">
              <td class="py-1.5 pr-3">
                <div class="item-description-text text-gray-800 text-sm"></div>
                <select class="item-description-select w-full border border-gray-300 rounded px-2 py-1 text-sm" style="display:none;" disabled>
                  <option value="" disabled selected>Select type</option>
                  <option value="storage_charges">Storage Charges</option>
                  <option value="inbound_handling">Inbound Handling</option>
                  <option value="outbound_handling">Outbound Handling</option>
                  <option value="pick_pack">Pick & Pack</option>
                  <option value="packaging_material">Packaging Material</option>
                  <option value="labelling_services">Labelling Services</option>
                  <option value="wms_platform">WMS Platform Access</option>
                  <option value="value_added">Value-Added Services</option>
                  <option value="transport">Transport Services</option>
                  <option value="other">Other</option>
                </select>
                <input type="hidden" name="__prefix__-item_description" class="item-description" disabled>
              </td>
              <td class="py-1.5 pr-3">
                <select name="__prefix__-storage_unit_type" class="storage-unit-type w-full border border-gray-300 rounded px-2 py-1 text-sm" style="display:none;" disabled>
                  <option value="per_sqft">per sq.ft/month</option>
                  <option value="per_pallet" selected>per pallet/month</option>
                  <option value="per_unit">per unit/month</option>
                  <option value="per_lumpsum">lumpsum/month</option>
                  <option value="per_order">per order/month</option>
                </select>
              </td>
              <td class="py-1.5 pr-3">
                <input type="text" name="__prefix__-vendor_unit_cost" class="vendor-unit-cost w-full text-right border border-gray-300 rounded px-2 py-1 text-sm" placeholder="At actual" disabled>
              </td>
              <td class="py-1.5 pr-3">
                <input type="text" name="__prefix__-vendor_quantity" class="vendor-quantity w-full text-right border border-gray-300 rounded px-2 py-1 text-sm" placeholder="At actual" disabled>
              </td>
              <td class="py-1.5">
                <input type="text" class="vendor-total w-full text-right border border-gray-200 rounded px-2 py-1 text-sm bg-gray-50" placeholder="0.00" disabled readonly>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <button type="button" class="add-item-btn mt-2 text-sm text-blue-600 hover:text-blue-800"
              data-location-index="{{ forloop.counter0 }}">+ Add row</button>
    </div>

    <!-- CLIENT PRICING TABLE -->
    <div class="p-4 border-t border-dashed border-gray-200 bg-blue-50/30">
      <div class="flex items-center gap-3 mb-2">
        <h4 class="text-sm font-semibold text-blue-700 uppercase tracking-wide">Client Pricing</h4>
        <span class="text-xs text-gray-500">(auto-calculated from cost × markup%)</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-blue-200">
              <th class="text-left py-2 pr-3 text-blue-700 font-medium w-48">Service</th>
              <th class="text-right py-2 pr-3 text-blue-700 font-medium w-28">Client Rate (₹)</th>
              <th class="text-right py-2 pr-3 text-blue-700 font-medium w-24">Qty</th>
              <th class="text-right py-2 pr-3 text-blue-700 font-medium w-28">Client Total</th>
              <th class="text-right py-2 text-blue-700 font-medium w-20">Markup%</th>
            </tr>
          </thead>
          <tbody class="client-rows" data-location-index="{{ forloop.counter0 }}">
            <!-- Rows populated by JS mirroring cost rows -->
          </tbody>
        </table>
      </div>
    </div>

    <!-- Location footer: totals + markup badge -->
    <div class="p-4 border-t border-gray-100 flex items-center justify-between">
      <div class="markup-badge text-sm font-medium px-3 py-1 rounded-full bg-gray-100 text-gray-500"
           data-location-index="{{ forloop.counter0 }}">
        Markup: —
      </div>
      <div class="text-right text-sm">
        <div class="text-gray-500">Subtotal: <span class="location-subtotal font-semibold text-gray-800">₹0.00</span></div>
        <div class="text-gray-500">GST ({{ form.gst_rate.value|default:'18' }}%): <span class="location-gst font-semibold text-gray-800">₹0.00</span></div>
        <div class="text-blue-700 font-bold">Total: <span class="location-grand-total">₹0.00</span></div>
      </div>
    </div>
  </div>
  {% endfor %}
</div>

<button type="button" id="add-location-btn"
  class="w-full py-3 border-2 border-dashed border-gray-300 rounded-xl text-gray-500 hover:border-blue-400 hover:text-blue-600 text-sm font-medium transition-colors">
  + Add Another Location
</button>

<!-- Overall markup banner -->
<div id="overall-markup-banner" class="mt-4 p-3 rounded-lg bg-gray-50 border border-gray-200 flex items-center justify-between">
  <span class="text-sm text-gray-600">Overall Markup Across All Locations:</span>
  <span id="overall-markup-value" class="text-lg font-bold text-gray-700">—</span>
</div>
```

**Step 2: Add revision reason field (shown when editing sent/accepted quotations)**

In `quotation_edit` template (same file used for create/edit), add conditionally before submit buttons:

```html
{% if quotation and quotation.status in 'sent,accepted' %}
<div class="mt-4 p-4 bg-amber-50 border border-amber-200 rounded-xl">
  <p class="text-sm text-amber-800 font-medium mb-2">
    ⚠ You are editing a {{ quotation.get_status_display }} quotation. A revision will be saved automatically.
  </p>
  <label class="text-sm text-gray-700">Reason for revision (optional):</label>
  <input type="text" name="revision_reason" placeholder="e.g. Updated storage rate per client request"
    class="w-full mt-1 px-3 py-2 border border-amber-300 rounded-lg text-sm">
</div>
{% endif %}
```

**Step 3: Update submit buttons**

```html
<div class="flex justify-end gap-3 mt-6">
  <a href="{% url 'projects:quotation_list' %}" class="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 text-sm hover:bg-gray-50">
    Cancel
  </a>
  <button type="submit" name="_action" value="save" class="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
    Save Draft
  </button>
  <button type="submit" name="_request_approval" value="1"
    class="px-6 py-2 bg-amber-500 text-white rounded-lg text-sm font-medium hover:bg-amber-600"
    id="request-approval-btn" style="display:none;">
    Request Director Approval
  </button>
</div>
```

### Task 13: Write the new quotation JS (static file)

**Files:**
- Modify: Create/replace `projects/static/projects/js/quotation_form.js`

> **Note:** The ERP project serves static files from `projects/static/projects/`. The existing template likely uses `{% static %}` tag. Check where the current JS is included.

**Full JS — `quotation_form.js`:**

The JS must implement:

1. **`ITEM_CHOICES`** — same 8 items as reference repo + transport + other (match `QuotationItem.ITEM_DESCRIPTION_CHOICES`)

2. **`initCommercialTypeToggle()`** — toggle buttons update hidden `#id_commercial_type` and relabel cost table headers

3. **`populateAllItemsForLocation(locationIdx)`** — clones `.item-template` 10 times, sets item_description for each, mirrors client rows immediately

4. **`applyMarkupToLocation(locationIdx)`** — reads `#id_default_markup_pct`, applies `cost × (1 + markup/100)` to each client row

5. **`calculateLocationTotals(locationIdx)`** — triplet logic on both cost and client rows, updates subtotal/GST/grand total badges

6. **`calculateLocationMarkup(locationIdx)`** — overall `(clientTotal - costTotal) / costTotal * 100`, updates markup badge color

7. **`updateOverallMarkup()`** — aggregates all locations, updates `#overall-markup-banner`

8. **`addLocation()`** — clones a location group, updates prefixes, calls `populateAllItemsForLocation`

9. **`removeLocation(e)`** — marks DELETE or removes from DOM, recalculates all

10. **`updateItemManagementForm(locationIdx)`** — counts visible non-template rows, sets `TOTAL_FORMS`

Key implementation detail for client row mirroring:

```javascript
// Client rows are NOT separate DOM rows submitted independently.
// They READ from cost fields and write to unit_cost / quantity fields.
// The unit_cost and quantity inputs ARE submitted (they live in the cost row, hidden twin inputs).
// OR: client rows are visually separate but their values are written back into
// the hidden unit_cost/quantity fields inside the cost rows before form submission.

// Simpler approach: Each item row has BOTH cost fields AND client fields.
// Cost fields: vendor_unit_cost, vendor_quantity (visible in cost table)
// Client fields: unit_cost, quantity (visible in client table, same row data-row-index)
// Client table rows are a separate visual tbody, but the inputs reference the same row index.
```

**Complete JS file content:**

```javascript
/**
 * Quotation Form JS
 * Implements: dual cost+client tables, markup auto-calc, triplet logic,
 * 10 item auto-populate, location add/remove, management form updates.
 * Reference: gw-systems/Quotation-Generator quotation_form.js
 */

const ITEM_CHOICES = [
    ['storage_charges', 'Storage Charges', true],   // [value, label, has_storage_unit]
    ['inbound_handling', 'Inbound Handling', false],
    ['outbound_handling', 'Outbound Handling', false],
    ['pick_pack', 'Pick & Pack', false],
    ['packaging_material', 'Packaging Material', false],
    ['labelling_services', 'Labelling Services', false],
    ['wms_platform', 'WMS Platform Access', false],
    ['value_added', 'Value-Added Services', false],
    ['transport', 'Transport Services', false],
    ['other', 'Other', false],
];

const GST_RATE = parseFloat(document.getElementById('id_gst_rate')?.value || '18') / 100;

document.addEventListener('DOMContentLoaded', function () {
    initCommercialTypeToggle();
    initLocationHandling();
    loadExistingItems();
    recalculateAll();

    // Markup % change → re-apply to all locations
    const markupInput = document.getElementById('id_default_markup_pct');
    if (markupInput) {
        markupInput.addEventListener('input', recalculateAll);
    }

    // Form submit validation
    document.getElementById('quotation-form')?.addEventListener('submit', function (e) {
        if (!validateForm()) {
            e.preventDefault();
        }
    });
});

// ─────────────────────────────────────────────
// Commercial type toggle
// ─────────────────────────────────────────────
function initCommercialTypeToggle() {
    document.querySelectorAll('.commercial-toggle').forEach(btn => {
        btn.addEventListener('click', function () {
            const type = this.dataset.type;
            document.getElementById('id_commercial_type').value = type;

            document.querySelectorAll('.commercial-toggle').forEach(b => {
                b.classList.toggle('bg-blue-600', b.dataset.type === type);
                b.classList.toggle('text-white', b.dataset.type === type);
                b.classList.toggle('bg-white', b.dataset.type !== type);
                b.classList.toggle('text-gray-700', b.dataset.type !== type);
            });

            const label = type === 'vendor' ? 'Vendor Commercial' : 'Market Rate';
            document.querySelectorAll('.cost-table-label').forEach(el => el.textContent = label);
        });
    });

    // Initialize active state from current value
    const current = document.getElementById('id_commercial_type')?.value || 'vendor';
    document.querySelector(`.commercial-toggle[data-type="${current}"]`)?.click();
}

// ─────────────────────────────────────────────
// Location handling
// ─────────────────────────────────────────────
function initLocationHandling() {
    document.getElementById('add-location-btn')?.addEventListener('click', addLocation);
    attachLocationListeners();

    // Auto-populate items for locations with no items yet
    document.querySelectorAll('.location-group').forEach(grp => {
        const idx = grp.getAttribute('data-location-index');
        const costRows = grp.querySelectorAll('.cost-rows .item-row:not(.item-template)');
        if (costRows.length === 0) {
            populateAllItemsForLocation(idx);
        }
    });
}

function attachLocationListeners() {
    document.querySelectorAll('.remove-location-btn').forEach(btn => {
        btn.replaceWith(btn.cloneNode(true));
    });
    document.querySelectorAll('.remove-location-btn').forEach(btn => {
        btn.addEventListener('click', removeLocation);
    });
    document.querySelectorAll('.add-item-btn').forEach(btn => {
        btn.replaceWith(btn.cloneNode(true));
    });
    document.querySelectorAll('.add-item-btn').forEach(btn => {
        btn.addEventListener('click', addItemToLocation);
    });
}

function addLocation() {
    const container = document.getElementById('locations-container');
    const totalForms = document.querySelector('#id_locations-TOTAL_FORMS');
    const newIdx = parseInt(totalForms.value);

    const template = container.querySelector('.location-group');
    if (!template) return;

    const newGrp = template.cloneNode(true);
    newGrp.setAttribute('data-location-index', newIdx);

    // Update all location-scoped prefixes
    newGrp.innerHTML = newGrp.innerHTML.replace(/locations-\d+-/g, `locations-${newIdx}-`);
    newGrp.querySelectorAll('[data-location-index]').forEach(el => {
        el.setAttribute('data-location-index', newIdx);
    });

    // Clear inputs
    newGrp.querySelectorAll('input:not([type=hidden]), textarea').forEach(f => { f.value = ''; });

    // Clear item rows
    newGrp.querySelectorAll('.item-row:not(.item-template)').forEach(r => r.remove());
    newGrp.querySelectorAll('.client-row').forEach(r => r.remove());

    // Reset totals
    newGrp.querySelector('.location-subtotal').textContent = '₹0.00';
    newGrp.querySelector('.location-gst').textContent = '₹0.00';
    newGrp.querySelector('.location-grand-total').textContent = '₹0.00';

    container.appendChild(newGrp);
    totalForms.value = newIdx + 1;

    attachLocationListeners();
    populateAllItemsForLocation(newIdx);
}

function removeLocation(e) {
    const grp = e.target.closest('.location-group');
    const totalForms = document.querySelector('#id_locations-TOTAL_FORMS');
    if (parseInt(totalForms.value) <= 1) {
        alert('At least one location is required.');
        return;
    }
    const del = grp.querySelector('input[name$="-DELETE"]');
    if (del) {
        del.checked = true;
        grp.style.display = 'none';
    } else {
        grp.remove();
        totalForms.value = parseInt(totalForms.value) - 1;
    }
    recalculateAll();
}

// ─────────────────────────────────────────────
// Item population (mirrors reference repo pattern)
// ─────────────────────────────────────────────
function populateAllItemsForLocation(locationIdx) {
    const grp = document.querySelector(`.location-group[data-location-index="${locationIdx}"]`);
    if (!grp) return;

    const costTbody = grp.querySelector('.cost-rows');
    const clientTbody = grp.querySelector('.client-rows');
    const template = costTbody.querySelector('.item-template');
    if (!template) return;

    ITEM_CHOICES.forEach(([value, label, hasStorageUnit], idx) => {
        // ── Cost row ──
        const costRow = template.cloneNode(true);
        costRow.classList.remove('item-template');
        costRow.style.display = '';
        costRow.setAttribute('data-row-index', idx);

        costRow.querySelectorAll('input, select').forEach(f => { f.disabled = false; });

        const prefix = `locations-${locationIdx}-items-${idx}`;
        updateItemPrefix(costRow, prefix);

        // Set description
        costRow.querySelector('.item-description').value = value;
        costRow.querySelector('.item-description-text').textContent = label;

        // Storage unit type
        const unitSel = costRow.querySelector('.storage-unit-type');
        if (hasStorageUnit && unitSel) {
            unitSel.style.display = 'block';
            unitSel.disabled = false;
        } else if (unitSel) {
            unitSel.style.display = 'none';
            unitSel.disabled = true;
        }

        // Clear values
        const vuc = costRow.querySelector('.vendor-unit-cost');
        const vqty = costRow.querySelector('.vendor-quantity');
        const vtot = costRow.querySelector('.vendor-total');
        if (vuc) vuc.value = '';
        if (vqty) vqty.value = '';
        if (vtot) vtot.value = '';

        costTbody.insertBefore(costRow, template);
        attachCostRowListeners(costRow, locationIdx, idx);

        // ── Client row ── (parallel visual row in client table)
        const clientRow = buildClientRow(value, label, locationIdx, idx, prefix);
        clientTbody.appendChild(clientRow);
        attachClientRowListeners(clientRow, locationIdx, idx);
    });

    updateItemManagementForm(locationIdx);
    calculateLocationTotals(locationIdx);
}

function buildClientRow(value, label, locationIdx, rowIdx, prefix) {
    const tr = document.createElement('tr');
    tr.className = 'client-row border-b border-blue-100';
    tr.setAttribute('data-row-index', rowIdx);
    tr.setAttribute('data-location-index', locationIdx);
    tr.innerHTML = `
      <td class="py-1.5 pr-3 text-gray-700 text-sm">${label}</td>
      <td class="py-1.5 pr-3">
        <input type="text" name="${prefix}-unit_cost" class="unit-cost w-full text-right border border-blue-200 rounded px-2 py-1 text-sm bg-white" placeholder="At actual">
      </td>
      <td class="py-1.5 pr-3">
        <input type="text" name="${prefix}-quantity" class="quantity w-full text-right border border-blue-200 rounded px-2 py-1 text-sm bg-white" placeholder="At actual">
      </td>
      <td class="py-1.5 pr-3">
        <input type="text" class="client-total w-full text-right border border-blue-100 rounded px-2 py-1 text-sm bg-blue-50/50" placeholder="0.00" readonly>
      </td>
      <td class="py-1.5 text-right text-xs text-gray-500 row-markup-pct">—</td>
    `;
    return tr;
}

function addItemToLocation(e) {
    const grp = e.target.closest('.location-group');
    const locationIdx = grp.getAttribute('data-location-index');
    const costTbody = grp.querySelector('.cost-rows');
    const clientTbody = grp.querySelector('.client-rows');
    const template = costTbody.querySelector('.item-template');

    const existingRows = costTbody.querySelectorAll('.item-row:not(.item-template)');
    const rowIdx = existingRows.length;
    const prefix = `locations-${locationIdx}-items-${rowIdx}`;

    // Cost row with dropdown
    const costRow = template.cloneNode(true);
    costRow.classList.remove('item-template');
    costRow.style.display = '';
    costRow.setAttribute('data-row-index', rowIdx);
    costRow.querySelectorAll('input, select').forEach(f => { f.disabled = false; });
    updateItemPrefix(costRow, prefix);

    // Show dropdown for manual items
    costRow.querySelector('.item-description-text').style.display = 'none';
    const sel = costRow.querySelector('.item-description-select');
    if (sel) { sel.style.display = 'block'; sel.disabled = false; }

    costTbody.insertBefore(costRow, template);
    attachCostRowListeners(costRow, locationIdx, rowIdx);

    const clientRow = buildClientRow('(select type)', '', locationIdx, rowIdx, prefix);
    clientTbody.appendChild(clientRow);
    attachClientRowListeners(clientRow, locationIdx, rowIdx);

    updateItemManagementForm(locationIdx);
}

function updateItemPrefix(row, prefix) {
    row.querySelectorAll('[name]').forEach(f => {
        f.setAttribute('name', f.getAttribute('name').replace(/__prefix__/g, prefix));
    });
    row.querySelectorAll('[id]').forEach(f => {
        f.setAttribute('id', f.getAttribute('id').replace(/__prefix__/g, prefix));
    });
}

// ─────────────────────────────────────────────
// Event listeners for cost & client rows
// ─────────────────────────────────────────────
function attachCostRowListeners(row, locationIdx, rowIdx) {
    const vuc = row.querySelector('.vendor-unit-cost');
    const vqty = row.querySelector('.vendor-quantity');
    const vtot = row.querySelector('.vendor-total');

    [vuc, vqty, vtot].forEach(inp => {
        inp?.addEventListener('input', function () {
            computeCostTotal(row);
            applyMarkupToRow(locationIdx, rowIdx);
            calculateLocationTotals(locationIdx);
            recalculateAll();
        });
    });

    // Remove button
    row.querySelector('.remove-item-btn')?.addEventListener('click', function () {
        const idInput = row.querySelector('input[name$="-id"]');
        const del = row.querySelector('input[name$="-DELETE"]');
        if (idInput?.value && del) {
            del.checked = true;
            row.style.display = 'none';
        } else {
            row.remove();
        }
        // Remove corresponding client row
        const clientRow = document.querySelector(
            `.client-row[data-location-index="${locationIdx}"][data-row-index="${rowIdx}"]`
        );
        clientRow?.remove();
        updateItemManagementForm(locationIdx);
        calculateLocationTotals(locationIdx);
        recalculateAll();
    });

    // Storage unit type select → update client row label if needed
    row.querySelector('.item-description-select')?.addEventListener('change', function () {
        row.querySelector('.item-description').value = this.value;
        const storageUnit = row.querySelector('.storage-unit-type');
        if (storageUnit) {
            storageUnit.style.display = this.value === 'storage_charges' ? 'block' : 'none';
            storageUnit.disabled = this.value !== 'storage_charges';
        }
    });
}

function attachClientRowListeners(row, locationIdx, rowIdx) {
    const uc = row.querySelector('.unit-cost');
    const qty = row.querySelector('.quantity');
    const ctot = row.querySelector('.client-total');

    [uc, qty, ctot].forEach(inp => {
        inp?.addEventListener('input', function () {
            computeClientTriplet(row);
            calculateLocationTotals(locationIdx);
            calculateLocationMarkup(locationIdx);
            updateOverallMarkup();
        });
    });
}

// ─────────────────────────────────────────────
// Calculations
// ─────────────────────────────────────────────
function computeCostTotal(costRow) {
    const vuc = parseFloat(costRow.querySelector('.vendor-unit-cost')?.value) || 0;
    const vqty = parseFloat(costRow.querySelector('.vendor-quantity')?.value) || 0;
    const vtot = costRow.querySelector('.vendor-total');
    if (vtot && vuc > 0 && vqty > 0) {
        vtot.value = (vuc * vqty).toFixed(2);
    }
}

function applyMarkupToRow(locationIdx, rowIdx) {
    const markupPct = parseFloat(document.getElementById('id_default_markup_pct')?.value) || 26;
    const multiplier = 1 + (markupPct / 100);

    const costRow = document.querySelector(
        `.location-group[data-location-index="${locationIdx}"] .cost-rows .item-row[data-row-index="${rowIdx}"]`
    );
    const clientRow = document.querySelector(
        `.location-group[data-location-index="${locationIdx}"] .client-row[data-row-index="${rowIdx}"]`
    );
    if (!costRow || !clientRow) return;

    const vuc = parseFloat(costRow.querySelector('.vendor-unit-cost')?.value);
    const vqty = parseFloat(costRow.querySelector('.vendor-quantity')?.value);

    const ucInput = clientRow.querySelector('.unit-cost');
    const qtyInput = clientRow.querySelector('.quantity');
    const totInput = clientRow.querySelector('.client-total');

    if (!isNaN(vuc) && vuc > 0) {
        ucInput.value = (vuc * multiplier).toFixed(2);
    }
    if (!isNaN(vqty) && vqty > 0) {
        qtyInput.value = vqty.toFixed(2);
    }
    if (!isNaN(vuc) && !isNaN(vqty) && vuc > 0 && vqty > 0) {
        totInput.value = (vuc * multiplier * vqty).toFixed(2);
    }

    // Update row-level markup%
    updateRowMarkup(clientRow, costRow);
}

function applyMarkupToAllRows(locationIdx) {
    const grp = document.querySelector(`.location-group[data-location-index="${locationIdx}"]`);
    if (!grp) return;
    grp.querySelectorAll('.cost-rows .item-row:not(.item-template)').forEach(row => {
        const rowIdx = row.getAttribute('data-row-index');
        applyMarkupToRow(locationIdx, rowIdx);
    });
}

function computeClientTriplet(clientRow) {
    const ucInput = clientRow.querySelector('.unit-cost');
    const qtyInput = clientRow.querySelector('.quantity');
    const totInput = clientRow.querySelector('.client-total');

    const uc = parseFloat(ucInput?.value);
    const qty = parseFloat(qtyInput?.value);
    const tot = parseFloat(totInput?.value);

    const hasUC = !isNaN(uc) && uc >= 0;
    const hasQty = !isNaN(qty) && qty > 0;
    const hasTot = !isNaN(tot) && tot >= 0;

    const lastEdited = clientRow.querySelector('[data-last-edited]')?.className || '';

    if (hasUC && hasQty) {
        if (totInput) totInput.value = (uc * qty).toFixed(2);
    } else if (hasUC && hasTot && uc > 0) {
        if (qtyInput) qtyInput.value = (tot / uc).toFixed(2);
    } else if (hasQty && hasTot && qty > 0) {
        if (ucInput) ucInput.value = (tot / qty).toFixed(2);
    }

    // Update row-level markup
    const locationIdx = clientRow.getAttribute('data-location-index');
    const rowIdx = clientRow.getAttribute('data-row-index');
    const costRow = document.querySelector(
        `.location-group[data-location-index="${locationIdx}"] .cost-rows .item-row[data-row-index="${rowIdx}"]`
    );
    if (costRow) updateRowMarkup(clientRow, costRow);
}

function updateRowMarkup(clientRow, costRow) {
    const uc = parseFloat(clientRow.querySelector('.unit-cost')?.value) || 0;
    const qty = parseFloat(clientRow.querySelector('.quantity')?.value) || 0;
    const vuc = parseFloat(costRow.querySelector('.vendor-unit-cost')?.value) || 0;
    const vqty = parseFloat(costRow.querySelector('.vendor-quantity')?.value) || 0;

    const clientTotal = uc * qty;
    const costTotal = vuc * vqty;

    const markupEl = clientRow.querySelector('.row-markup-pct');
    if (!markupEl) return;

    if (costTotal > 0 && clientTotal > 0) {
        const markup = ((clientTotal - costTotal) / costTotal) * 100;
        markupEl.textContent = markup.toFixed(1) + '%';
        markupEl.className = 'py-1.5 text-right text-xs font-medium row-markup-pct ' + (
            markup >= 26 ? 'text-green-600' :
            markup >= 15 ? 'text-amber-600' : 'text-red-600'
        );
    } else {
        markupEl.textContent = '—';
        markupEl.className = 'py-1.5 text-right text-xs text-gray-400 row-markup-pct';
    }
}

function calculateLocationTotals(locationIdx) {
    const grp = document.querySelector(`.location-group[data-location-index="${locationIdx}"]`);
    if (!grp) return;

    let clientSubtotal = 0;
    grp.querySelectorAll(`.client-row[data-location-index="${locationIdx}"]`).forEach(row => {
        const uc = parseFloat(row.querySelector('.unit-cost')?.value) || 0;
        const qty = parseFloat(row.querySelector('.quantity')?.value) || 0;
        const tot = parseFloat(row.querySelector('.client-total')?.value) || 0;
        clientSubtotal += tot || (uc * qty);
    });

    const gst = clientSubtotal * GST_RATE;
    const grandTotal = clientSubtotal + gst;

    grp.querySelector('.location-subtotal').textContent = '₹' + formatINR(clientSubtotal);
    grp.querySelector('.location-gst').textContent = '₹' + formatINR(gst);
    grp.querySelector('.location-grand-total').textContent = '₹' + formatINR(grandTotal);
}

function calculateLocationMarkup(locationIdx) {
    const grp = document.querySelector(`.location-group[data-location-index="${locationIdx}"]`);
    if (!grp) return;

    let clientTotal = 0;
    let costTotal = 0;

    grp.querySelectorAll('.cost-rows .item-row:not(.item-template)').forEach(costRow => {
        const rowIdx = costRow.getAttribute('data-row-index');
        const clientRow = grp.querySelector(`.client-row[data-row-index="${rowIdx}"]`);

        const vuc = parseFloat(costRow.querySelector('.vendor-unit-cost')?.value) || 0;
        const vqty = parseFloat(costRow.querySelector('.vendor-quantity')?.value) || 0;
        costTotal += vuc * vqty;

        if (clientRow) {
            const uc = parseFloat(clientRow.querySelector('.unit-cost')?.value) || 0;
            const qty = parseFloat(clientRow.querySelector('.quantity')?.value) || 0;
            const tot = parseFloat(clientRow.querySelector('.client-total')?.value) || 0;
            clientTotal += tot || (uc * qty);
        }
    });

    const badge = grp.querySelector('.markup-badge');
    if (!badge) return;

    if (costTotal > 0) {
        const markup = ((clientTotal - costTotal) / costTotal) * 100;
        badge.textContent = `Markup: ${markup.toFixed(1)}%`;
        badge.className = 'markup-badge text-sm font-medium px-3 py-1 rounded-full ' + (
            markup >= 26 ? 'bg-green-100 text-green-700' :
            markup >= 15 ? 'bg-amber-100 text-amber-700' :
            'bg-red-100 text-red-700'
        );
    } else {
        badge.textContent = 'Markup: —';
        badge.className = 'markup-badge text-sm font-medium px-3 py-1 rounded-full bg-gray-100 text-gray-500';
    }
}

function updateOverallMarkup() {
    let totalClient = 0;
    let totalCost = 0;

    document.querySelectorAll('.location-group').forEach(grp => {
        if (grp.style.display === 'none') return;
        const locationIdx = grp.getAttribute('data-location-index');

        grp.querySelectorAll('.cost-rows .item-row:not(.item-template)').forEach(costRow => {
            const rowIdx = costRow.getAttribute('data-row-index');
            const clientRow = grp.querySelector(`.client-row[data-row-index="${rowIdx}"]`);

            const vuc = parseFloat(costRow.querySelector('.vendor-unit-cost')?.value) || 0;
            const vqty = parseFloat(costRow.querySelector('.vendor-quantity')?.value) || 0;
            totalCost += vuc * vqty;

            if (clientRow) {
                const uc = parseFloat(clientRow.querySelector('.unit-cost')?.value) || 0;
                const qty = parseFloat(clientRow.querySelector('.quantity')?.value) || 0;
                const tot = parseFloat(clientRow.querySelector('.client-total')?.value) || 0;
                totalClient += tot || (uc * qty);
            }
        });
    });

    const banner = document.getElementById('overall-markup-banner');
    const valueEl = document.getElementById('overall-markup-value');
    const approvalBtn = document.getElementById('request-approval-btn');

    if (!valueEl) return;

    if (totalCost > 0) {
        const markup = ((totalClient - totalCost) / totalCost) * 100;
        valueEl.textContent = markup.toFixed(1) + '%';

        if (markup >= 26) {
            valueEl.className = 'text-lg font-bold text-green-600';
            banner.className = 'mt-4 p-3 rounded-lg bg-green-50 border border-green-200 flex items-center justify-between';
            if (approvalBtn) approvalBtn.style.display = 'none';
        } else if (markup >= 15) {
            valueEl.className = 'text-lg font-bold text-amber-600';
            banner.className = 'mt-4 p-3 rounded-lg bg-amber-50 border border-amber-300 flex items-center justify-between';
            if (approvalBtn) approvalBtn.style.display = 'inline-flex';
        } else {
            valueEl.className = 'text-lg font-bold text-red-600';
            banner.className = 'mt-4 p-3 rounded-lg bg-red-50 border border-red-300 flex items-center justify-between';
            if (approvalBtn) approvalBtn.style.display = 'none';
            // Show error hint
            const hint = document.getElementById('markup-error-hint') || (() => {
                const d = document.createElement('span');
                d.id = 'markup-error-hint';
                d.className = 'text-xs text-red-600 ml-2';
                d.textContent = 'Below 15% — cannot save. Increase client pricing.';
                valueEl.parentNode.appendChild(d);
                return d;
            })();
            hint.style.display = 'inline';
        }
    } else {
        valueEl.textContent = '—';
        valueEl.className = 'text-lg font-bold text-gray-400';
    }
}

function recalculateAll() {
    document.querySelectorAll('.location-group').forEach(grp => {
        const idx = grp.getAttribute('data-location-index');
        applyMarkupToAllRows(idx);
        calculateLocationTotals(idx);
        calculateLocationMarkup(idx);
    });
    updateOverallMarkup();
}

// ─────────────────────────────────────────────
// Load existing items (edit mode)
// ─────────────────────────────────────────────
function loadExistingItems() {
    if (typeof EXISTING_ITEMS_JSON === 'undefined') return;
    const existing = JSON.parse(EXISTING_ITEMS_JSON || '{}');

    Object.entries(existing).forEach(([locationIdx, items]) => {
        if (!items || items.length === 0) return;

        const grp = document.querySelector(`.location-group[data-location-index="${locationIdx}"]`);
        if (!grp) return;

        const costTbody = grp.querySelector('.cost-rows');
        const clientTbody = grp.querySelector('.client-rows');
        const template = costTbody.querySelector('.item-template');

        items.forEach((item, idx) => {
            const prefix = `locations-${locationIdx}-items-${idx}`;
            const hasStorageUnit = item.item_description === 'storage_charges';

            // Cost row
            const costRow = template.cloneNode(true);
            costRow.classList.remove('item-template');
            costRow.style.display = '';
            costRow.setAttribute('data-row-index', idx);
            costRow.querySelectorAll('input, select').forEach(f => { f.disabled = false; });
            updateItemPrefix(costRow, prefix);

            costRow.querySelector('.item-description').value = item.item_description;
            costRow.querySelector('.item-description-text').textContent = getLabelForChoice(item.item_description);

            // Set hidden id field for existing items
            const idInput = costRow.querySelector('input[name$="-id"]');
            if (idInput && item.id) idInput.value = item.id;

            const storageUnit = costRow.querySelector('.storage-unit-type');
            if (storageUnit) {
                storageUnit.style.display = hasStorageUnit ? 'block' : 'none';
                storageUnit.disabled = !hasStorageUnit;
                if (hasStorageUnit && item.storage_unit_type) {
                    storageUnit.value = item.storage_unit_type;
                }
            }

            const vuc = costRow.querySelector('.vendor-unit-cost');
            const vqty = costRow.querySelector('.vendor-quantity');
            if (vuc) vuc.value = item.vendor_unit_cost || '';
            if (vqty) vqty.value = item.vendor_quantity || '';
            computeCostTotal(costRow);

            costTbody.insertBefore(costRow, template);
            attachCostRowListeners(costRow, locationIdx, idx);

            // Client row
            const clientRow = buildClientRow(
                getLabelForChoice(item.item_description),
                item.item_description,
                locationIdx, idx, prefix
            );
            const ucInput = clientRow.querySelector('.unit-cost');
            const qtyInput = clientRow.querySelector('.quantity');
            if (ucInput) ucInput.value = item.unit_cost || '';
            if (qtyInput) qtyInput.value = item.quantity || '';

            clientTbody.appendChild(clientRow);
            attachClientRowListeners(clientRow, locationIdx, idx);
        });

        updateItemManagementForm(locationIdx);
    });
}

function getLabelForChoice(value) {
    const found = ITEM_CHOICES.find(([v]) => v === value);
    return found ? found[1] : value;
}

// ─────────────────────────────────────────────
// Management form
// ─────────────────────────────────────────────
function updateItemManagementForm(locationIdx) {
    const grp = document.querySelector(`.location-group[data-location-index="${locationIdx}"]`);
    if (!grp) return;

    const visible = Array.from(grp.querySelectorAll('.cost-rows .item-row')).filter(row => {
        if (row.classList.contains('item-template')) return false;
        const del = row.querySelector('input[name$="-DELETE"]');
        if (del && del.checked) return false;
        const firstInput = row.querySelector('input, select');
        if (firstInput && firstInput.disabled) return false;
        return true;
    });

    const totalForms = document.getElementById(`id_locations-${locationIdx}-items-TOTAL_FORMS`);
    if (totalForms) totalForms.value = visible.length;
}

// ─────────────────────────────────────────────
// Validation
// ─────────────────────────────────────────────
function validateForm() {
    // Check overall markup is not below 15%
    let totalClient = 0;
    let totalCost = 0;

    document.querySelectorAll('.location-group').forEach(grp => {
        if (grp.style.display === 'none') return;
        grp.querySelectorAll('.cost-rows .item-row:not(.item-template)').forEach(costRow => {
            const rowIdx = costRow.getAttribute('data-row-index');
            const locationIdx = grp.getAttribute('data-location-index');
            const clientRow = grp.querySelector(`.client-row[data-row-index="${rowIdx}"]`);
            const vuc = parseFloat(costRow.querySelector('.vendor-unit-cost')?.value) || 0;
            const vqty = parseFloat(costRow.querySelector('.vendor-quantity')?.value) || 0;
            totalCost += vuc * vqty;
            if (clientRow) {
                const uc = parseFloat(clientRow.querySelector('.unit-cost')?.value) || 0;
                const qty = parseFloat(clientRow.querySelector('.quantity')?.value) || 0;
                const tot = parseFloat(clientRow.querySelector('.client-total')?.value) || 0;
                totalClient += tot || (uc * qty);
            }
        });
    });

    if (totalCost > 0) {
        const markup = ((totalClient - totalCost) / totalCost) * 100;
        if (markup < 15) {
            alert(`Markup is ${markup.toFixed(1)}%, which is below the 15% minimum. Please increase client pricing.`);
            return false;
        }
    }
    return true;
}

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────
function formatINR(n) {
    if (isNaN(n)) return '0.00';
    return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
```

**Step 4: Update template to reference new JS and pass `EXISTING_ITEMS_JSON` as JS variable**

At the bottom of `quotation_create.html`, inside `{% block extra_js %}`:

```html
<script>
  const EXISTING_ITEMS_JSON = {{ existing_items_json|safe }};
</script>
<script src="{% static 'projects/js/quotation_form.js' %}?v={{ BUILD_VERSION|default:'1' }}"></script>
```

---

## Phase 5: Templates — Detail, List, New Pages

### Task 14: Update `quotation_detail.html`

**Files:**
- Modify: `templates/projects/quotations/quotation_detail.html`

**Step 1: Add status transition buttons**

After the existing action buttons (Download, Send Email, etc.), add:

```html
<!-- Status Transition Actions -->
{% if quotation.status == 'sent' %}
<form method="post" action="{% url 'projects:quotation_transition' quotation.quotation_id %}" class="inline">
  {% csrf_token %}
  <input type="hidden" name="action" value="mark_accepted">
  <button type="submit" class="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700">
    ✓ Mark Accepted
  </button>
</form>
<form method="post" action="{% url 'projects:quotation_transition' quotation.quotation_id %}" class="inline ml-2">
  {% csrf_token %}
  <input type="hidden" name="action" value="mark_rejected">
  <button type="submit" class="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700">
    ✗ Mark Rejected
  </button>
</form>
{% endif %}

{% if quotation.status in 'accepted,rejected' and is_director %}
<form method="post" action="{% url 'projects:quotation_transition' quotation.quotation_id %}" class="inline ml-2">
  {% csrf_token %}
  <input type="hidden" name="action" value="reopen_draft">
  <button type="submit" class="px-4 py-2 bg-gray-600 text-white rounded-lg text-sm font-medium hover:bg-gray-700">
    ↩ Reopen as Draft
  </button>
</form>
{% endif %}

{% if quotation.status == 'draft' and is_director %}
<form method="post" action="{% url 'projects:quotation_transition' quotation.quotation_id %}" class="inline ml-2"
      onsubmit="return confirm('Void this quotation? This cannot be undone.');">
  {% csrf_token %}
  <input type="hidden" name="action" value="void">
  <button type="submit" class="px-4 py-2 bg-gray-400 text-white rounded-lg text-sm font-medium hover:bg-gray-500">
    🚫 Void
  </button>
</form>
{% endif %}

<!-- Clone button -->
<form method="post" action="{% url 'projects:quotation_clone' quotation.quotation_id %}" class="inline ml-2">
  {% csrf_token %}
  <button type="submit" class="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm hover:bg-gray-50">
    Clone
  </button>
</form>
```

**Step 2: Add acceptance link section (shown for sent quotations)**

```html
{% if quotation.status == 'sent' %}
<div class="mt-4 p-4 bg-blue-50 border border-blue-200 rounded-xl">
  <div class="flex items-center justify-between">
    <div>
      <h4 class="text-sm font-semibold text-blue-700">Client Acceptance Link</h4>
      {% if acceptance_link %}
      <p class="text-xs text-gray-600 mt-1 break-all">{{ acceptance_link }}</p>
      {% elif quotation.acceptance_token %}
      <p class="text-xs text-gray-600 mt-1">
        Token generated. Status:
        {% if quotation.acceptance_token.is_used %}
          <span class="font-medium">{{ quotation.acceptance_token.accepted|yesno:"Accepted,Rejected" }}</span>
        {% else %}
          Awaiting client response
        {% endif %}
      </p>
      {% else %}
      <p class="text-xs text-gray-500 mt-1">Generate a link for the client to accept/reject without login.</p>
      {% endif %}
    </div>
    <form method="post" action="{% url 'projects:quotation_acceptance_link' quotation.quotation_id %}">
      {% csrf_token %}
      <button type="submit" class="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700">
        Generate Link
      </button>
    </form>
  </div>
</div>
{% endif %}
```

**Step 3: Add acceptance_link from session to context in `quotation_detail` view**

In `projects/views_quotation.py`, in `quotation_detail`:

```python
# Retrieve acceptance link from session if just generated
acceptance_link = request.session.pop(f'acceptance_link_{quotation_id}', None)

context = {
    'quotation': quotation,
    'audit_logs': quotation.audit_logs.all()[:20],
    'is_director': is_director,
    'acceptance_link': acceptance_link,
    **({'revisions': quotation.revisions.all()[:5]} if hasattr(quotation, 'revisions') else {}),
}
```

**Step 4: Add revision history accordion**

```html
<!-- Revision History -->
{% if quotation.revisions.exists %}
<div class="mt-6">
  <h3 class="text-sm font-semibold text-gray-700 mb-2">Revision History</h3>
  <div class="space-y-2">
    {% for rev in quotation.revisions.all|slice:":5" %}
    <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200 text-sm">
      <div>
        <span class="font-medium text-gray-800">Rev {{ rev.revision_number }}</span>
        <span class="text-gray-500 ml-2">{{ rev.created_at|date:"d M Y" }}</span>
        {% if rev.created_by %}<span class="text-gray-500 ml-2">by {{ rev.created_by.get_full_name }}</span>{% endif %}
        {% if rev.reason %}<span class="text-gray-600 ml-2">— {{ rev.reason }}</span>{% endif %}
      </div>
      <a href="{% url 'projects:quotation_revision_view' quotation.quotation_id rev.revision_number %}"
         class="text-blue-600 hover:underline text-xs">View</a>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
```

**Step 5: Add expiry banner on detail page**

```html
{% if quotation.status == 'expired' %}
<div class="mb-4 p-3 bg-amber-50 border border-amber-300 rounded-lg text-sm text-amber-800">
  ⚠ This quotation expired on {{ quotation.validity_date|date:"d M Y" }}.
  {% if is_director %}
    <a href="{% url 'projects:quotation_edit' quotation.quotation_id %}" class="ml-2 underline">Edit to renew</a>
  {% endif %}
</div>
{% endif %}
```

### Task 15: Create new template pages

**Files:**
- Create: `templates/projects/quotations/quotation_accept_public.html`
- Create: `templates/projects/quotations/quotation_dashboard.html`
- Create: `templates/projects/quotations/quotation_revision.html`

**`quotation_accept_public.html`** — standalone, no ERP nav:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Quotation Response — Godamwale</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen flex items-start justify-center pt-10 px-4">
  <div class="max-w-2xl w-full">
    <!-- Header -->
    <div class="text-center mb-8">
      <h1 class="text-2xl font-bold text-gray-800">Godamwale Warehousing & Logistics</h1>
      <p class="text-gray-500 text-sm mt-1">Quotation Response Portal</p>
    </div>

    {% if already_responded %}
    <div class="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 text-center">
      <div class="text-4xl mb-4">{% if accepted %}✅{% else %}❌{% endif %}</div>
      <h2 class="text-xl font-semibold text-gray-800 mb-2">Already Responded</h2>
      <p class="text-gray-600">You have already {% if accepted %}accepted{% else %}declined{% endif %} quotation <strong>{{ quotation.quotation_number }}</strong>.</p>
    </div>

    {% elif expired %}
    <div class="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 text-center">
      <div class="text-4xl mb-4">⏰</div>
      <h2 class="text-xl font-semibold text-gray-800 mb-2">Link Expired</h2>
      <p class="text-gray-600">This acceptance link for quotation <strong>{{ quotation.quotation_number }}</strong> has expired.</p>
      <p class="text-gray-500 text-sm mt-2">Please contact your Godamwale representative.</p>
    </div>

    {% elif thank_you %}
    <div class="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 text-center">
      <div class="text-4xl mb-4">{% if accepted %}🎉{% else %}👋{% endif %}</div>
      <h2 class="text-xl font-semibold text-gray-800 mb-2">Thank You!</h2>
      <p class="text-gray-600">
        You have <strong>{% if accepted %}accepted{% else %}declined{% endif %}</strong> quotation
        <strong>{{ quotation.quotation_number }}</strong> from Godamwale.
      </p>
      <p class="text-gray-500 text-sm mt-2">Our team will be in touch shortly.</p>
    </div>

    {% else %}
    <!-- Main response form -->
    <div class="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
      <div class="p-6 border-b border-gray-100">
        <div class="flex justify-between items-start">
          <div>
            <h2 class="text-lg font-semibold text-gray-800">{{ quotation.quotation_number }}</h2>
            <p class="text-gray-500 text-sm">{{ quotation.client_company }}</p>
          </div>
          <div class="text-right text-sm text-gray-500">
            <div>Valid until: <strong>{{ quotation.validity_date|date:"d M Y" }}</strong></div>
          </div>
        </div>
      </div>

      <!-- Quotation summary -->
      <div class="p-6">
        {% for location in locations %}
        <h3 class="font-medium text-gray-700 mb-2">{{ location.location_name }}</h3>
        <table class="w-full text-sm mb-4">
          <thead>
            <tr class="border-b border-gray-200">
              <th class="text-left py-1 text-gray-600">Service</th>
              <th class="text-right py-1 text-gray-600">Rate</th>
              <th class="text-right py-1 text-gray-600">Qty</th>
              <th class="text-right py-1 text-gray-600">Total</th>
            </tr>
          </thead>
          <tbody>
            {% for item in location.items.all %}
            <tr class="border-b border-gray-100">
              <td class="py-1.5 text-gray-800">{{ item.display_description }}</td>
              <td class="py-1.5 text-right text-gray-700">{{ item.display_unit_cost }}</td>
              <td class="py-1.5 text-right text-gray-700">{{ item.display_quantity }}</td>
              <td class="py-1.5 text-right font-medium text-gray-800">{{ item.display_total }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        {% endfor %}
      </div>

      <!-- Response form -->
      <div class="p-6 bg-gray-50 border-t border-gray-100">
        <h3 class="font-semibold text-gray-700 mb-4">Your Response</h3>
        <form method="post">
          {% csrf_token %}
          <textarea name="remarks" rows="3" placeholder="Add any remarks or questions (optional)"
            class="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm resize-none mb-4 focus:ring-2 focus:ring-blue-500 focus:outline-none"></textarea>
          <div class="flex gap-3">
            <button type="submit" name="action" value="accept"
              class="flex-1 py-3 bg-green-600 text-white rounded-xl font-semibold text-sm hover:bg-green-700 transition-colors">
              ✓ Accept Quotation
            </button>
            <button type="submit" name="action" value="reject"
              class="flex-1 py-3 bg-red-100 text-red-700 rounded-xl font-semibold text-sm hover:bg-red-200 transition-colors">
              ✗ Decline
            </button>
          </div>
        </form>
      </div>
    </div>
    {% endif %}
  </div>
</body>
</html>
```

**`quotation_dashboard.html`** — extends base.html:

```html
{% extends 'base.html' %}
{% block title %}Quotation Dashboard{% endblock %}
{% block content %}
<div class="max-w-7xl mx-auto px-4 py-6">
  <div class="flex items-center justify-between mb-6">
    <h1 class="text-2xl font-bold text-gray-800">Quotation Dashboard</h1>
    <a href="{% url 'projects:quotation_list' %}" class="text-sm text-blue-600 hover:underline">← All Quotations</a>
  </div>

  <!-- This Month Stats -->
  <div class="grid grid-cols-4 gap-4 mb-6">
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div class="text-3xl font-bold text-gray-800">{{ monthly_sent }}</div>
      <div class="text-sm text-gray-500 mt-1">Sent This Month</div>
    </div>
    <div class="bg-white rounded-xl border border-green-200 shadow-sm p-5">
      <div class="text-3xl font-bold text-green-600">{{ monthly_won }}</div>
      <div class="text-sm text-gray-500 mt-1">Won ({{ win_rate }}%)</div>
    </div>
    <div class="bg-white rounded-xl border border-red-200 shadow-sm p-5">
      <div class="text-3xl font-bold text-red-500">{{ monthly_lost }}</div>
      <div class="text-sm text-gray-500 mt-1">Lost</div>
    </div>
    <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div class="text-3xl font-bold text-gray-600">{{ monthly_sent|add:"-"|add:monthly_won|add:"-"|add:monthly_lost }}</div>
      <div class="text-sm text-gray-500 mt-1">In Pipeline</div>
    </div>
  </div>

  <!-- Pending Actions -->
  <div class="grid grid-cols-3 gap-4 mb-6">
    <a href="{% url 'projects:quotation_list' %}?status=pending_approval"
       class="bg-amber-50 border border-amber-200 rounded-xl p-4 hover:bg-amber-100 transition-colors">
      <div class="text-2xl font-bold text-amber-700">{{ pending_approval_count }}</div>
      <div class="text-sm text-amber-600 mt-1">Awaiting Director Approval</div>
    </a>
    <div class="bg-red-50 border border-red-200 rounded-xl p-4">
      <div class="text-2xl font-bold text-red-600">{{ expiring_soon_count }}</div>
      <div class="text-sm text-red-500 mt-1">Expiring This Week</div>
    </div>
    <a href="{% url 'projects:quotation_list' %}?status=sent"
       class="bg-blue-50 border border-blue-200 rounded-xl p-4 hover:bg-blue-100 transition-colors">
      <div class="text-2xl font-bold text-blue-600">{{ awaiting_response }}</div>
      <div class="text-sm text-blue-500 mt-1">Awaiting Client Response</div>
    </a>
  </div>

  <!-- Recent Won Quotations -->
  <div class="bg-white rounded-xl border border-gray-200 shadow-sm">
    <div class="p-4 border-b border-gray-100">
      <h2 class="font-semibold text-gray-700">Recently Won</h2>
    </div>
    <div class="divide-y divide-gray-100">
      {% for q in top_accepted %}
      <a href="{% url 'projects:quotation_detail' q.quotation_id %}"
         class="flex items-center justify-between px-4 py-3 hover:bg-gray-50">
        <div>
          <span class="font-medium text-gray-800">{{ q.quotation_number }}</span>
          <span class="text-gray-500 ml-3 text-sm">{{ q.client_company }}</span>
        </div>
        <div class="text-sm text-green-600 font-medium">₹{{ q.grand_total|floatformat:0 }}</div>
      </a>
      {% empty %}
      <p class="px-4 py-6 text-gray-400 text-sm text-center">No accepted quotations yet.</p>
      {% endfor %}
    </div>
  </div>
</div>
{% endblock %}
```

**`quotation_revision.html`** — extends base.html, read-only snapshot:

```html
{% extends 'base.html' %}
{% block title %}Revision {{ revision.revision_number }} — {{ quotation.quotation_number }}{% endblock %}
{% block content %}
<div class="max-w-5xl mx-auto px-4 py-6">
  <div class="flex items-center gap-3 mb-6">
    <a href="{% url 'projects:quotation_detail' quotation.quotation_id %}" class="text-blue-600 hover:underline text-sm">
      ← {{ quotation.quotation_number }}
    </a>
    <span class="text-gray-400">/</span>
    <h1 class="text-xl font-bold text-gray-800">Revision {{ revision.revision_number }}</h1>
    <span class="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full">Read Only</span>
  </div>

  <div class="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-6 text-sm text-amber-800">
    Snapshot taken on {{ revision.created_at|date:"d M Y H:i" }}
    {% if revision.created_by %}by {{ revision.created_by.get_full_name }}{% endif %}
    {% if revision.reason %}— "{{ revision.reason }}"{% endif %}
  </div>

  <!-- Snapshot data -->
  {% with s=snapshot %}
  <div class="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-4">
    <div class="grid grid-cols-2 gap-4 text-sm">
      <div><span class="text-gray-500">Client:</span> <span class="font-medium">{{ s.client_name }} ({{ s.client_company }})</span></div>
      <div><span class="text-gray-500">Status at time:</span> <span class="font-medium">{{ s.status|capfirst }}</span></div>
      <div><span class="text-gray-500">GST Rate:</span> <span class="font-medium">{{ s.gst_rate }}%</span></div>
      <div><span class="text-gray-500">Markup %:</span> <span class="font-medium">{{ s.default_markup_pct }}%</span></div>
    </div>
  </div>

  {% for loc in s.locations %}
  <div class="bg-white rounded-xl border border-gray-200 shadow-sm mb-4">
    <div class="p-4 border-b border-gray-100 font-medium text-gray-700">{{ loc.location_name }}</div>
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-gray-100">
          <th class="px-4 py-2 text-left text-gray-600">Service</th>
          <th class="px-4 py-2 text-right text-gray-600">Rate</th>
          <th class="px-4 py-2 text-right text-gray-600">Qty</th>
        </tr>
      </thead>
      <tbody>
        {% for item in loc.items %}
        <tr class="border-b border-gray-50">
          <td class="px-4 py-2 text-gray-800">{{ item.item_description }}</td>
          <td class="px-4 py-2 text-right text-gray-700">{{ item.unit_cost }}</td>
          <td class="px-4 py-2 text-right text-gray-700">{{ item.quantity }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endfor %}
  {% endwith %}
</div>
{% endblock %}
```

### Task 16: Update `quotation_list.html`

**Files:**
- Modify: `templates/projects/quotations/quotation_list.html`

**Step 1: Add `expired` to status filter dropdown**

In the status filter `<select>`, add:
```html
<option value="expired" {% if status_filter == 'expired' %}selected{% endif %}>Expired</option>
<option value="voided" {% if status_filter == 'voided' %}selected{% endif %}>Voided</option>
```

**Step 2: Update status badge colors**

Add to the `status_badge` logic:
```html
{% elif quotation.status == 'expired' %}
  <span class="px-2 py-1 text-xs font-medium rounded-full bg-orange-100 text-orange-700">Expired</span>
{% elif quotation.status == 'voided' %}
  <span class="px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-500">Voided</span>
```

**Step 3: Add Dashboard link in page header**

```html
{% if is_director %}
<a href="{% url 'projects:quotation_dashboard' %}"
   class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200">
  Dashboard
</a>
{% endif %}
```

---

## Phase 6: PDF/DOCX — Remove Vendor Rates from Output

### Task 17: Update `quotation_docx_local.py`

**Files:**
- Modify: `projects/services/quotation_docx_local.py`

**Goal:** The DOCX/PDF generator should only use `unit_cost` / `quantity` (client pricing) when building the commercials table. Remove any code that outputs `vendor_unit_cost` / `vendor_quantity`.

**Step 1: Search for vendor field references in the generator**

```bash
grep -n "vendor" projects/services/quotation_docx_local.py
```

**Step 2: For each occurrence of `item.vendor_unit_cost` or `item.vendor_quantity`** in the table generation code, remove that column or replace with the client-side equivalent.

The typical pattern in `quotation_docx_local.py` builds a table row with all item fields. The output table should have only:
- Description (item.display_description)
- Unit (item.storage_unit_type display, if storage_charges)
- Rate (item.display_unit_cost — client rate)
- Quantity (item.display_quantity — client qty)
- Total (item.display_total — client total)

Remove any separate "Vendor" section or columns from the template rendering.

---

## Phase 7: Final Wiring + Smoke Test

### Task 18: Add `is_director` to list view context

**Files:**
- Modify: `projects/views_quotation.py`

In `quotation_list`, add `is_director` to context (needed for Dashboard link):

```python
is_director = (
    request.user.is_superuser
    or (hasattr(request.user, 'role') and request.user.role in ('director', 'admin'))
)
context = {
    'quotations': quotations,
    'search_query': search,
    'status_filter': status,
    'is_director': is_director,
}
```

### Task 19: Add `QuotationAuditService` action for new action types

**Files:**
- Modify: `projects/services/quotation_audit.py`

The `log_action` method currently validates `action` against choices. Add the new action types:
- `'cloned'`
- `'expired'`
- `'acceptance_link_sent'`
- `'client_responded'`

Check the service and ensure it accepts arbitrary action strings or add them to the choices list in the model.

### Task 20: Smoke test every new feature manually

```bash
# Start dev server
python manage.py runserver
```

Test checklist:
1. Create a quotation → verify cost table + client auto-fill at 26% markup
2. Change markup % → verify client rates update live
3. Set client rates below 15% markup → verify save blocked
4. Set client rates 15–25.99% → verify save works + status = pending_approval
5. Set client rates ≥26% → verify save works + status = draft
6. Director approves margin → verify status transitions back to draft
7. Send quotation → verify status = sent
8. Click "Mark Accepted" → verify status = accepted
9. Director clicks "Reopen as Draft" → verify status = draft
10. Director clicks "Void" → verify status = voided
11. Edit a "sent" quotation → verify revision snapshot created
12. View revision history on detail page → verify revision link works
13. Clone quotation → verify new quotation number, all data copied
14. Generate acceptance link → verify link works without login
15. Client accepts via link → verify status = accepted
16. Run `check_quotation_expiry` command → verify expired quotations handled
17. Open Dashboard → verify metrics show
18. Download PDF → verify NO vendor rates in output

---

## Notes

- **No git commit or push** without explicit user instruction.
- The `quotation_form.js` file path: check whether ERP serves static from `projects/static/projects/js/` or elsewhere. Run `python manage.py findstatic projects/js/quotation_form.js` to confirm.
- The `EXISTING_ITEMS_JSON` variable must be set in the template before the JS runs. The existing code in `quotation_create.html` already does this — preserve the pattern.
- The `QuotationAudit.ACTION_CHOICES` validation: if `log_action` enforces choices strictly, update both the model choices list AND re-run `makemigrations` for the `action` field change.
- UUID URLs: Django's `<uuid:token>` converter handles UUID format validation automatically.
