# Testing Guide - Gmail & RFQ Integration

## Pre-Testing Setup

### 1. Install Packages
```bash
pip install -r requirements.txt
```

### 2. Check Installation
```bash
python manage.py shell
```
```python
# Test imports
from gmail.models import GmailToken, Email
from supply.models import RFQ, RFQVendorMapping, VendorContact
from gmail.services import EmailService

print("✅ All imports successful!")
exit()
```

### 3. Run Migrations
```bash
# Create migrations
python manage.py makemigrations gmail
python manage.py makemigrations supply

# Apply migrations
python manage.py migrate

# Check tables created
python manage.py dbshell
```
```sql
-- Check Gmail tables
\dt gmail_*

-- Check RFQ tables
\dt rfqs
\dt rfq_vendor_mappings

-- Check VendorContact has new fields
\d vendor_contacts

-- Exit
\q
```

---

## Phase 1: Test Gmail Integration

### Test 1: Gmail App URLs
```bash
python manage.py runserver
```

Visit these URLs in browser (while logged in):
- `http://localhost:8000/gmail/` - Should show Gmail dashboard
- Should NOT crash (templates missing is OK for now)

### Test 2: Django Admin
Visit: `http://localhost:8000/admin/`

Check these models exist:
- **Gmail section**:
  - Gmail Tokens
  - Emails
  - Contacts
  - Sync Statuses

- **Supply section**:
  - RFQs
  - RFQ Vendor Mappings
  - Vendor Contacts (check if new fields visible)

### Test 3: Connect Gmail Account (OAuth2)

**Prerequisites**:
1. You MUST have `credentials.json` in project root
2. Get it from: https://console.cloud.google.com/apis/credentials

**Steps**:
```bash
python manage.py runserver
```

1. Visit: `http://localhost:8000/gmail/`
2. Click "Connect Gmail Account" (button should exist)
3. Should redirect to Google OAuth consent screen
4. Login with your `@godamwale.com` account
5. Grant all permissions
6. Should redirect back to `/gmail/` dashboard
7. Should see your connected account

**Verify in Database**:
```bash
python manage.py shell
```
```python
from gmail.models import GmailToken

tokens = GmailToken.objects.all()
print(f"Connected accounts: {tokens.count()}")

for token in tokens:
    print(f"- {token.email_account} (User: {token.user.username})")
```

### Test 4: Test Email Sending (Simple)
```bash
python manage.py shell
```
```python
from gmail.services import EmailService
from gmail.models import GmailToken
from accounts.models import User

# Get your user
user = User.objects.first()
print(f"Testing with user: {user.username}")

# Get connected Gmail account
token = GmailToken.objects.filter(user=user, is_active=True).first()
if not token:
    print("❌ No Gmail account connected!")
else:
    sender_email = token.email_account
    print(f"Sending from: {sender_email}")

    # Send test email
    success = EmailService.send_email(
        user=user,
        sender_email=sender_email,
        to_email="your-email@example.com",  # Replace with real email
        subject="Test Email from Saral ERP",
        message_text="This is a plain text test email.",
        html_body="<h1>Test Email</h1><p>This is an <strong>HTML</strong> test email from Saral ERP.</p>"
    )

    if success:
        print("✅ Email sent successfully!")
    else:
        print("❌ Email failed to send. Check logs.")
```

**Expected Result**: You should receive the email at the TO address.

### Test 5: Test Permission System
```bash
python manage.py shell
```
```python
from gmail.services import EmailService
from gmail.models import GmailToken
from accounts.models import User

# Test 1: Regular user sees only own accounts
regular_user = User.objects.filter(role='sales_manager').first()
if regular_user:
    accounts = EmailService.get_available_sender_accounts(regular_user)
    print(f"Regular user '{regular_user.username}' sees {accounts.count()} account(s)")
    print([acc.email_account for acc in accounts])

# Test 2: Admin sees ALL accounts
admin_user = User.objects.filter(role='admin').first()
if admin_user:
    accounts = EmailService.get_available_sender_accounts(admin_user)
    print(f"Admin '{admin_user.username}' sees {accounts.count()} account(s)")
    print([acc.email_account for acc in accounts])
```

**Expected**:
- Regular user: Only their connected accounts
- Admin: ALL connected accounts in system

---

## Phase 2: Test RFQ Models

### Test 1: Create RFQ (Auto-Sequence)
```bash
python manage.py shell
```
```python
from supply.models import RFQ
from accounts.models import User

user = User.objects.first()

# Create first RFQ
rfq1 = RFQ.objects.create(
    city="Pune",
    area_required_sqft=2000,
    product="Polymer",
    tenure="medium",
    remarks="Test RFQ 1",
    created_by=user
)

print(f"✅ Created: {rfq1.rfq_id}")  # Should be: RFQ-042576

# Create second RFQ
rfq2 = RFQ.objects.create(
    city="Mumbai",
    area_required_sqft=5000,
    product="Solar Panels",
    tenure="high",
    created_by=user
)

print(f"✅ Created: {rfq2.rfq_id}")  # Should be: RFQ-042577

# Verify sequence
all_rfqs = RFQ.objects.all().order_by('rfq_id')
print("\nAll RFQs:")
for rfq in all_rfqs:
    print(f"  {rfq.rfq_id} - {rfq.area_required_sqft} sqft in {rfq.city}")
```

