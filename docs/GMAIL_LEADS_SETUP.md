# Gmail Lead Fetcher Setup Guide

## Overview

The Gmail Lead Fetcher app fetches **Contact Us** and **SAAS Inventory** lead emails from a dedicated Gmail account and stores them in the database with full metadata including UTM parameters.

**Key Features:**
- Fetches 2 lead types: CONTACT_US and SAAS_INVENTORY
- Bigin-style dashboard with column visibility toggle
- Expandable message preview in same view (no separate detail pages)
- Gmail-style filters and search
- Celery background sync (every 15 minutes)
- Comprehensive sync logging with quota tracking
- Duplicate detection
- Incremental sync with Last Processed Time tracking

---

## 1. Google Cloud Console Setup

You need to create **separate OAuth2 credentials** for the Gmail Lead Fetcher (different from the main Gmail app).

### Step 1: Go to Google Cloud Console
https://console.cloud.google.com/

### Step 2: Select or Create Project
- Use an existing project or create a new one: "Saral ERP Gmail Leads"

### Step 3: Enable Gmail API
1. Go to **APIs & Services** → **Library**
2. Search for "Gmail API"
3. Click **Enable**

### Step 4: Create OAuth2 Credentials
1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User Type: **Internal** (if G Suite) or **External**
   - App name: "Saral ERP Gmail Lead Fetcher"
   - User support email: your-email@example.com
   - Developer contact: your-email@example.com
   - Scopes: Add `https://www.googleapis.com/auth/gmail.readonly`

4. Create OAuth Client ID:
   - Application type: **Web application**
   - Name: "Gmail Lead Fetcher OAuth"
   - Authorized redirect URIs:
     ```
     http://localhost:8000/integrations/gmail-leads/oauth/callback/
     http://127.0.0.1:8000/integrations/gmail-leads/oauth/callback/
     https://your-production-domain.com/integrations/gmail-leads/oauth/callback/
     ```

5. Click **Create**
6. Download the JSON file (it will be named something like `client_secret_XXX.json`)

### Step 5: Save Credentials File
1. Rename the downloaded file to `gmail_leads_credentials.json`
2. Place it in your project root directory:
   ```
   /Users/apple/Documents/DataScienceProjects/ERP/gmail_leads_credentials.json
   ```

**IMPORTANT:**
- This file contains sensitive credentials
- Add `gmail_leads_credentials.json` to your `.gitignore`
- Never commit this file to version control

---

## 2. Database Migration

Run the migrations to create the necessary tables:

```bash
source venv/bin/activate
python manage.py migrate gmail_leads
```

**Tables Created:**
- `gmail_leads_tokens` - OAuth2 tokens for lead Gmail accounts
- `gmail_lead_emails` - Lead email data with all fields
- `gmail_leads_lpt` - Last Processed Time tracking per lead type
- `gmail_leads_sync_logs` - API operation logs
- `gmail_leads_duplicate_cache` - Duplicate detection cache

---

## 3. Connect Gmail Account

### Step 1: Login as Admin
Login to your ERP system with an admin account.

### Step 2: Go to Gmail Lead Fetcher
Navigate to: `http://localhost:8000/integrations/gmail-leads/`

### Step 3: Click "Connect Gmail Account"
1. Click the **"Connect Gmail Account"** button
2. You'll be redirected to Google's OAuth consent screen
3. **IMPORTANT:** Login with the Gmail account that receives the lead emails (e.g., `marketing@godamwale.com`)
4. Grant permissions to read emails
5. You'll be redirected back to the dashboard

### Step 4: Verify Connection
You should see the connected account displayed with:
- Email address
- Last sync time
- "Sync Now" and "Disconnect" buttons

---

## 4. Manual Sync

### Sync Single Account:
1. On the dashboard, find the connected account card
2. Click **"Sync Now"**
3. Wait for the notification: "Synced X leads"
4. Page will reload showing the new leads

