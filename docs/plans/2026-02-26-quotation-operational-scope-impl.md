# Quotation Operational Scope Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the `scope_of_service` checkbox section with a full "Operational Scope of Service" — multiple product/SKU rows with product dimensions, pallet planning calculations, and live JS summary. Calculations are backend-only; downloaded documents show product names, operation type, and billable area.

**Architecture:** New `QuotationProduct` model (FK → `Quotation`) stores per-SKU data. Operational summary fields (total boxes, variance, pallet dims) live on `Quotation`. All calculation logic is Python properties + mirrored in JavaScript for live UI feedback.

**Tech Stack:** Django 4.x, python-docx, Tailwind CSS, vanilla JS (existing project patterns)

---

## Task 1: Add `QuotationProduct` model + operational fields to `Quotation`

**Files:**
- Modify: `projects/models_quotation.py`

**Step 1: Remove `scope_of_service` field and add operational summary fields to `Quotation`**

In `projects/models_quotation.py`, find the `scope_of_service` field (around line 96-100):

```python
# Scope of Service (JSON array of selected services)
scope_of_service = models.JSONField(
    default=list,
    blank=True,
    help_text="Selected services from predefined options"
)
```

Replace it with:

```python
# Operational Scope of Service (replaces legacy scope_of_service checkboxes)
operational_total_boxes = models.DecimalField(
    max_digits=10, decimal_places=2,
    null=True, blank=True,
    help_text='Total boxes to be stored across all SKUs'
)
operational_variance_pct = models.DecimalField(
    max_digits=5, decimal_places=2,
    default=Decimal('30.00'),
    help_text='Batch management buffer percentage (default 30%)'
)
operational_pallet_l = models.DecimalField(
    max_digits=6, decimal_places=3,
    default=Decimal('3.330'),
    help_text='Pallet length in ft (default 3.33)'
)
operational_pallet_w = models.DecimalField(
    max_digits=6, decimal_places=3,
    default=Decimal('3.330'),
    help_text='Pallet width in ft (default 3.33)'
)
operational_pallet_h = models.DecimalField(
    max_digits=6, decimal_places=3,
    default=Decimal('4.000'),
    help_text='Pallet height in ft (default 4.00)'
)
```

**Step 2: Add computed operational properties to `Quotation`**

After the `margin_pct` property (around line 179-186), add:

```python
@property
def pallet_area_sqft(self):
    """Pallet floor area in sq.ft."""
    return self.operational_pallet_l * self.operational_pallet_w

@property
def pallet_volume_ft3(self):
    """Pallet volume in cubic feet."""
    return self.operational_pallet_l * self.operational_pallet_w * self.operational_pallet_h

@property
def total_pallets_required(self):
    """Sum of num_pallets across all SKUs. Returns None if any SKU is incomplete."""
    products = list(self.products.all())
    if not products:
        return None
    pallets = [p.num_pallets for p in products]
    if any(p is None for p in pallets):
        return None
    return sum(pallets)

@property
def actual_pallets_required(self):
    """total_pallets × (1 + variance_pct / 100)."""
    total = self.total_pallets_required
    if total is None:
        return None
    return total * (1 + self.operational_variance_pct / Decimal('100'))

@property
def billable_storage_area_sqft(self):
    """actual_pallets × 25 sq.ft."""
    actual = self.actual_pallets_required
    if actual is None:
        return None
    return actual * Decimal('25')
```

**Step 3: Add `QuotationProduct` model at the end of the file (before `QuotationAudit`)**

```python
class QuotationProduct(models.Model):
    """Per-SKU product data for Operational Scope of Service section."""

    BUSINESS_TYPE_CHOICES = [
        ('B2B', 'B2B'),
        ('B2C', 'B2C'),
    ]
    OPERATION_TYPE_CHOICES = [
        ('box_in_box_out', 'Box In – Box Out'),
        ('box_in_piece_out', 'Box In – Piece Out'),
        ('box_in_pallet_out', 'Box In – Pallet Out'),
        ('pallet_in_box_out', 'Pallet In – Box Out'),
    ]
    DIM_UNIT_CHOICES = [
        ('MM', 'MM'),
        ('CM', 'CM'),
        ('INCH', 'INCH'),
        ('FT', 'FT'),
    ]
    _UNIT_TO_FT = {
        'MM': Decimal('304.8'),
        'CM': Decimal('30.48'),
        'INCH': Decimal('12'),
        'FT': Decimal('1'),
    }

    product_id = models.AutoField(primary_key=True)
    quotation = models.ForeignKey(
        'Quotation',
        on_delete=models.CASCADE,
        related_name='products'
    )
    product_name = models.CharField(max_length=255)
    type_of_business = models.CharField(
        max_length=10,
        choices=BUSINESS_TYPE_CHOICES,
        default='B2B'
    )
    type_of_operation = models.CharField(
        max_length=30,
        choices=OPERATION_TYPE_CHOICES
    )
    packaging_type = models.CharField(max_length=100, blank=True)
    avg_weight_kg = models.DecimalField(
        max_digits=8, decimal_places=2,
        null=True, blank=True,
        help_text='Average box/bag/pallet weight in kg'
    )
    dim_l = models.DecimalField(max_digits=10, decimal_places=4)
    dim_w = models.DecimalField(max_digits=10, decimal_places=4)
    dim_h = models.DecimalField(max_digits=10, decimal_places=4)
    dim_unit = models.CharField(max_length=10, choices=DIM_UNIT_CHOICES, default='CM')
    share_pct = models.DecimalField(
        max_digits=6, decimal_places=2,
        default=Decimal('100.00'),
        help_text='% of total boxes this SKU represents (0–100)'
    )
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'quotation_product'
        ordering = ['quotation', 'order']

    def __str__(self):
        return f"{self.quotation.quotation_number} – {self.product_name}"

    def _to_ft(self, val):
        """Convert dimension value to feet."""
        divisor = self._UNIT_TO_FT.get(self.dim_unit, Decimal('1'))
        return val / divisor

    @property
    def dim_l_ft(self):
        return self._to_ft(self.dim_l)

    @property
    def dim_w_ft(self):
        return self._to_ft(self.dim_w)

    @property
    def dim_h_ft(self):
        return self._to_ft(self.dim_h)

    @property
    def volume_per_box_ft3(self):
        """Product box volume in cubic feet."""
        return self.dim_l_ft * self.dim_w_ft * self.dim_h_ft

    @property
    def boxes_per_pallet(self):
        """How many boxes fit per pallet."""
        vol = self.volume_per_box_ft3
        if vol == 0:
            return None
        pallet_vol = self.quotation.pallet_volume_ft3
        if not pallet_vol:
            return None
        return pallet_vol / vol

    @property
    def total_boxes(self):
        """Boxes for this SKU = total_boxes × share_pct / 100."""
        if self.quotation.operational_total_boxes is None:
            return None
        return self.quotation.operational_total_boxes * (self.share_pct / Decimal('100'))

    @property
    def num_pallets(self):
        """Pallets required for this SKU."""
        bpp = self.boxes_per_pallet
        tb = self.total_boxes
        if bpp is None or tb is None or bpp == 0:
            return None
        return tb / bpp
```

