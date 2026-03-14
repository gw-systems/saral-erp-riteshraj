# Bigin Full CRUD Implementation Guide

This guide explains how to enable CREATE, UPDATE, and DELETE operations for Bigin in your ERP system.

## Current Status

Your ERP currently has **READ-ONLY** access to Bigin. To enable full bi-directional sync (CREATE, UPDATE, DELETE), you need to re-authorize with the correct OAuth scopes.

---

## Step 1: Update OAuth Scopes

You need to re-authorize your Zoho Bigin app with these scopes:

### Required Scopes for Full CRUD:

```
ZohoBigin.modules.contacts.ALL
ZohoBigin.modules.accounts.ALL
ZohoBigin.modules.deals.ALL
ZohoBigin.modules.products.ALL
ZohoBigin.modules.notes.ALL
ZohoBigin.users.READ
ZohoBigin.settings.modules.READ
```

### What Each Scope Provides:

| Scope | Operations | Description |
|-------|-----------|-------------|
| `ZohoBigin.modules.contacts.ALL` | CREATE, READ, UPDATE, DELETE | Full access to Contacts |
| `ZohoBigin.modules.accounts.ALL` | CREATE, READ, UPDATE, DELETE | Full access to Accounts (Companies) |
| `ZohoBigin.modules.deals.ALL` | CREATE, READ, UPDATE, DELETE | Full access to Deals |
| `ZohoBigin.modules.products.ALL` | CREATE, READ, UPDATE, DELETE | Full access to Products |
| `ZohoBigin.modules.notes.ALL` | CREATE, READ, UPDATE, DELETE | Full access to Notes |

---

## Step 2: Re-Authorization Process

### Option A: Using Zoho API Console (Recommended)

1. **Go to Zoho API Console**:
   - Visit: https://api-console.zoho.com/
   - Sign in with your Zoho account

2. **Create/Update Self Client**:
   - Go to "Self Client" tab
   - Note your `Client ID` and `Client Secret`

3. **Generate New Token with Correct Scopes**:
   - Click "Generate Code" button
   - **Scope**: Paste all the required scopes (comma-separated):
     ```
     ZohoBigin.modules.contacts.ALL,ZohoBigin.modules.accounts.ALL,ZohoBigin.modules.deals.ALL,ZohoBigin.modules.products.ALL,ZohoBigin.modules.notes.ALL,ZohoBigin.users.READ,ZohoBigin.settings.modules.READ
     ```
   - **Time Duration**: 10 minutes (or custom)
   - **Scope Description**: Full CRUD access for Bigin ERP integration
   - Click **Create**

4. **Get Authorization Code**:
   - Copy the generated authorization code
   - **Important**: This code expires quickly (in 10 minutes), so use it immediately

5. **Update Tokens in ERP**:
   - Go to your ERP: `/bigin/api/manual-token-update/`
   - Enter the authorization code
   - Click "Update Tokens"

### Option B: Using OAuth Flow in ERP

1. **Update Authorization URL Generator** (if needed):
   - The authorization URL should include all required scopes
   - URL format:
     ```
     https://accounts.zoho.com/oauth/v2/auth?
     scope=ZohoBigin.modules.contacts.ALL,ZohoBigin.modules.accounts.ALL,ZohoBigin.modules.deals.ALL,ZohoBigin.modules.products.ALL,ZohoBigin.modules.notes.ALL,ZohoBigin.users.READ,ZohoBigin.settings.modules.READ
     &client_id=YOUR_CLIENT_ID
     &response_type=code
     &access_type=offline
     &redirect_uri=YOUR_REDIRECT_URI
     ```

2. **Authorize**:
   - Visit the authorization URL
   - Grant all requested permissions
   - You'll be redirected to your callback URL with a code
   - The ERP will automatically exchange it for tokens

---

## Step 3: Verify Permissions

After re-authorizing, verify that your tokens have the correct scopes:

```python
# Test in Django shell
from integrations.bigin.token_manager import get_valid_token
import requests

token = get_valid_token()

# Try to create a test contact
response = requests.post(
    'https://bigin.zoho.com/api/v1/Contacts',
    headers={'Authorization': f'Zoho-oauthtoken {token}'},
    json={
        'data': [{
            'First_Name': 'Test',
            'Last_Name': 'User',
            'Email': 'test@example.com'
        }]
    }
)

print(response.status_code)  # Should be 200 or 201
print(response.json())
```

**Expected Response** (if scopes are correct):
```json
{
    "data": [{
        "code": "SUCCESS",
        "details": {
            "id": "4876876000000123456",
            ...
        }
    }]
}
```

**Error Response** (if scopes are missing):
```json
{
    "code": "OAUTH_SCOPE_MISMATCH",
    "message": "invalid oauth scope to access this URL"
}
```

---

## Step 4: Using the CRUD API Endpoints

Once re-authorized, you can use these endpoints:

### Create a Contact

```bash
POST /bigin/api/contacts/create/
Content-Type: application/json

{
    "First_Name": "John",
    "Last_Name": "Doe",
    "Email": "john@example.com",
    "Mobile": "+919876543210",
    "Type": "3pl",
    "Status": ["Hot"],
    "Area_Requirement": "5000"
}
```

**Response**:
```json
{
    "success": true,
    "message": "Contact created successfully in Bigin",
    "bigin_id": "4876876000000123456",
    "record": { ... }
}
```

### Update a Contact

```bash
PUT /bigin/api/contacts/4876876000000123456/update/
Content-Type: application/json

{
    "Mobile": "+919876543211",
    "Status": ["Warm"],
    "Area_Requirement": "6000"
}
```

