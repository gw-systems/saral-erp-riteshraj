# Gmail Integration Setup Guide

## Overview
The Gmail app provides OAuth2-based email integration for Saral ERP, allowing users to connect their Gmail accounts and send emails via Gmail API.

## Features
✅ OAuth2 authentication (secure, no passwords stored)
✅ Multi-account support (users can connect multiple Gmail accounts)
✅ HTML email support (for beautiful RFQ emails)
✅ Permission system (Admin/Director can access all accounts)
✅ Email tracking (all sent emails stored in database)
✅ Reply-to support (for POC emails)

## Setup Instructions

### 1. Install Required Packages
```bash
pip install -r requirements.txt
```

This installs:
- google-auth>=2.17.0
- google-auth-oauthlib>=1.0.0
- google-auth-httplib2>=0.1.0
- google-api-python-client>=2.80.0
- cryptography>=41.0.0

### 2. Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable Gmail API:
   - Navigate to **APIs & Services** → **Library**
   - Search for "Gmail API"
   - Click **Enable**

### 3. Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. Choose **Web application**
4. Configure:
   - **Name**: Saral ERP Gmail Integration
   - **Authorized redirect URIs**:
     - `http://localhost:8000/gmail/oauth/callback/` (for development)
     - `https://your-domain.com/gmail/oauth/callback/` (for production)
5. Click **Create**
6. Download the `credentials.json` file
7. Place `credentials.json` in your project root directory

### 4. Run Migrations
```bash
python manage.py makemigrations gmail
python manage.py migrate
```

This creates the following tables:
- `gmail_tokens` - Stores encrypted OAuth tokens
- `gmail_emails` - Stores synced emails
- `gmail_contacts` - Stores email contacts
- `gmail_sync_status` - Tracks sync status

### 5. Start Development Server
```bash
python manage.py runserver
```

### 6. Connect Gmail Account

1. Login to Saral ERP
2. Navigate to `/gmail/`
3. Click **Connect Gmail Account**
4. Login with Google
5. Grant permissions (Gmail send & read)
6. You'll be redirected back to ERP

Your Gmail account is now connected!

## Usage

### For Regular Users (Sales Manager, Supply Manager, etc.)

**Connect Your Gmail:**
- Visit `/gmail/` dashboard
- Click "Connect Gmail Account"
- Follow OAuth flow

**Send Emails:**
- When sending RFQs, select YOUR connected Gmail account from dropdown
- You can only send from accounts you've connected

**View Emails:**
- You can only see emails from YOUR connected accounts

### For Admin & Director

**Send from Any Account:**
- Can see ALL connected Gmail accounts in sender dropdown
- Can send RFQs from anyone's Gmail account

**View All Emails:**
- Can access email history from ALL users' accounts
- Full visibility across organization

### For Operation Controller

**View Only:**
- Can see all users' emails
- Cannot send from others' accounts

## Security

### Token Encryption
- OAuth tokens are encrypted using `cryptography.fernet`
- Encryption key derived from Django `SECRET_KEY`
- For production, set dedicated `GMAIL_ENCRYPTION_KEY` env variable

### OAuth Scopes
Required scopes:
- `https://www.googleapis.com/auth/gmail.readonly` - Read emails
- `https://www.googleapis.com/auth/gmail.send` - Send emails
- `https://www.googleapis.com/auth/gmail.modify` - Mark as read/unread
- `https://mail.google.com/` - Full access (for complete functionality)

### Permission Model
```python
# Admin, Director → Access ALL accounts
# Operation Controller → View all, send from own
# Regular users → Own accounts only
```

## Troubleshooting

### "Insufficient scope" Error
**Problem**: Emails not sending, 403 error
**Solution**: Reconnect Gmail account to grant all required scopes

### "credentials.json not found"
**Problem**: OAuth flow fails
**Solution**: Ensure `credentials.json` is in project root

### "Token expired" Error
**Problem**: OAuth token refresh failed
**Solution**: Disconnect and reconnect Gmail account

## API Usage (for RFQ Sending)

```python
from gmail.services import EmailService

# Send RFQ email
success = EmailService.send_email(
    user=request.user,
    sender_email="vivek@godamwale.com",
    to_email="vendor@example.com",
    subject="RFQ-042576 - 2000 Sq Ft in Pune",
    message_text="Plain text version",
    html_body=render_to_string('supply/emails/rfq_email.html', context),
    cc="manager@godamwale.com, director@godamwale.com",
    reply_to="abhishek@godamwale.com"
)
```

## Database Models

### GmailToken
- Stores encrypted OAuth tokens
- One-to-many: User → GmailTokens
- Unique: (user, email_account)

### Email
- Stores synced emails
- Linked to GmailToken
- Contains subject, body (text & HTML), sender, recipients

### Contact
- Email addresses extracted from emails
- Unique email addresses

### SyncStatus
- Tracks sync operations
- Records history IDs for incremental sync

## Next Steps

After Gmail setup is complete:
1. ✅ Users connect their Gmail accounts
2. ✅ Create RFQ models in supply app
3. ✅ Build "Send to Vendors" UI
4. ✅ Integrate with EmailService.send_email()
5. ✅ Track sent RFQs in RFQVendorMapping

## Support

For issues:
1. Check Django logs
2. Verify credentials.json is valid
3. Ensure redirect URIs match in Google Cloud Console
4. Test with `python manage.py shell` and EmailService directly
