# Transport Projectwise Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Redesign the transport expenses project-wise view to group by (client_name, transporter_name) pairs showing Charges@GW, Charges@Client, and Margin% for Approved expenses only.

**Architecture:** Rewrite the view to filter Approved-only expenses, group by (client_name, transporter_name), sum charges_at_gw and charges_at_client, compute margin. Rewrite the template to show the new 5-column table with a Total row at top, 3 summary cards, and month + search filters only.

**Tech Stack:** Django, Python, Tailwind CSS (existing project stack)

---

### Task 1: Rewrite the view `transport_expenses_projectwise`

**Files:**
- Modify: `integrations/expense_log/views.py` lines 704–837

**Step 1: Replace the entire view function body**

Find the function starting at line 704 and replace its body with the following:

```python
@login_required
def transport_expenses_projectwise(request):
    """
    Transport expenses grouped by (client_name, transporter_name).
    Only Approved expenses. Shows Charges@GW, Charges@Client, Margin%.
    """
    from django.db.models import Q
    from decimal import Decimal
    from datetime import datetime
    from collections import defaultdict

    # Filters
    current_month = datetime.now().strftime('%B %Y')
    month_filter = request.GET.get('month', current_month)
    search_query = request.GET.get('search', '').strip()

    # Base queryset: transport expenses, Approved only
    transport_expenses = ExpenseRecord.get_expenses_for_user(request.user).filter(
        Q(nature_of_expense__icontains='transport') |
        Q(raw_data__Transport__isnull=False)
    ).exclude(
        client_name__isnull=True
    ).exclude(
        client_name=''
    ).filter(
        approval_status='Approved'
    )

    if month_filter:
        transport_expenses = transport_expenses.filter(service_month=month_filter)

    if search_query:
        transport_expenses = transport_expenses.filter(
            Q(client_name__icontains=search_query) |
            Q(transporter_name__icontains=search_query)
        )

    # Group by (client_name, transporter_name)
    rows_data = defaultdict(lambda: {
        'client_name': '',
        'transporter_name': '',
        'charges_at_gw': Decimal('0'),
        'charges_at_client': Decimal('0'),
    })

    for expense in transport_expenses:
        key = (expense.client_name, expense.transporter_name or '-')
        rows_data[key]['client_name'] = expense.client_name
        rows_data[key]['transporter_name'] = expense.transporter_name or '-'
        rows_data[key]['charges_at_gw'] += expense.charges_at_gw or Decimal('0')
        rows_data[key]['charges_at_client'] += expense.charges_at_client or Decimal('0')

    # Compute margin per row
    rows = []
    for row in rows_data.values():
        gw = row['charges_at_gw']
        client = row['charges_at_client']
        if client > 0:
            margin = ((client - gw) / client) * 100
        else:
            margin = Decimal('0')
        rows.append({
            'client_name': row['client_name'],
            'transporter_name': row['transporter_name'],
            'charges_at_gw': gw,
            'charges_at_client': client,
            'margin': margin,
        })

    # Sort by charges_at_gw descending
    rows = sorted(rows, key=lambda x: x['charges_at_gw'], reverse=True)

    # Totals
    total_gw = sum(r['charges_at_gw'] for r in rows)
    total_client = sum(r['charges_at_client'] for r in rows)
    total_margin = ((total_client - total_gw) / total_client * 100) if total_client > 0 else Decimal('0')
    total_rows = len(rows)

    # Distinct months for dropdown (all transport expenses, not filtered)
    distinct_months = ExpenseRecord.get_expenses_for_user(request.user).filter(
        Q(nature_of_expense__icontains='transport') |
        Q(raw_data__Transport__isnull=False)
    ).exclude(
        service_month__isnull=True
    ).exclude(
        service_month=''
    ).values_list('service_month', flat=True).distinct().order_by('-service_month')

    context = {
        'rows': rows,
        'total_gw': total_gw,
        'total_client': total_client,
        'total_margin': total_margin,
        'total_rows': total_rows,
        'month_filter': month_filter,
        'search_query': search_query,
        'distinct_months': distinct_months,
        'current_month': current_month,
    }

    return render(request, 'expense_log/transport_projectwise.html', context)
```

**Step 2: Verify no syntax errors**