**Step 4: Update import in `models_quotation.py`**

The model imports `QuotationProduct` implicitly by being in the same file. But `views_quotation.py` will need to import it. No action needed here.

**Step 5: Run check**

```bash
cd /Users/apple/Documents/DataScienceProjects/ERP
python manage.py check
```

Expected: no errors (migration not yet applied, but model syntax check passes).

---

## Task 2: Create migration 0039

**Files:**
- Create: `projects/migrations/0039_quotation_operational_scope_product.py`

```bash
cd /Users/apple/Documents/DataScienceProjects/ERP
python manage.py makemigrations projects --name="quotation_operational_scope_product"
```

Verify the generated migration:
- `RemoveField('quotation', 'scope_of_service')`
- `AddField` × 5 on `Quotation` (operational_* fields)
- `CreateModel('QuotationProduct', ...)`

Apply migration:

```bash
python manage.py migrate projects
```

Expected: `OK` — migrates cleanly.

**Step: Commit**

```bash
git add projects/models_quotation.py projects/migrations/0039_quotation_operational_scope_product.py
git commit -m "feat: add QuotationProduct model and operational scope fields to Quotation"
```

---

## Task 3: Update forms

**Files:**
- Modify: `projects/forms_quotation.py`

**Step 1: Update imports at top of file**

After the existing `from projects.models_quotation import Quotation, QuotationLocation, QuotationItem` line, add `QuotationProduct`:

```python
from projects.models_quotation import Quotation, QuotationLocation, QuotationItem, QuotationProduct
```

**Step 2: Remove `scope_of_service` from `QuotationForm`**

In `QuotationForm.Meta.fields`, remove `'scope_of_service'` from the list.

In `QuotationForm.__init__`, remove the entire block that populates scope_of_service choices:
```python
# Remove this block:
# Populate scope of service choices from settings
scope_options = settings.scope_of_service_options
if scope_options:
    choices = [(option['id'], option['title']) for option in scope_options]
    self.fields['scope_of_service'] = forms.MultipleChoiceField(...)
```

**Step 3: Add operational fields to `QuotationForm.Meta.fields`**

In `QuotationForm.Meta.fields`, after the Quotation details block, add:

```python
# Operational Scope
'operational_total_boxes',
'operational_variance_pct',
'operational_pallet_l',
'operational_pallet_w',
'operational_pallet_h',
```

**Step 4: Add operational field widgets to `QuotationForm.Meta.widgets`**

```python
'operational_total_boxes': forms.NumberInput(attrs={
    'class': INPUT_CLASSES,
    'step': '1', 'min': '1',
    'placeholder': 'Total boxes to be stored'
}),
'operational_variance_pct': forms.NumberInput(attrs={
    'class': INPUT_CLASSES,
    'step': '0.01', 'min': '0', 'max': '100',
}),
'operational_pallet_l': forms.NumberInput(attrs={
    'class': INPUT_CLASSES,
    'step': '0.001', 'min': '0.001',
}),
'operational_pallet_w': forms.NumberInput(attrs={
    'class': INPUT_CLASSES,
    'step': '0.001', 'min': '0.001',
}),
'operational_pallet_h': forms.NumberInput(attrs={
    'class': INPUT_CLASSES,
    'step': '0.001', 'min': '0.001',
}),
```

**Step 5: Add `QuotationProductForm` class**

After `QuotationItemForm`, add:

```python
class QuotationProductForm(forms.ModelForm):
    """Form for each product/SKU in the Operational Scope section."""

    class Meta:
        model = QuotationProduct
        fields = [
            'product_name', 'type_of_business', 'type_of_operation',
            'packaging_type', 'avg_weight_kg',
            'dim_l', 'dim_w', 'dim_h', 'dim_unit',
            'share_pct', 'order',
        ]
        widgets = {
            'product_name': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'e.g. Baby Diapers, Electronics',
                'required': True
            }),
            'type_of_business': forms.Select(attrs={'class': SELECT_CLASSES}),
            'type_of_operation': forms.Select(attrs={'class': SELECT_CLASSES}),
            'packaging_type': forms.TextInput(attrs={
                'class': INPUT_CLASSES,
                'placeholder': 'e.g. Carton, Polybag, Drum'
            }),
            'avg_weight_kg': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01', 'min': '0', 'placeholder': 'kg'
            }),
            'dim_l': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.0001', 'min': '0.0001', 'placeholder': 'Length'
            }),
            'dim_w': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.0001', 'min': '0.0001', 'placeholder': 'Width'
            }),
            'dim_h': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.0001', 'min': '0.0001', 'placeholder': 'Height'
            }),
            'dim_unit': forms.Select(attrs={'class': SELECT_CLASSES}),
            'share_pct': forms.NumberInput(attrs={
                'class': INPUT_CLASSES,
                'step': '0.01', 'min': '0', 'max': '100', 'placeholder': '100'
            }),
            'order': forms.NumberInput(attrs={
                'class': INPUT_CLASSES + ' w-16', 'min': '0', 'value': '0'
            }),
        }

    def clean_share_pct(self):
        val = self.cleaned_data.get('share_pct')
        if val is not None and (val < 0 or val > 100):
            raise forms.ValidationError('Share % must be between 0 and 100.')
        return val

    def clean(self):
        cleaned = super().clean()
        for field in ('dim_l', 'dim_w', 'dim_h'):
            val = cleaned.get(field)
            if val is not None and val <= 0:
                self.add_error(field, 'Dimension must be greater than zero.')
        return cleaned
```

**Step 6: Add `QuotationProductFormSet` at the bottom of the file**

After `QuotationItemFormSet`, add:

```python
QuotationProductFormSet = inlineformset_factory(
    Quotation,
    QuotationProduct,
    form=QuotationProductForm,
    extra=0,
    can_delete=True,
    min_num=0,
    max_num=20,
)
```

**Step 7: Commit**

```bash
git add projects/forms_quotation.py
git commit -m "feat: add QuotationProductForm and QuotationProductFormSet; remove scope_of_service"
```

---

## Task 4: Update views

**Files:**
- Modify: `projects/views_quotation.py`

**Step 1: Update model import (line 20)**

```python
from projects.models_quotation import Quotation, QuotationLocation, QuotationItem, QuotationAudit, QuotationProduct
```

**Step 2: Update form import (line 22-25)**

```python
from projects.forms_quotation import (
    QuotationForm, QuotationLocationFormSet, QuotationItemFormSet,
    QuotationProductFormSet, QuotationSettingsForm, EmailQuotationForm
)
```

**Step 3: Add product formset helpers after `_build_items_json_from_post` (around line 240)**

```python
def _collect_product_formset(request, quotation=None):
    """Collect product formset from POST data."""
    if quotation and quotation.pk:
        return QuotationProductFormSet(request.POST, prefix='products', instance=quotation)
    return QuotationProductFormSet(request.POST, prefix='products')


def _build_existing_products_json(quotation):
    """Build JSON list of existing products for template pre-population."""
    if not quotation or not quotation.pk:
        return '[]'
    products = quotation.products.all().order_by('order')
    return json.dumps([
        {
            'id': p.pk,
            'product_name': p.product_name,
            'type_of_business': p.type_of_business,
            'type_of_operation': p.type_of_operation,
            'packaging_type': p.packaging_type or '',
            'avg_weight_kg': str(p.avg_weight_kg) if p.avg_weight_kg else '',
            'dim_l': str(p.dim_l),
            'dim_w': str(p.dim_w),
            'dim_h': str(p.dim_h),
            'dim_unit': p.dim_unit,
            'share_pct': str(p.share_pct),
            'order': p.order,
        }
        for p in products
    ])


def _build_products_json_from_post(request):
    """Reconstruct products JSON from POST data (for re-render on validation failure)."""
    total = int(request.POST.get('products-TOTAL_FORMS', 0))
    products = []
    for i in range(total):
        p = f'products-{i}'
        name = request.POST.get(f'{p}-product_name', '')
        if not name:
            continue
        products.append({
            'id': request.POST.get(f'{p}-id', ''),
            'product_name': name,
            'type_of_business': request.POST.get(f'{p}-type_of_business', 'B2B'),
            'type_of_operation': request.POST.get(f'{p}-type_of_operation', ''),
            'packaging_type': request.POST.get(f'{p}-packaging_type', ''),
            'avg_weight_kg': request.POST.get(f'{p}-avg_weight_kg', ''),
            'dim_l': request.POST.get(f'{p}-dim_l', ''),
            'dim_w': request.POST.get(f'{p}-dim_w', ''),
            'dim_h': request.POST.get(f'{p}-dim_h', ''),
            'dim_unit': request.POST.get(f'{p}-dim_unit', 'CM'),
            'share_pct': request.POST.get(f'{p}-share_pct', '100'),
            'order': request.POST.get(f'{p}-order', str(i)),
        })
    return json.dumps(products)
```

**Step 4: Update `quotation_create` view**

In `quotation_create`, after `location_formset = QuotationLocationFormSet(...)` (POST branch), add:

```python
product_formset = _collect_product_formset(request)
```

Then include it in the `all_valid` check:

```python
all_valid = form.is_valid() and location_formset.is_valid() and product_formset.is_valid()
```

After `quotation.save()` + location/item save, add:

```python
# Save product SKU rows
product_formset.instance = quotation
product_formset.save()
```

In the GET branch, add:

```python
product_formset = QuotationProductFormSet(prefix='products')
```

In the context dict, add:

```python
'product_formset': product_formset,
'existing_products_json': _build_products_json_from_post(request) if request.method == 'POST' else '[]',
'product_business_choices': QuotationProduct.BUSINESS_TYPE_CHOICES,
'product_operation_choices': QuotationProduct.OPERATION_TYPE_CHOICES,
'product_dim_unit_choices': QuotationProduct.DIM_UNIT_CHOICES,
```

Also in the early-return (margin validation failure) context, add these same keys.

**Step 5: Update `quotation_edit` view**

Same changes as create but using instance:

POST branch:
```python
product_formset = _collect_product_formset(request, quotation=quotation)
```

GET branch:
```python
product_formset = QuotationProductFormSet(instance=quotation, prefix='products')
```

After saving locations/items in POST:
```python
product_formset.instance = quotation
product_formset.save()
```

Context:
```python
'product_formset': product_formset,
'existing_products_json': _build_products_json_from_post(request) if request.method == 'POST' else _build_existing_products_json(quotation),
'product_business_choices': QuotationProduct.BUSINESS_TYPE_CHOICES,
'product_operation_choices': QuotationProduct.OPERATION_TYPE_CHOICES,
'product_dim_unit_choices': QuotationProduct.DIM_UNIT_CHOICES,
```

**Step 6: Update `quotation_detail` view**

Remove the old `scope_services` block (lines 122-130):

```python
# DELETE these lines:
scope_services = []
if quotation.scope_of_service:
    settings = QuotationSettings.get_settings()
    options_map = {opt['id']: opt for opt in (settings.scope_of_service_options or [])}
    for service_id in quotation.scope_of_service:
        opt = options_map.get(service_id)
        if opt:
            scope_services.append(opt)
```

Update the prefetch in `quotation_detail` to include products:

```python
quotation = get_object_or_404(
    Quotation.objects.select_related('created_by').prefetch_related(
        'locations__items',
        'products',
        'audit_logs__user'
    ),
    quotation_id=quotation_id
)
```

Remove `'scope_services': scope_services,` from context dict.

**Step 7: Run check + commit**

```bash
python manage.py check
```

```bash
git add projects/views_quotation.py
git commit -m "feat: integrate QuotationProductFormSet into create/edit/detail views"
```

---

## Task 5: Update `quotation_create.html` — Operational Scope section

**Files:**
- Modify: `templates/projects/quotations/quotation_create.html`

**Step 1: Add Operational Scope section between Section 2 (Quotation Details) and Section 3 (Locations & Items)**

Find the comment `<!-- Section 3: Locations & Items (Dynamic Formsets) -->` at line 161.
Insert the following block **before** it:

```html
        <!-- Section 3: Operational Scope of Service -->
        <div class="bg-white shadow rounded-lg p-6" id="operational-scope-section">
            <h2 class="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <svg width="20" height="20" aria-hidden="true" class="h-5 w-5 text-blue-600 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/>
                </svg>
                Operational Scope of Service
            </h2>

            <!-- Pallet & Summary Inputs -->
            <div class="grid grid-cols-2 gap-6 mb-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
                <div>
                    <h3 class="text-sm font-semibold text-blue-800 mb-3">Storage Configuration</h3>
                    <div class="grid grid-cols-2 gap-3">
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Total Boxes to Store</label>
                            {{ form.operational_total_boxes }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Variance % (buffer)</label>
                            {{ form.operational_variance_pct }}
                        </div>
                    </div>
                </div>
                <div>
                    <h3 class="text-sm font-semibold text-blue-800 mb-3">Pallet Dimensions (ft) — Standard: 3.33 × 3.33 × 4.00</h3>
                    <div class="grid grid-cols-3 gap-3">
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Length (ft)</label>
                            {{ form.operational_pallet_l }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Width (ft)</label>
                            {{ form.operational_pallet_w }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Height (ft)</label>
                            {{ form.operational_pallet_h }}
                        </div>
                    </div>
                </div>
            </div>

            <!-- Product Formset Management Form -->
            {{ product_formset.management_form }}

            <!-- Product Rows -->
            <div id="product-rows-container" class="space-y-4 mb-4">
                {% for product_form in product_formset %}
                <div class="product-row border border-gray-200 rounded-lg p-4 bg-gray-50 relative" data-product-index="{{ forloop.counter0 }}">
                    <div class="hidden">
                        {{ product_form.id }}
                        {{ product_form.DELETE }}
                        {{ product_form.order }}
                    </div>
                    <div class="flex items-center justify-between mb-3">
                        <span class="text-sm font-semibold text-gray-700">SKU {{ forloop.counter }}</span>
                        <button type="button" class="delete-product-row text-xs px-2 py-1 bg-red-100 text-red-600 rounded hover:bg-red-200">Remove</button>
                    </div>
                    <div class="grid grid-cols-6 gap-3 mb-3">
                        <div class="col-span-2">
                            <label class="block text-xs font-medium text-gray-700 mb-1">Product Name <span class="text-red-500">*</span></label>
                            {{ product_form.product_name }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Type of Business</label>
                            {{ product_form.type_of_business }}
                        </div>
                        <div class="col-span-2">
                            <label class="block text-xs font-medium text-gray-700 mb-1">Type of Operation</label>
                            {{ product_form.type_of_operation }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Packaging Type</label>
                            {{ product_form.packaging_type }}
                        </div>
                    </div>
                    <div class="grid grid-cols-7 gap-3">
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Avg Weight (kg)</label>
                            {{ product_form.avg_weight_kg }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Length</label>
                            {{ product_form.dim_l }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Width</label>
                            {{ product_form.dim_w }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Height</label>
                            {{ product_form.dim_h }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Unit</label>
                            {{ product_form.dim_unit }}
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-gray-700 mb-1">Share %</label>
                            {{ product_form.share_pct }}
                        </div>
                        <!-- Computed display (read-only) -->
                        <div>
                            <label class="block text-xs font-medium text-gray-500 mb-1">Pallets (calc)</label>
                            <input type="text" readonly class="product-pallets-display w-full px-2 py-2 bg-gray-100 border border-gray-200 rounded text-xs text-gray-600" value="—">
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>

            <!-- Add Product Button -->
            <button type="button" id="add-product-row"
                    class="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 transition">
                + Add Product / SKU
            </button>

            <!-- Live Summary Panel -->
            <div class="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-lg" id="operational-summary">
                <h3 class="text-sm font-semibold text-amber-800 mb-3">Pallet Planning Summary</h3>
                <div class="grid grid-cols-4 gap-4 text-center">
                    <div>
                        <p class="text-xs text-gray-500">Pallet Volume</p>
                        <p class="text-lg font-bold text-gray-800" id="summary-pallet-vol">—</p>
                        <p class="text-xs text-gray-400">ft³</p>
                    </div>
                    <div>
                        <p class="text-xs text-gray-500">Total Pallets</p>
                        <p class="text-lg font-bold text-gray-800" id="summary-total-pallets">—</p>
                    </div>
                    <div>
                        <p class="text-xs text-gray-500">Actual Pallets (with variance)</p>
                        <p class="text-lg font-bold text-blue-700" id="summary-actual-pallets">—</p>
                    </div>
                    <div>
                        <p class="text-xs text-gray-500">Billable Storage Area</p>
                        <p class="text-xl font-bold text-green-700" id="summary-billable-area">—</p>
                        <p class="text-xs text-gray-400">sq.ft</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Hidden product row template for JS cloning -->
        <template id="product-row-template">
            <div class="product-row border border-gray-200 rounded-lg p-4 bg-gray-50 relative" data-product-index="__IDX__">
                <div class="hidden">
                    <input type="hidden" name="products-__IDX__-id" value="">
                    <input type="hidden" name="products-__IDX__-DELETE" value="">
                    <input type="hidden" name="products-__IDX__-order" value="__IDX__">
                </div>
                <div class="flex items-center justify-between mb-3">
                    <span class="text-sm font-semibold text-gray-700">SKU <span class="sku-number">__NUM__</span></span>
                    <button type="button" class="delete-product-row text-xs px-2 py-1 bg-red-100 text-red-600 rounded hover:bg-red-200">Remove</button>
                </div>
                <div class="grid grid-cols-6 gap-3 mb-3">
                    <div class="col-span-2">
                        <label class="block text-xs font-medium text-gray-700 mb-1">Product Name <span class="text-red-500">*</span></label>
                        <input type="text" name="products-__IDX__-product_name" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent" placeholder="e.g. Baby Diapers">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-700 mb-1">Type of Business</label>
                        <select name="products-__IDX__-type_of_business" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                            {% for val, label in product_business_choices %}<option value="{{ val }}">{{ label }}</option>{% endfor %}
                        </select>
                    </div>
                    <div class="col-span-2">
                        <label class="block text-xs font-medium text-gray-700 mb-1">Type of Operation</label>
                        <select name="products-__IDX__-type_of_operation" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                            <option value="">— Select —</option>
                            {% for val, label in product_operation_choices %}<option value="{{ val }}">{{ label }}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-700 mb-1">Packaging Type</label>
                        <input type="text" name="products-__IDX__-packaging_type" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent" placeholder="e.g. Carton">
                    </div>
                </div>
                <div class="grid grid-cols-7 gap-3">
                    <div>
                        <label class="block text-xs font-medium text-gray-700 mb-1">Avg Weight (kg)</label>
                        <input type="number" name="products-__IDX__-avg_weight_kg" step="0.01" min="0" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent" placeholder="kg">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-700 mb-1">Length</label>
                        <input type="number" name="products-__IDX__-dim_l" step="0.0001" min="0.0001" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent product-dim" placeholder="L">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-700 mb-1">Width</label>
                        <input type="number" name="products-__IDX__-dim_w" step="0.0001" min="0.0001" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent product-dim" placeholder="W">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-700 mb-1">Height</label>
                        <input type="number" name="products-__IDX__-dim_h" step="0.0001" min="0.0001" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent product-dim" placeholder="H">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-700 mb-1">Unit</label>
                        <select name="products-__IDX__-dim_unit" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent product-dim-unit">
                            {% for val, label in product_dim_unit_choices %}<option value="{{ val }}"{% if val == 'CM' %} selected{% endif %}>{{ label }}</option>{% endfor %}
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-700 mb-1">Share %</label>
                        <input type="number" name="products-__IDX__-share_pct" step="0.01" min="0" max="100" value="100" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent product-share">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 mb-1">Pallets (calc)</label>
                        <input type="text" readonly class="product-pallets-display w-full px-2 py-2 bg-gray-100 border border-gray-200 rounded text-xs text-gray-600" value="—">
                    </div>
                </div>
            </div>
        </template>
```