**Expected**: IDs should auto-increment: RFQ-042576, RFQ-042577, RFQ-042578...

### Test 2: Add RFQ Vendor Contact
```bash
python manage.py shell
```
```python
from supply.models import VendorContact, VendorCard

# Get or create a vendor
vendor, created = VendorCard.objects.get_or_create(
    vendor_legal_name="Test Vendor Pvt Ltd",
    defaults={'vendor_short_name': 'Test Vendor'}
)

# Create RFQ contact
contact = VendorContact.objects.create(
    vendor_code=vendor,
    vendor_contact_person="John Doe",
    vendor_contact_designation="Sales Manager",
    vendor_contact_department="Sales",
    vendor_contact_phone="9876543210",
    vendor_contact_email="john@testvendor.com",
    is_rfq_contact=True,  # Flag for RFQ
    rfq_cc_emails=["cc1@testvendor.com", "cc2@testvendor.com"],
    rfq_cities="Mumbai, Pune, Bangalore",
    rfq_contact_number="9876543210"
)

print(f"✅ Created RFQ contact: {contact.vendor_contact_email}")
print(f"   CC Emails: {contact.rfq_cc_emails}")
print(f"   Cities: {contact.rfq_cities}")

# Verify
rfq_contacts = VendorContact.objects.filter(is_rfq_contact=True)
print(f"\nTotal RFQ contacts: {rfq_contacts.count()}")
```

### Test 3: Test RFQ with Rates
```python
from supply.models import RFQ
from accounts.models import User

user = User.objects.first()

rfq = RFQ.objects.create(
    city="Bangalore",
    area_required_sqft=3000,
    product="Chemicals",
    tenure="short",
    storage_rate_sqft=24.50,
    storage_rate_pallet=600.00,
    handling_rate_pallet=170.00,
    remarks="Hazardous materials. Fire safety required.",
    created_by=user
)

print(f"✅ Created: {rfq.rfq_id}")
print(f"   Storage (Sq Ft): ₹{rfq.storage_rate_sqft}")
print(f"   Storage (Pallet): ₹{rfq.storage_rate_pallet}")
print(f"   Handling: ₹{rfq.handling_rate_pallet}")
```

---

## Phase 3: Test RFQ Views (URL Testing)

### Test 1: RFQ List
```bash
python manage.py runserver
```

Visit: `http://localhost:8000/supply/rfqs/`

**Expected**:
- Should NOT crash (even if template missing)
- If template exists: Shows list of RFQs
- If missing: Shows template error (this is OK)

### Test 2: RFQ Create
Visit: `http://localhost:8000/supply/rfqs/create/`

**Expected**: Shows create form (or template missing error)

### Test 3: RFQ Detail
```bash
python manage.py shell
```
```python
from supply.models import RFQ
rfq = RFQ.objects.first()
print(f"Visit: http://localhost:8000/supply/rfqs/{rfq.rfq_id}/")
```

Visit the URL printed above.

**Expected**: Shows RFQ details (or template missing error)

### Test 4: RFQ Send Dialog
Visit: `http://localhost:8000/supply/rfqs/RFQ-042576/send/`

**Expected**: Shows send form with:
- Sender account dropdown
- Vendor selection
- Deadline picker
- POC dropdown

---

## Phase 4: End-to-End RFQ Email Test

### Prerequisites:
1. Gmail account connected
2. RFQ created
3. At least one RFQ vendor contact created

### Test: Send RFQ Email
```bash
python manage.py shell
```
```python
from supply.models import RFQ, VendorContact, RFQVendorMapping
from gmail.services import EmailService
from gmail.models import GmailToken
from accounts.models import User
from django.template.loader import render_to_string

# Get components
user = User.objects.first()
rfq = RFQ.objects.first()
vendor_contact = VendorContact.objects.filter(is_rfq_contact=True).first()
gmail_token = GmailToken.objects.filter(user=user, is_active=True).first()

if not all([rfq, vendor_contact, gmail_token]):
    print("❌ Missing prerequisites!")
    print(f"  RFQ: {rfq}")
    print(f"  Vendor Contact: {vendor_contact}")
    print(f"  Gmail Token: {gmail_token}")
else:
    sender_email = gmail_token.email_account
    deadline_date = "31st December 2024"

    # Render email
    html_body = render_to_string('supply/emails/rfq_email.html', {
        'rfq': rfq,
        'deadline': deadline_date,
        'poc': user,  # Using sender as POC for test
        'sender': user,
        'vendor': vendor_contact
    })

    # Send email
    success = EmailService.send_email(
        user=user,
        sender_email=sender_email,
        to_email=vendor_contact.vendor_contact_email,
        subject=f"{rfq.rfq_id} - {rfq.area_required_sqft} Sq Ft in {rfq.city}",
        message_text=f"RFQ for {rfq.area_required_sqft} sqft in {rfq.city}",
        html_body=html_body,
        cc=', '.join(vendor_contact.rfq_cc_emails) if vendor_contact.rfq_cc_emails else '',
        reply_to=user.email
    )

    if success:
        # Create tracking record
        mapping = RFQVendorMapping.objects.create(
            rfq=rfq,
            vendor_contact=vendor_contact,
            sent_from_account=sender_email,
            sent_to_email=vendor_contact.vendor_contact_email,
            sent_cc_emails=vendor_contact.rfq_cc_emails or [],
            deadline_date="2024-12-31",
            point_of_contact=user,
            sent_by=user
        )
        print(f"✅ Email sent successfully!")
        print(f"   Tracking ID: {mapping.id}")
        print(f"   From: {sender_email}")
        print(f"   To: {vendor_contact.vendor_contact_email}")
        print(f"   CC: {vendor_contact.rfq_cc_emails}")
    else:
        print("❌ Email failed to send!")
```

