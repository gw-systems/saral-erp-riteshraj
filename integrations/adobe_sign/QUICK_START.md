# Adobe Sign Integration - Quick Start Guide

## 🚀 Get Up and Running in 10 Minutes

### Step 1: Get Adobe Sign Integration Key (5 minutes)

1. Log in to **Adobe Sign** as administrator (Vivek's account)
2. Navigate to: **Account → Adobe Sign API → Integration Keys**
3. Click **"Create Integration Key"**
4. Name it: "Godamwale ERP"
5. **IMPORTANT:** Copy the key immediately (shown only once!)

### Step 2: Add to .env File (1 minute)

Open `/Users/apple/Documents/DataScienceProjects/ERP/.env` and add:

```bash
# Adobe Sign Integration
ADOBE_SIGN_INTEGRATION_KEY=paste_your_key_here
ADOBE_SIGN_BASE_URL=https://api.in1.adobesign.com/api/rest/v6
ADOBE_SIGN_DIRECTOR_EMAIL=vivek.tiwari@godamwale.com
```

### Step 3: Run Database Migrations (2 minutes)

```bash
cd /Users/apple/Documents/DataScienceProjects/ERP
source venv/bin/activate  # activate your virtualenv
python manage.py makemigrations adobe_sign
python manage.py migrate
```

### Step 4: Create Initial Settings (1 minute)

```bash
python manage.py shell
```

```python
from integrations.adobe_sign.models import AdobeSignSettings
settings = AdobeSignSettings.objects.create(
    director_name='Vivek Tiwari',
    director_email='vivek.tiwari@godamwale.com',
    director_title='Director'
)
exit()
```

### Step 5: Start Server & Test (1 minute)

```bash
python manage.py runserver
```

Visit: http://localhost:8000/integrations/adobe-sign/

**You should see:**
- ✅ Green checkmarks on settings page
- Dashboard with statistics (all zeros initially)
- "Create New Agreement" button

---

## 🎯 Create Your First Agreement

### As Backoffice:

1. Click **"Create New Agreement"**
2. **Upload PDF:** Drag & drop a scanned contract
3. **Place Signature Blocks:**
   - Click "Director Signature" button
   - Click on PDF where signature should go
   - See green box appear
   - Drag to reposition, resize from corner
   - Repeat for Director Date, Client Signature, Client Date
4. **Fill Details:**
   - Agreement Name: "Test NDA"
   - Client Name: "ABC Company"
   - Client Email: "test@example.com"
   - Signing Flow: "Director signs first, then client"
5. Click **"Submit for Director Approval"**

### As Director:

1. Go to **"Pending Approvals"**
2. Click **"Review"** on the test agreement
3. Embedded Adobe viewer loads with your document
4. Verify signature blocks are correctly placed
5. Click **"Approve & Send to Client"**

### Check Results:

- Agreement status changes to "Approved - Sent"
- Client receives email from Adobe Sign
- You can track progress in agreement detail page

---

## 🔍 Verify Everything Works

### Check Adobe Sign Account:
1. Log in to Adobe Sign
2. Go to "Agreements"
3. Your test agreement should be there
4. Signature fields should be at exact positions you clicked

### Check Email:
- Client email should have received Adobe Sign notification
- Contains signing link

### Check ERP:
- Agreement shows correct status
- Audit trail shows all events
- Can sync status from Adobe

---

## ⚠️ Troubleshooting

### "Integration key is missing"
→ Check `.env` file has ADOBE_SIGN_INTEGRATION_KEY

### "No module named 'integrations.adobe_sign'"
→ Run migrations first: `python manage.py migrate`

### PDF viewer doesn't load
→ Check browser console for errors
→ Ensure PDF.js CDN is accessible

### Signature blocks not appearing in Adobe
→ Check if agreement was created successfully
→ View Adobe Sign account to verify
→ Try syncing status

---

## 📊 What Each Role Sees

### Backoffice:
- Dashboard with all agreements
- Create new agreement (with visual signature placement)
- Edit drafts and rejected agreements
- View agreement details
- **NO ACCESS to Adobe Sign**

### Director (Vivek Tiwari):
- Pending approvals list
- Review page with embedded Adobe viewer
- Approve/reject buttons
- Embedded signing (if needed)
- Send reminders, cancel agreements

### Admin:
- All of the above
- Template management
- Settings configuration
- Complete audit trails

---

## 🎓 Training Notes for Backoffice

### How to Place Signature Blocks (2 minutes to learn):

1. **Upload PDF** → It appears in viewer on right side
2. **Click field type button** on left (e.g., "Director Signature")
3. **Click on PDF** where you want to place it
4. **See colored box appear:**
   - Green = Director's fields
   - Orange = Client's fields
5. **Adjust if needed:**
   - Drag to move
   - Drag corner to resize
   - Click X to delete
6. **Repeat** for other fields (typically 4 total: 2 signatures + 2 dates)
7. **Fill form** on left with client details
8. **Submit for approval**

**That's it!** No Adobe interface, no external tools, all in ERP.

---

## 📝 Common Workflows

### Create Standard NDA:
1. Upload scanned NDA
2. Place 4 fields: Director Sig, Director Date, Client Sig, Client Date
3. Set flow: "Director signs first, then client"
4. Submit

### Client-Only Agreement (Director already signed):
1. Upload PDF with director's wet signature
2. Place only client fields: Client Sig, Client Date
3. Set flow: "Client only"
4. Submit

### Urgent Agreement (Parallel Signing):
1. Upload PDF
2. Place all fields
3. Set flow: "Parallel signing"
4. Both director and client sign simultaneously

---

## 🚨 Important Notes

### DO:
- ✅ Test with sample PDFs first
- ✅ Verify signature blocks are correctly placed before submitting
- ✅ Double-check client email addresses
- ✅ Keep Adobe Sign account credentials secure

### DON'T:
- ❌ Give backoffice access to Adobe Sign account
- ❌ Place too many signature fields (max 4-6 per document)
- ❌ Submit without reviewing placement
- ❌ Share integration key publicly

---

## 📞 Need Help?

### Common Questions:

**Q: Can I save signature block positions as templates?**
A: Not yet - this is a future enhancement. Currently, you place blocks per-agreement.

**Q: What if I make a mistake in placement?**
A: Director will see it during review and can reject with feedback. You can then fix and resubmit.

**Q: Can I edit after director approves?**
A: No - once approved and sent to client, it's locked. Cancel and recreate if needed.

**Q: What file types are supported?**
A: PDF only. Maximum 25MB.

**Q: How long does client have to sign?**
A: Default is 30 days, configurable per agreement.

---

## ✅ Success Checklist

- [ ] Adobe Sign integration key added to .env
- [ ] Database migrations run successfully
- [ ] Initial settings created
- [ ] Server starts without errors
- [ ] Dashboard loads and shows green checkmarks on settings page
- [ ] Created test agreement with visual signature placement
- [ ] Director reviewed and approved test agreement
- [ ] Test client received email from Adobe Sign
- [ ] Agreement status syncs correctly from Adobe
- [ ] Downloaded signed PDF after completion

---

## 🎉 You're All Set!

The system is now ready for production use. Start with a few test agreements to get comfortable with the workflow, then roll out to full backoffice team.

**Estimated time to proficiency:**
- Backoffice: 30 minutes
- Director: 10 minutes

**The visual signature placement tool is so intuitive that minimal training is needed!**