```bash
cd /Users/apple/Documents/DataScienceProjects/ERP
source venv/bin/activate
python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

**Step 3: Commit**

```bash
git add integrations/expense_log/views.py
git commit -m "feat: rewrite transport projectwise view — group by client+transporter, approved only, charges@gw/client/margin"
```

---

### Task 2: Rewrite the template `transport_projectwise.html`

**Files:**
- Modify: `templates/expense_log/transport_projectwise.html` (full replacement)

**Step 1: Replace the entire template**

```html
{% extends 'base.html' %}
{% load static %}
{% load humanize %}

{% block title %}Transport Expenses - Project-wise{% endblock %}

{% block content %}
<div class="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

    <!-- Page Header -->
    <div class="flex items-center justify-between mb-8">
        <div>
            <h1 class="text-3xl font-bold text-gray-900">🚚 Transport Expenses - Project-wise</h1>
            <p class="text-gray-600 mt-1">Approved charges by project & transporter</p>
        </div>
        <a href="{% url 'expense_log:dashboard' %}" class="inline-flex items-center px-4 py-2 bg-gray-600 text-white rounded-lg text-sm font-medium hover:bg-gray-700 transition">
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"/>
            </svg>
            Back to Dashboard
        </a>
    </div>

    <!-- Summary Cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div class="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl shadow-md border-l-4 border-blue-500 p-6">
            <div class="text-center">
                <h3 class="text-sm font-semibold text-blue-700 uppercase tracking-wide mb-3">Total Charges@GW</h3>
                <p class="text-2xl lg:text-3xl font-bold text-blue-900 break-words">₹{{ total_gw|floatformat:0|intcomma }}</p>
                <p class="text-sm text-blue-600 mt-1">{{ total_rows }} rows</p>
            </div>
        </div>
        <div class="bg-gradient-to-br from-green-50 to-green-100 rounded-xl shadow-md border-l-4 border-green-500 p-6">
            <div class="text-center">
                <h3 class="text-sm font-semibold text-green-700 uppercase tracking-wide mb-3">Total Charges@Client</h3>
                <p class="text-2xl lg:text-3xl font-bold text-green-900 break-words">₹{{ total_client|floatformat:0|intcomma }}</p>
            </div>
        </div>
        <div class="bg-gradient-to-br {% if total_margin > 0 %}from-emerald-50 to-emerald-100 border-emerald-500{% else %}from-red-50 to-red-100 border-red-500{% endif %} rounded-xl shadow-md border-l-4 p-6">
            <div class="text-center">
                <h3 class="text-sm font-semibold {% if total_margin > 0 %}text-emerald-700{% else %}text-red-700{% endif %} uppercase tracking-wide mb-3">Overall Margin</h3>
                <p class="text-2xl lg:text-3xl font-bold {% if total_margin > 0 %}text-emerald-900{% else %}text-red-900{% endif %} break-words">{{ total_margin|floatformat:2 }}%</p>
            </div>
        </div>
    </div>

    <!-- Filters -->
    <div class="bg-white rounded-xl shadow-md p-6 mb-6">
        <form method="get" class="flex flex-wrap gap-4 items-end">
            <div class="flex-1 min-w-[200px]">
                <label class="block text-sm font-medium text-gray-700 mb-2">Service Month</label>
                <select name="month" class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-transparent">
                    <option value="">All Months</option>
                    {% for month in distinct_months %}
                    <option value="{{ month }}" {% if month == month_filter %}selected{% endif %}>{{ month }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="flex-1 min-w-[250px]">
                <label class="block text-sm font-medium text-gray-700 mb-2">Search</label>
                <input type="text" name="search" value="{{ search_query }}" placeholder="Search project or transporter..." class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 focus:border-transparent">
            </div>
            <button type="submit" class="px-6 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition font-medium">
                Apply Filters
            </button>
            {% if search_query %}
            <a href="?month={{ month_filter }}" class="px-6 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition font-medium">
                Clear
            </a>
            {% endif %}
        </form>
    </div>

    <!-- Table -->
    <div class="bg-white rounded-xl shadow-lg overflow-hidden">
        {% if rows %}
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gradient-to-r from-teal-600 to-teal-700">
                    <tr>
                        <th class="px-4 py-4 text-left text-xs font-bold text-white uppercase tracking-wider w-[35%]">Client</th>
                        <th class="px-4 py-4 text-left text-xs font-bold text-white uppercase tracking-wider w-[25%]">Transporter</th>
                        <th class="px-4 py-4 text-right text-xs font-bold text-white uppercase tracking-wider w-[13%]">Charges@GW</th>
                        <th class="px-4 py-4 text-right text-xs font-bold text-white uppercase tracking-wider w-[13%]">Charges@Client</th>
                        <th class="px-4 py-4 text-right text-xs font-bold text-white uppercase tracking-wider w-[14%]">Margin%</th>
                    </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                    <!-- Total Row -->
                    <tr class="bg-gray-100 font-bold">
                        <td class="px-4 py-3 text-sm text-gray-800">Total</td>
                        <td class="px-4 py-3 text-sm text-gray-800"></td>
                        <td class="px-4 py-3 text-right text-sm text-gray-900">{{ total_gw|floatformat:0|intcomma }}</td>
                        <td class="px-4 py-3 text-right text-sm text-gray-900">{{ total_client|floatformat:0|intcomma }}</td>
                        <td class="px-4 py-3 text-right text-sm {% if total_margin > 0 %}text-green-700{% else %}text-red-700{% endif %}">{{ total_margin|floatformat:2 }}%</td>
                    </tr>
                    <!-- Data Rows -->
                    {% for row in rows %}
                    <tr class="hover:bg-teal-50 transition">
                        <td class="px-4 py-3 text-sm text-gray-900 break-words">{{ row.client_name }}</td>
                        <td class="px-4 py-3 text-sm text-gray-700">{{ row.transporter_name }}</td>
                        <td class="px-4 py-3 text-right text-sm text-gray-900 whitespace-nowrap">{{ row.charges_at_gw|floatformat:0|intcomma }}</td>
                        <td class="px-4 py-3 text-right text-sm text-gray-900 whitespace-nowrap">{{ row.charges_at_client|floatformat:0|intcomma }}</td>
                        <td class="px-4 py-3 text-right text-sm font-semibold whitespace-nowrap {% if row.margin > 0 %}text-green-700{% else %}text-red-700{% endif %}">{{ row.margin|floatformat:2 }}%</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="p-12 text-center">
            <svg class="h-16 w-16 mx-auto text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path d="M9 17a2 2 0 11-4 0 2 2 0 014 0zM19 17a2 2 0 11-4 0 2 2 0 014 0z"/>
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16V6a1 1 0 00-1-1H4a1 1 0 00-1 1v10a1 1 0 001 1h1m8-1a1 1 0 01-1-1V4a1 1 0 011-1h2.586a1 1 0 01.707.293l3.414 3.414a1 1 0 01.293.707V16a1 1 0 01-1 1h-1m-6 0a1 1 0 001 1h2a1 1 0 001-1m0 0h2a2 2 0 002-2v-3m-4 5V9h3"/>
            </svg>
            <p class="text-gray-600 font-medium mb-2">No approved transport expenses found</p>
            <p class="text-sm text-gray-500">Try adjusting your filters or check back later.</p>
        </div>
        {% endif %}
    </div>

</div>
</div>
{% endblock %}
```

**Step 2: Verify Django can find the template (no syntax errors)**

```bash
python manage.py check --deploy 2>&1 | head -20
# Or just visit the page in browser
```

**Step 3: Commit**

```bash
git add templates/expense_log/transport_projectwise.html
git commit -m "feat: rewrite transport projectwise template — client+transporter table, charges@gw/client/margin, total row"
```

---

### Task 3: Manual verification in browser

**Step 1:** Start dev server

```bash
python manage.py runserver
```

**Step 2:** Navigate to `/expenses/transport-projectwise/`

**Step 3:** Verify:
- [ ] Summary cards show Total Charges@GW, Total Charges@Client, Overall Margin%
- [ ] Table has 5 columns: Client | Transporter | Charges@GW | Charges@Client | Margin%
- [ ] Total row appears at top in bold
- [ ] Margin% is green for positive, red for negative
- [ ] Month filter works (changes visible rows)
- [ ] Search filters by client name or transporter name
- [ ] Only Approved expenses are included (verify with a known record)

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: transport projectwise redesign complete"
git push origin main
```