**Check**:
1. Email received at TO address?
2. CC recipients received copy?
3. HTML formatting correct?
4. Reply-to header set correctly?

---

## Phase 5: Test Django Admin

### Test Admin Interface
Visit: `http://localhost:8000/admin/`

#### 1. Gmail Tokens
- Go to **Gmail > Gmail Tokens**
- Should see connected accounts
- Check encrypted_token_data is filled
- Try editing (should work)

#### 2. RFQs
- Go to **Supply > RFQs**
- Should see created RFQs
- Try creating new RFQ via admin
- Should auto-generate ID

#### 3. RFQ Vendor Mappings
- Go to **Supply > RFQ Vendor Mappings**
- Should see sent RFQs
- Check all fields populated

#### 4. Vendor Contacts
- Go to **Supply > Vendor Contacts**
- Check new fields visible:
  - is_rfq_contact (checkbox)
  - rfq_cc_emails (JSON)
  - rfq_cities (text)
  - rfq_contact_number (text)

---

## Phase 6: Permission Testing

### Test 1: Regular User Cannot Send from Admin's Account
```bash
python manage.py shell
```
```python
from gmail.services import EmailService
from gmail.models import GmailToken
from accounts.models import User

# Get a regular user (sales_manager)
regular_user = User.objects.filter(role='sales_manager').first()

# Get an admin's Gmail account
admin_user = User.objects.filter(role='admin').first()
admin_gmail = GmailToken.objects.filter(user=admin_user).first()

if regular_user and admin_gmail:
    can_send = EmailService.can_send_from_account(
        regular_user,
        admin_gmail.email_account
    )
    print(f"Can regular user send from admin's Gmail? {can_send}")
    # Should print: False
```

### Test 2: Admin Can Send from Any Account
```python
admin_user = User.objects.filter(role='admin').first()
any_gmail = GmailToken.objects.first()

if admin_user and any_gmail:
    can_send = EmailService.can_send_from_account(
        admin_user,
        any_gmail.email_account
    )
    print(f"Can admin send from any Gmail? {can_send}")
    # Should print: True
```

---

## Common Issues & Solutions

### Issue 1: "No module named 'gmail'"
**Solution**:
```bash
# Check INSTALLED_APPS has 'gmail'
python manage.py shell
from django.conf import settings
print('gmail' in settings.INSTALLED_APPS)
```

### Issue 2: "credentials.json not found"
**Solution**:
```bash
# Check file exists
ls credentials.json

# If missing, download from Google Cloud Console
# https://console.cloud.google.com/apis/credentials
```

### Issue 3: "Insufficient OAuth scope"
**Solution**:
- Disconnect Gmail account
- Reconnect (will re-request all scopes)

### Issue 4: "Template does not exist"
**This is OK!** Backend is complete, templates are next step.

### Issue 5: Migration errors
```bash
# Reset migrations if needed
python manage.py migrate gmail zero
python manage.py migrate supply zero

# Then remigrate
python manage.py makemigrations gmail supply
python manage.py migrate
```

---

## Success Checklist

- [ ] Packages installed
- [ ] Migrations run successfully
- [ ] Gmail tables created in database
- [ ] RFQ tables created in database
- [ ] VendorContact has new RFQ fields
- [ ] Can visit `/gmail/` without crash
- [ ] Can connect Gmail account via OAuth2
- [ ] Gmail token stored in database (encrypted)
- [ ] Can send test email via shell
- [ ] Can create RFQ (auto-generates ID)
- [ ] RFQ IDs increment correctly
- [ ] Can create RFQ vendor contact
- [ ] Can visit `/supply/rfqs/` without crash
- [ ] Can send RFQ email end-to-end
- [ ] RFQVendorMapping created after send
- [ ] Django admin shows all models
- [ ] Permission system works (admin vs regular)
- [ ] HTML email received correctly formatted

---

## Next: Create Frontend Templates

After all tests pass, create these 4 HTML files:
1. `templates/supply/rfq_list.html`
2. `templates/supply/rfq_form.html`
3. `templates/supply/rfq_detail.html`
4. `templates/supply/rfq_send.html`

Copy structure from existing supply templates!