**Response**:
```json
{
    "success": true,
    "message": "Contact updated successfully in Bigin",
    "bigin_id": "4876876000000123456",
    "record": { ... }
}
```

### Delete a Contact

```bash
DELETE /bigin/api/contacts/4876876000000123456/delete/
```

**Response**:
```json
{
    "success": true,
    "message": "Contact deleted successfully from Bigin",
    "bigin_id": "4876876000000123456"
}
```

### Bulk Create Contacts

```bash
POST /bigin/api/contacts/bulk-create/
Content-Type: application/json

{
    "contacts": [
        {
            "First_Name": "John",
            "Last_Name": "Doe",
            "Email": "john@example.com"
        },
        {
            "First_Name": "Jane",
            "Last_Name": "Smith",
            "Email": "jane@example.com"
        }
    ]
}
```

**Response**:
```json
{
    "success": true,
    "message": "Successfully created 2 contacts",
    "created_count": 2,
    "records": [ ... ]
}
```

### Bulk Update Contacts

```bash
PUT /bigin/api/contacts/bulk-update/
Content-Type: application/json

{
    "contacts": [
        {
            "id": "4876876000000123456",
            "Status": ["Hot"]
        },
        {
            "id": "4876876000000789012",
            "Status": ["Warm"]
        }
    ]
}
```

**Response**:
```json
{
    "success": true,
    "message": "Successfully updated 2 contacts",
    "updated_count": 2,
    "records": [ ... ]
}
```

---

## Step 5: Testing in Production

1. **Test Create**:
   ```bash
   curl -X POST https://your-erp-domain.com/bigin/api/contacts/create/ \
     -H "Content-Type: application/json" \
     -d '{
       "First_Name": "Test",
       "Last_Name": "Contact",
       "Email": "test@example.com"
     }'
   ```

2. **Test Update**:
   ```bash
   curl -X PUT https://your-erp-domain.com/bigin/api/contacts/BIGIN_ID/update/ \
     -H "Content-Type: application/json" \
     -d '{
       "Mobile": "+919999999999"
     }'
   ```

3. **Test Delete**:
   ```bash
   curl -X DELETE https://your-erp-domain.com/bigin/api/contacts/BIGIN_ID/delete/
   ```

---

## Bigin Field Reference

### Contact Fields (Common)

| Field Name | Type | Required | Example |
|------------|------|----------|---------|
| `First_Name` | String | Yes | "John" |
| `Last_Name` | String | Yes | "Doe" |
| `Email` | String | No | "john@example.com" |
| `Mobile` | String | No | "+919876543210" |
| `Type` | String | No | "3pl", "Lead (Standalone )" |
| `Status` | Array | No | ["Hot"], ["Warm"], ["Cold"] |
| `Status_of_Action` | Array | No | ["Follow Up"], ["Quotation Sent"] |
| `Area_Requirement` | String | No | "5000" |
| `Lead_Source` | String | No | "Website", "Referral" |
| `Locations` | String | No | "Mumbai, Delhi" |
| `Description` | String | No | "Additional notes..." |
| `Owner` | Object | No | {"id": "123456"} |

### Status Values (Picklist)

- Hot
- Warm
- Cold
- Converted
- Closed
- Junk

### Lead Stage Values (Multi-select)

- Follow Up
- Quotation Sent
- Negotiation
- Site Visit
- Contract Sent
- Lost
- Converted

---

## Troubleshooting

### Error: "OAUTH_SCOPE_MISMATCH"

**Problem**: Your token doesn't have the required permissions.

**Solution**:
1. Re-authorize with the correct scopes (see Step 2)
2. Make sure you included `.ALL` in the scope names
3. Use `ZohoBigin.modules.contacts.ALL` not just `ZohoBigin.modules.contacts.READ`

### Error: "INVALID_TOKEN"

**Problem**: Token expired or invalid.

**Solution**:
1. Go to `/bigin/api/force-token-refresh/` to refresh the token
2. If that fails, re-authorize from scratch

### Error: "MANDATORY_NOT_FOUND"

**Problem**: Required fields missing from the request.

**Solution**:
- For Contacts: `First_Name` and `Last_Name` are required
- Check the Bigin field requirements in the API documentation

### Records Not Syncing to Local DB

**Problem**: Records created/updated in Bigin but not appearing in ERP.

**Solution**:
1. Run a manual sync: `/bigin/api/trigger-sync/`
2. Check sync logs in the `Sync Audit` page
3. Verify the record was actually created in Bigin first

---

## Next Steps

1. **Re-authorize with new scopes** (Step 2)
2. **Test the CRUD endpoints** (Step 5)
3. **Integrate into your forms/views** to allow users to create/update/delete contacts from the ERP
4. **Add UI components** for the CRUD operations in your templates

---

## Security Notes

- **CSRF Protection**: The CRUD endpoints use `@csrf_exempt` for API access. If calling from your own frontend, add CSRF protection.
- **Authentication**: Currently no authentication required. Add `@login_required` decorator if needed.
- **Rate Limiting**: Zoho Bigin has API rate limits (typically 200 requests/minute). The client includes retry logic.
- **Validation**: Always validate user input before sending to Bigin API.

---

## Support

If you encounter issues:

1. Check the logs in `/bigin/sync-audit/`
2. Review the Zoho Bigin API documentation: https://www.zoho.com/bigin/developer/api/
3. Verify your OAuth scopes in the Zoho API Console
4. Test the endpoints with curl/Postman before integrating into your app

---

**Last Updated**: 2026-02-02
**ERP Version**: Current
**Bigin API Version**: v1