**Step 2: Add `existing_products_json` hidden input (near existing `existing_items_json` hidden input)**

Find where `existing_items_json` is used in the template. Add just below it:

```html
<div id="existing-products-json" class="hidden">{{ existing_products_json|escapejs }}</div>
```

**Step 3: Add operational scope JS to the `<script>` block**

Find the `<script>` section in `quotation_create.html` (near end of file). Add these functions:

```javascript
// ================================================================
// OPERATIONAL SCOPE — Pallet Calculator
// ================================================================

const DIM_DIVISORS = { 'MM': 304.8, 'CM': 30.48, 'INCH': 12, 'FT': 1 };

function toFt(val, unit) {
    const divisor = DIM_DIVISORS[unit] || 1;
    return val / divisor;
}

function getPalletVolume() {
    const L = parseFloat(document.getElementById('id_operational_pallet_l')?.value) || 3.33;
    const W = parseFloat(document.getElementById('id_operational_pallet_w')?.value) || 3.33;
    const H = parseFloat(document.getElementById('id_operational_pallet_h')?.value) || 4.0;
    return L * W * H;
}

function calcProductPallets(row) {
    const totalBoxes = parseFloat(document.getElementById('id_operational_total_boxes')?.value) || 0;
    const share = parseFloat(row.querySelector('[name$="-share_pct"]')?.value) || 100;
    const dimL = parseFloat(row.querySelector('[name$="-dim_l"]')?.value) || 0;
    const dimW = parseFloat(row.querySelector('[name$="-dim_w"]')?.value) || 0;
    const dimH = parseFloat(row.querySelector('[name$="-dim_h"]')?.value) || 0;
    const unit = row.querySelector('[name$="-dim_unit"]')?.value || 'CM';

    if (!totalBoxes || !dimL || !dimW || !dimH) return null;

    const lFt = toFt(dimL, unit);
    const wFt = toFt(dimW, unit);
    const hFt = toFt(dimH, unit);
    const volPerBox = lFt * wFt * hFt;
    if (volPerBox <= 0) return null;

    const palletVol = getPalletVolume();
    const boxesPerPallet = palletVol / volPerBox;
    if (boxesPerPallet <= 0) return null;

    const skuBoxes = totalBoxes * (share / 100);
    return skuBoxes / boxesPerPallet;
}

function updateOperationalSummary() {
    const variance = parseFloat(document.getElementById('id_operational_variance_pct')?.value) || 30;
    const palletVol = getPalletVolume();

    document.getElementById('summary-pallet-vol').textContent = palletVol.toFixed(2);

    let totalPallets = 0;
    let allValid = true;
    const rows = document.querySelectorAll('.product-row:not([data-deleted="true"])');

    rows.forEach(row => {
        const pallets = calcProductPallets(row);
        const display = row.querySelector('.product-pallets-display');
        if (pallets !== null) {
            if (display) display.value = pallets.toFixed(1);
            totalPallets += pallets;
        } else {
            if (display) display.value = '—';
            if (row.querySelector('[name$="-product_name"]')?.value) allValid = false;
        }
    });

    if (rows.length === 0 || !allValid) {
        document.getElementById('summary-total-pallets').textContent = '—';
        document.getElementById('summary-actual-pallets').textContent = '—';
        document.getElementById('summary-billable-area').textContent = '—';
        return;
    }

    const actualPallets = totalPallets * (1 + variance / 100);
    const billableArea = actualPallets * 25;

    document.getElementById('summary-total-pallets').textContent = totalPallets.toFixed(1);
    document.getElementById('summary-actual-pallets').textContent = actualPallets.toFixed(1);
    document.getElementById('summary-billable-area').textContent = Math.ceil(billableArea).toLocaleString('en-IN');
}

// Wire up listeners for summary inputs
['id_operational_total_boxes', 'id_operational_variance_pct',
 'id_operational_pallet_l', 'id_operational_pallet_w', 'id_operational_pallet_h'
].forEach(id => {
    document.getElementById(id)?.addEventListener('input', updateOperationalSummary);
});

// Delegate listeners for product row inputs
document.getElementById('product-rows-container')?.addEventListener('input', updateOperationalSummary);

// Add product row button
let productRowCount = {{ product_formset.total_form_count }};
document.getElementById('add-product-row')?.addEventListener('click', function() {
    const template = document.getElementById('product-row-template');
    if (!template) return;
    const html = template.innerHTML
        .replace(/__IDX__/g, productRowCount)
        .replace(/__NUM__/g, productRowCount + 1);
    const container = document.getElementById('product-rows-container');
    container.insertAdjacentHTML('beforeend', html);
    productRowCount++;
    document.getElementById('id_products-TOTAL_FORMS').value = productRowCount;
    updateOperationalSummary();
});

// Delete product row button (delegated)
document.getElementById('product-rows-container')?.addEventListener('click', function(e) {
    if (!e.target.classList.contains('delete-product-row')) return;
    const row = e.target.closest('.product-row');
    if (!row) return;
    const deleteInput = row.querySelector('input[name$="-DELETE"]');
    if (deleteInput) {
        deleteInput.value = 'on';
        row.style.display = 'none';
        row.dataset.deleted = 'true';
    } else {
        row.remove();
        productRowCount--;
        document.getElementById('id_products-TOTAL_FORMS').value = productRowCount;
    }
    updateOperationalSummary();
});

// Initial summary calculation
updateOperationalSummary();
```

