# 🔐 Gmail OAuth2 Credentials Setup Guide

## ⚠️ REQUIRED: Before Users Can Connect Gmail

You need to set up Google Cloud OAuth2 credentials **once** for the entire application.

---

## 📋 Step-by-Step Setup (5 minutes)

### **Step 1: Go to Google Cloud Console**

Visit: https://console.cloud.google.com/

### **Step 2: Create a New Project**

1. Click "Select a project" (top left)
2. Click "New Project"
3. Name: **"Saral ERP Gmail Integration"**
4. Click "Create"

### **Step 3: Enable Gmail API**

1. Go to: https://console.cloud.google.com/apis/library
2. Search for: **"Gmail API"**
3. Click on "Gmail API"
4. Click **"Enable"**

### **Step 4: Create OAuth2 Credentials**

1. Go to: https://console.cloud.google.com/apis/credentials
2. Click **"Create Credentials"** → Choose **"OAuth client ID"**

**If you see "Configure consent screen" warning:**
- Click "Configure Consent Screen"
- Choose **"Internal"** (if you have Google Workspace) or **"External"**
- Fill in:
  - App name: **Saral ERP**
  - User support email: **your-email@godamwale.com**
  - Developer contact: **your-email@godamwale.com**
- Click "Save and Continue" → "Save and Continue" → "Save and Continue"
- Click "Back to Dashboard"
- Go back to: https://console.cloud.google.com/apis/credentials

3. Click **"Create Credentials"** → **"OAuth client ID"**
4. Choose **"Web application"**
5. Name: **"Saral ERP Web App"**
6. Add **Authorized redirect URIs**:
   ```
   http://localhost:8000/gmail/oauth/callback/
   http://127.0.0.1:8000/gmail/oauth/callback/
   ```

   **For Production (when you deploy), also add:**
   ```
   https://your-domain.com/gmail/oauth/callback/
   ```

7. Click **"Create"**

### **Step 5: Download credentials.json**

1. You'll see a popup with **Client ID** and **Client Secret**
2. Click **"Download JSON"**
3. Save the file
4. **Rename it to:** `credentials.json`

### **Step 6: Place credentials.json in Project Root**

Copy the downloaded `credentials.json` to your ERP project root:

```bash
/Users/apple/Documents/DataScienceProjects/ERP/credentials.json
```

**File structure should be:**
```
ERP/
├── credentials.json          ← Place here!
├── manage.py
├── minierp/
├── gmail/
├── supply/
└── ...
```

---

## ✅ Verify Setup

1. Check that `credentials.json` exists:
   ```bash
   ls -la /Users/apple/Documents/DataScienceProjects/ERP/credentials.json
   ```

2. Restart Django server:
   ```bash
   python manage.py runserver
   ```

3. Visit: http://localhost:8000/gmail/
4. Click "Connect Gmail Account"
5. Should redirect to Google login page ✅

---

## 🔒 Security Notes

### ✅ DO:
- Keep `credentials.json` **SECRET**
- Add to `.gitignore` (already done)
- Never commit to Git
- Never share publicly

### ❌ DON'T:
- Don't share your Client Secret
- Don't commit credentials.json
- Don't post screenshots with credentials visible

---

## 📝 Sample credentials.json Structure

Your file should look like this (with your actual values):

```json
{
  "web": {
    "client_id": "123456789-xxxxx.apps.googleusercontent.com",
    "project_id": "saral-erp-gmail",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "GOCSPX-xxxxxxxxxxxxxxxxxxxxx",
    "redirect_uris": [
      "http://localhost:8000/gmail/oauth/callback/",
      "http://127.0.0.1:8000/gmail/oauth/callback/"
    ]
  }
}
```

---

## 🐛 Troubleshooting

### Error: "No such file or directory: credentials.json"
**Solution:** Follow Step 6 above - place file in project root

### Error: "redirect_uri_mismatch"
**Solution:**
1. Go to Google Cloud Console → Credentials
2. Edit your OAuth2 client
3. Add the exact redirect URI from the error message
4. Wait 5 minutes for changes to propagate

### Error: "Access blocked: This app's request is invalid"
**Solution:**
1. Make sure Gmail API is enabled (Step 3)
2. Check OAuth consent screen is configured (Step 4)
3. Add your test users if using "External" user type

---

## 🎯 After Setup

Once `credentials.json` is in place:

1. **Users can connect:** Each user visits `/gmail/` and clicks "Connect Gmail Account"
2. **One-time per user:** They log in with Google once
3. **Automatic after:** Token stored, works forever
4. **Send RFQs:** Users can now send RFQ emails from Supply dashboard

---

## 📞 Need Help?

If you encounter issues:
1. Check the error message carefully
2. Verify all 6 steps above
3. Restart Django server after adding credentials.json
4. Check Django logs for specific error messages

---

## ✅ Checklist

- [ ] Created Google Cloud project
- [ ] Enabled Gmail API
- [ ] Created OAuth2 credentials
- [ ] Downloaded credentials.json
- [ ] Renamed file to credentials.json
- [ ] Placed in project root: `/Users/apple/Documents/DataScienceProjects/ERP/credentials.json`
- [ ] Restarted Django server
- [ ] Tested connection at /gmail/

**Once all checked, users can connect their Gmail!** ✅