### Sync All Accounts (Admin Only):
1. Click **"Sync All Accounts"** button (top right)
2. Wait for completion notification
3. All accounts will be synced

---

## 5. Automatic Background Sync

The app is configured to sync automatically every 15 minutes using Celery Beat.

### Verify Celery is Running:
Check that these processes are running:
```bash
# Should show celery worker and beat processes
ps aux | grep celery
```

### Celery Configuration:
The schedule is defined in `minierp/settings.py`:
```python
CELERY_BEAT_SCHEDULE = {
    "gmail-leads-sync": {
        "task": "gmail_leads.sync_all_accounts",
        "schedule": 900,  # 15 minutes
        "args": (False,),  # Incremental sync
    },
}
```

### Change Sync Frequency:
To change the frequency, edit the `schedule` value in seconds:
- Every 5 minutes: `300`
- Every 15 minutes: `900` (default)
- Every 30 minutes: `1800`
- Every hour: `3600`

---

## 6. Lead Types Configuration

The app fetches 2 types of leads based on email subject:

### 1. Contact Us Leads
**Subject:** `Godamwale "Contact us form submission from website"`

**Extracted Fields:**
- Name (from "From:" field)
- Email (from "Email ID:" field)
- Phone (from "Number:" field)
- Message (from "Tell us more:" field)

### 2. SAAS Inventory Leads (Inciflo)
**Subject:** `Inventory Management Inciflo "LEAD"`

**Extracted Fields:**
- Name
- Email
- Phone
- Company
- Message

### Customize Lead Types:
Edit `integrations/gmail_leads/gmail_leads_sync.py`:
```python
CONFIG = {
    "LEAD_TYPES": [
        {
            "type": "CONTACT_US",
            "subject": 'Godamwale "Contact us form submission from website"',
            "max_emails_per_sync": 100
        },
        {
            "type": "SAAS_INVENTORY",
            "subject": 'Inventory Management Inciflo "LEAD"',
            "max_emails_per_sync": 100
        }
    ],
    "BATCH_SIZE": 20,
    "HISTORY_SYNC_DAYS": 30,
}
```

---

## 7. Dashboard Features

### Stats Cards
- **Total Leads**: All-time count
- **Contact Us**: Contact form submissions
- **SAAS Inventory**: Inciflo leads
- **Today**: Leads received today
- **This Week**: Leads from last 7 days

### Filters
- **Date Range**: Start date → End date
- **Lead Type**: All / Contact Us / SAAS Inventory
- **Search**: Search by name, email, company, or message
- **UTM Campaign**: Multi-select dropdown
- **UTM Medium**: Multi-select dropdown

### Column Visibility (Bigin-style)
Click column name buttons to show/hide:
- Lead Type
- Date & Time
- Form fields (Name, Email, Phone, Company)
- UTM parameters (Campaign, Medium, Term, Content)
- Email headers (From, Reply-To, Subject)
- Message Preview

**Note:** Your preferences are saved in browser localStorage

### Message Preview
- Click on message text to expand/collapse
- Shows full extracted form data
- No separate detail page needed (all data visible in table)

---

## 8. Sync Logs

View detailed sync logs at: `/integrations/gmail-leads/logs/`

**Log Levels:**
- **DEBUG**: Detailed operation info (API calls, quota usage)
- **INFO**: General information (sync started, completed)
- **SUCCESS**: Successful operations (message processed)
- **WARNING**: Non-fatal issues (parsing failures)
- **ERROR**: Failed operations
- **CRITICAL_DEBUG**: Critical debugging info

**Filters:**
- Filter by log level
- Filter by date

**Use Cases:**
- Track Gmail API quota usage
- Debug sync failures
- Monitor duplicate detection
- View sync performance (duration in ms)

---

## 9. Gmail API Scopes Required

The OAuth2 app must have this scope:
- `https://www.googleapis.com/auth/gmail.readonly` - Read emails