**Step 4: Commit**

```bash
git add templates/projects/quotations/quotation_create.html
git commit -m "feat: add Operational Scope section to quotation create/edit template with live pallet calculator"
```

---

## Task 6: Update `quotation_detail.html`

**Files:**
- Modify: `templates/projects/quotations/quotation_detail.html`

**Step 1: Replace old scope_of_service section (lines 229-253)**

Find and replace:

```html
    <!-- Scope of Service -->
    {% if quotation.scope_of_service %}
    <div class="bg-white shadow rounded-lg p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Scope of Service</h2>
        <div class="grid grid-cols-2 gap-4">
            {% for service in scope_services %}
            <div class="flex items-start gap-2 p-3 bg-gray-50 rounded-lg">
                <svg width="20" height="20" aria-hidden="true" class="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                <div>
                    <p class="text-sm font-medium text-gray-900">{{ service.title }}</p>
                    {% if service.points %}
                    <ul class="mt-1 text-xs text-gray-500 space-y-0.5">
                        {% for point in service.points %}
                        <li>{{ point }}</li>
                        {% endfor %}
                    </ul>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}
```

With:

```html
    <!-- Operational Scope of Service -->
    {% with products=quotation.products.all %}
    {% if products or quotation.operational_total_boxes %}
    <div class="bg-white shadow rounded-lg p-6">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Operational Scope of Service</h2>

        <!-- Configuration summary -->
        <div class="grid grid-cols-3 gap-4 mb-4 p-3 bg-blue-50 rounded-lg text-sm">
            <div>
                <span class="text-gray-500">Total Boxes:</span>
                <span class="font-semibold ml-1">{{ quotation.operational_total_boxes|default:"—" }}</span>
            </div>
            <div>
                <span class="text-gray-500">Variance:</span>
                <span class="font-semibold ml-1">{{ quotation.operational_variance_pct }}%</span>
            </div>
            <div>
                <span class="text-gray-500">Pallet Dims (ft):</span>
                <span class="font-semibold ml-1">{{ quotation.operational_pallet_l }} × {{ quotation.operational_pallet_w }} × {{ quotation.operational_pallet_h }}</span>
            </div>
        </div>

        <!-- Product rows -->
        {% if products %}
        <table class="min-w-full divide-y divide-gray-200 mb-4">
            <thead class="bg-gray-50">
                <tr>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Product</th>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Business</th>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Operation</th>
                    <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Packaging</th>
                    <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Share %</th>
                    <th class="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase">Pallets</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
                {% for product in products %}
                <tr>
                    <td class="px-3 py-2 text-sm font-medium text-gray-900">{{ product.product_name }}</td>
                    <td class="px-3 py-2 text-sm text-gray-500">{{ product.type_of_business }}</td>
                    <td class="px-3 py-2 text-sm text-gray-500">{{ product.get_type_of_operation_display }}</td>
                    <td class="px-3 py-2 text-sm text-gray-500">{{ product.packaging_type|default:"—" }}</td>
                    <td class="px-3 py-2 text-sm text-gray-900 text-right">{{ product.share_pct }}%</td>
                    <td class="px-3 py-2 text-sm font-semibold text-gray-900 text-right">
                        {% if product.num_pallets %}{{ product.num_pallets|floatformat:1 }}{% else %}—{% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endif %}

        <!-- Summary -->
        {% if quotation.billable_storage_area_sqft %}
        <div class="grid grid-cols-3 gap-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-center">
            <div>
                <p class="text-xs text-gray-500">Total Pallets</p>
                <p class="text-lg font-bold text-gray-800">{{ quotation.total_pallets_required|floatformat:1|default:"—" }}</p>
            </div>
            <div>
                <p class="text-xs text-gray-500">Actual Pallets (with {{ quotation.operational_variance_pct }}% buffer)</p>
                <p class="text-lg font-bold text-blue-700">{{ quotation.actual_pallets_required|floatformat:1|default:"—" }}</p>
            </div>
            <div>
                <p class="text-xs text-gray-500">Billable Storage Area</p>
                <p class="text-xl font-bold text-green-700">{{ quotation.billable_storage_area_sqft|floatformat:0 }} sq.ft</p>
            </div>
        </div>
        {% endif %}
    </div>
    {% endif %}
    {% endwith %}
```

**Step 2: Commit**

```bash
git add templates/projects/quotations/quotation_detail.html
git commit -m "feat: replace scope_of_service display with Operational Scope of Service on quotation detail"
```

---

## Task 7: Update DOCX generator

**Files:**
- Modify: `projects/services/quotation_docx_local.py`

**Step 1: Replace `_build_scope_elements` method**

Find the existing `_build_scope_elements` method (around line 519-554) and replace it entirely:

```python
def _build_scope_elements(self, proto_heading, proto_bullet, original_heading_elem):
    """Build Operational Scope of Service elements for the DOCX.

    Shows: product names + type of operation + billable storage area.
    Does NOT show: dimensions, unit conversions, or intermediate calculations.
    """
    q = self.quotation
    products = list(q.products.all().order_by('order'))

    elements = []

    if products:
        for idx, product in enumerate(products, 1):
            # Heading: "1. Product Name (Operation Type)"
            heading = _clone_element(proto_heading)
            texts = heading.findall('.//' + qn('w:t'))
            op_label = dict(product.OPERATION_TYPE_CHOICES).get(product.type_of_operation, product.type_of_operation)
            heading_text = f'{idx}. {product.product_name} ({op_label})'
            if texts:
                texts[0].text = heading_text
                texts[0].set(qn('xml:space'), 'preserve')
                for t in texts[1:]:
                    t.text = ''
            elements.append(heading)

            # Bullet: Packaging Type (if set)
            if product.packaging_type:
                bullet = _clone_element(proto_bullet)
                texts = bullet.findall('.//' + qn('w:t'))
                if texts:
                    texts[0].text = f'Packaging: {product.packaging_type}'
                    texts[0].set(qn('xml:space'), 'preserve')
                    for t in texts[1:]:
                        t.text = ''
                elements.append(bullet)

            # Bullet: Type of business
            bullet = _clone_element(proto_bullet)
            texts = bullet.findall('.//' + qn('w:t'))
            if texts:
                texts[0].text = f'Business Type: {product.type_of_business}'
                texts[0].set(qn('xml:space'), 'preserve')
                for t in texts[1:]:
                    t.text = ''
            elements.append(bullet)

    # Final bullet: Billable Storage Area
    billable = q.billable_storage_area_sqft
    if billable is not None:
        bullet = _clone_element(proto_bullet)
        texts = bullet.findall('.//' + qn('w:t'))
        area_text = f'Billable / Storage Area: {int(billable):,} sq.ft'
        if texts:
            texts[0].text = area_text
            texts[0].set(qn('xml:space'), 'preserve')
            for t in texts[1:]:
                t.text = ''
        elements.append(bullet)

    return elements
```

**Step 2: Commit**

```bash
git add projects/services/quotation_docx_local.py
git commit -m "feat: update DOCX generator to show product names, operation type, and billable area in scope section"
```

---

## Task 8: Update test quotation management command

**Files:**
- Modify: `projects/management/commands/create_test_quotation.py`

**Step 1: Update imports in `handle` method**

Change:

```python
from projects.models_quotation import Quotation, QuotationLocation, QuotationItem
```

To:

```python
from projects.models_quotation import Quotation, QuotationLocation, QuotationItem, QuotationProduct
```

**Step 2: Add products to Scenario 1 (FreshMart)**

After `loc = QuotationLocation.objects.create(...)` and the `bulk_create` for items in `_create_good_margin_quotation`, add:

```python
# Add product SKU rows
QuotationProduct.objects.create(
    quotation=q,
    product_name='FMCG Cartons',
    type_of_business='B2B',
    type_of_operation='box_in_box_out',
    packaging_type='Carton',
    avg_weight_kg=Decimal('12.5'),
    dim_l=Decimal('45'), dim_w=Decimal('30'), dim_h=Decimal('25'), dim_unit='CM',
    share_pct=Decimal('60.00'),
    order=0,
)
QuotationProduct.objects.create(
    quotation=q,
    product_name='Pharma Units',
    type_of_business='B2B',
    type_of_operation='box_in_piece_out',
    packaging_type='Polybag',
    avg_weight_kg=Decimal('2.0'),
    dim_l=Decimal('20'), dim_w=Decimal('15'), dim_h=Decimal('10'), dim_unit='CM',
    share_pct=Decimal('40.00'),
    order=1,
)
# Set operational totals
q.operational_total_boxes = Decimal('10000')
q.operational_variance_pct = Decimal('30.00')
q.save(update_fields=['operational_total_boxes', 'operational_variance_pct'])
```

**Step 3: Add same for Scenario 2 + 3 (abbreviated, single product)**

In `_create_pending_approval_quotation`, after items bulk_create:

```python
QuotationProduct.objects.create(
    quotation=q,
    product_name='Freight Goods',
    type_of_business='B2B',
    type_of_operation='pallet_in_box_out',
    packaging_type='Pallet',
    dim_l=Decimal('100'), dim_w=Decimal('80'), dim_h=Decimal('120'), dim_unit='CM',
    share_pct=Decimal('100.00'),
    order=0,
)
q.operational_total_boxes = Decimal('5000')
q.save(update_fields=['operational_total_boxes'])
```

In `_create_director_approved_quotation`, after items bulk_create:

```python
QuotationProduct.objects.create(
    quotation=q,
    product_name='Retail Apparel',
    type_of_business='B2C',
    type_of_operation='box_in_piece_out',
    packaging_type='Polybag',
    dim_l=Decimal('50'), dim_w=Decimal('40'), dim_h=Decimal('30'), dim_unit='CM',
    share_pct=Decimal('100.00'),
    order=0,
)
q.operational_total_boxes = Decimal('7500')
q.save(update_fields=['operational_total_boxes'])
```

**Step 4: Commit**

```bash
git add projects/management/commands/create_test_quotation.py
git commit -m "feat: add QuotationProduct rows to test quotation scenarios"
```

---

## Task 9: Verification

**Step 1: Django system check**

```bash
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

**Step 2: Run CI tests**

```bash
python manage.py test tests/test_ci_pipeline.py --keepdb -v 2
```

Expected: All tests pass (9/9 or similar).

**Step 3: Run test quotation command**

```bash
python manage.py create_test_quotation
```

Expected output includes billable area in each scenario.

**Step 4: Spot-check the DOCX**

Open a test quotation in the UI, click Download DOCX, verify:
- Shows product names + operation type under SCOPE OF SERVICE
- Shows billable area
- Does NOT show dimensions or calculations

**Step 5: Final commit**

```bash
git add .
git commit -m "feat: complete Operational Scope of Service implementation with pallet calculator"
```