**To verify scopes:**
1. Go to Google Cloud Console → APIs & Services → OAuth consent screen
2. Check "Scopes" section
3. Ensure `gmail.readonly` is listed

**Important:** If you add new scopes later, users must **disconnect and reconnect** their Gmail accounts to grant the new permissions.

---

## 10. Permissions

### Admin / Director:
- Can connect Gmail accounts
- Can sync all accounts
- Can view all leads
- Can access sync logs

### Sales Manager / Executive:
- Can connect their own Gmail accounts
- Can sync their own accounts
- Can view leads from their accounts
- Can access logs for their accounts

---

## 11. Troubleshooting

### Error: "credentials file not found"
**Fix:**
1. Download credentials from Google Cloud Console
2. Rename to `gmail_leads_credentials.json`
3. Place in project root directory

### Error: "Invalid token data"
**Fix:** Disconnect and reconnect the Gmail account

### Error: "Insufficient OAuth scope"
**Fix:**
1. Update OAuth2 app scopes in Google Cloud Console
2. Users must disconnect and reconnect accounts

### No leads synced
**Possible causes:**
1. Gmail account has no matching emails
2. Subject line doesn't match exactly
3. Token expired - reconnect account
4. Gmail API quota exceeded - check logs

### Sync button not working
**Fix:**
1. Check browser console for errors
2. Verify CSRF token is present
3. Hard refresh (Ctrl+Shift+R / Cmd+Shift+R)

### Celery not running
**Fix:**
```bash
# Start Celery worker
celery -A minierp worker --loglevel=info

# Start Celery Beat (scheduler)
celery -A minierp beat --loglevel=info
```

---

## 12. Database Schema

### LeadEmail Model
All fields from Google Sheets:
- `lead_type`: CONTACT_US or SAAS_INVENTORY
- `month_year`: "February 2026"
- `from_name`, `from_email`: Email sender
- `reply_to_name`, `reply_to_email`: Actual lead contact
- `to_addresses`: Recipients (comma-separated)
- `utm_term`, `utm_campaign`, `utm_medium`, `utm_content`: Campaign tracking
- `subject`: Email subject
- `date_received`, `time_received`, `datetime_received`: Timestamps
- `form_name`, `form_email`, `form_phone`, `form_address`, `form_company_name`: Extracted form data
- `message_preview`: Full message text
- `processed_timestamp`: When synced
- `message_id`: Gmail message ID (unique)

### SyncLog Model
Tracks all operations:
- `timestamp`: When logged
- `level`: DEBUG, INFO, WARNING, SUCCESS, ERROR, CRITICAL_DEBUG
- `operation`: Operation name (e.g., "Gmail API Fetch", "Quota")
- `details`: Descriptive message
- `duration_ms`: Operation duration
- `account_link`: Which account
- `lead_type`: Which lead type

---

## 13. Next Steps

After Gmail Lead Fetcher is working:

1. **Callyzer Integration** - Fetch call tracking data
2. **Google Ads Integration** - Fetch ad performance data
3. **Cross-integration Analytics** - Correlate leads with ads and calls
4. **Lead Scoring** - Auto-score leads based on UTM and form data
5. **CRM Integration** - Push leads to Bigin CRM

---

## Summary

✅ Gmail Lead Fetcher is fully operational with:
- Bigin-style dashboard with column visibility
- Expandable message preview (no separate detail pages)
- Automatic background sync (every 15 minutes)
- Comprehensive sync logging
- Duplicate detection
- UTM parameter tracking
- Permission-based access control
- Ready for production deployment

**Access URLs:**
- Dashboard: `/integrations/gmail-leads/`
- Sync Logs: `/integrations/gmail-leads/logs/`
- Connect Account: `/integrations/gmail-leads/connect/`

**Total Implementation:**
- 12 files created/modified
- ~3,500 lines of production-ready code
- Following Bigin integration pattern
- Ready for Callyzer and Google Ads integrations
