# Godamwale Portal Ecosystem — Design & Implementation Plan

## Context

Godamwale currently coordinates with clients and vendors via WhatsApp groups and email. Every client project has a WhatsApp group (GW + Client), and each vendor has a group covering their projects. All operational coordination — daily updates, document exchange, billing disputes, decisions — happens through these unstructured channels. This creates:
- No audit trail or searchable history
- Documents scattered across WhatsApp/email
- No structured dispute or query tracking
- GW team manually bridges client ↔ vendor communication
- No data ownership or control

**Goal**: Build two separate portal applications (Client Portal + Vendor Portal) that replace WhatsApp/email with enterprise-grade project-scoped communication, structured document exchange, and self-service operations. Saral ERP remains the single source of truth, exposing a REST API that both portals consume. Monthly billing is ERP-internal only — portals do NOT show billing data.

---

## Architecture

```
┌─────────────────────────┐     ┌──────────────────────────┐     ┌──────────────────────────┐
│     SARAL ERP            │     │    CLIENT PORTAL          │     │    VENDOR PORTAL          │
│     (Internal Ops)       │     │    (External)             │     │    (External)             │
│                          │     │                           │     │                           │
│  erp.godamwale.com       │     │  client.godamwale.com     │     │  vendor.godamwale.com     │
│  Cloud Run Instance #1   │     │  Cloud Run Instance #2    │     │  Cloud Run Instance #3    │
│  PostgreSQL DB: erp_prod │     │  PostgreSQL DB: client_db │     │  PostgreSQL DB: vendor_db │
│  GCS: erp-media-prod     │     │  GCS: client-portal-media │     │  GCS: vendor-portal-media │
│                          │     │                           │     │                           │
│  ┌────────────────────┐  │     │  Django app               │     │  Django app               │
│  │  api/ app (NEW)    │◄─┼─────┤  Calls ERP API            │     │  Calls ERP API            │
│  │  DRF + API keys    │◄─┼─────┤  (X-API-Key header)       │─────┤  (X-API-Key header)       │
│  │  Token auth        │  │     │                           │     │                           │
│  └────────────────────┘  │     │  Email+OTP auth           │     │  Email+OTP auth           │
└─────────────────────────┘     └──────────────────────────┘     └──────────────────────────┘
```

**Key decisions:**
- 3 separate Cloud Run instances, 3 separate PostgreSQL databases, 3 separate GCS buckets
- Django for all three (same tech stack = code reuse)
- Email + OTP authentication for portal users (no passwords)
- API key auth between portals and ERP + email ID whitelisting (only GW-registered portal user emails can authenticate)
- Project-scoped enterprise-grade conversation threads replace WhatsApp groups
- Portal uploads to own GCS bucket, ERP syncs via API notification with retry-until-success
- Monthly Billing is ERP-internal only — NOT exposed to client or vendor portals
- Portal user management is GW Admin only (not client/vendor self-service)
- Portal users are independently onboarded — NOT linked to ClientContact/VendorContact records in ERP
- Responsive design from Phase 1 (future Android app possible)

---

## Implementation Phases

### Phase 1: ERP API Layer (`api/` app inside Saral ERP)

**New Django app:** `api/` inside existing ERP project

**Install:** Django REST Framework + `djangorestframework` in requirements.txt

**Files to create:**
- `api/__init__.py`
- `api/apps.py`
- `api/urls.py` — all API route definitions
- `api/authentication.py` — API key auth + portal token auth + email whitelist validation
- `api/permissions.py` — client-only, vendor-only, portal-specific permissions
- `api/serializers/` — DRF serializers organized by domain:
  - `projects.py` — ProjectCode, ProjectDocument serializers
  - `quotations.py` — Quotation, QuotationLocation, QuotationItem serializers
  - `disputes.py` — DisputeLog, DisputeComment serializers (bidirectional: portal ↔ ERP)
  - `supply.py` — VendorCard, VendorWarehouse, RFQ serializers
  - `agreements.py` — EscalationTracker, AgreementRenewalTracker serializers
  - `threads.py` — Message sync serializers
  - `auth.py` — OTP request/verify serializers
- `api/views/` — DRF viewsets organized by domain (matching serializers)
- `api/models.py` — APIKey model, PortalUser whitelist model, OTP model, PortalSession model
- `api/throttling.py` — rate limiting per API key
- `api/middleware.py` — request logging, API key validation

**API Key Model:**
```python
class APIKey(models.Model):
    name = models.CharField(max_length=100)  # "client-portal", "vendor-portal"
    key_hash = models.CharField(max_length=128)  # SHA256 of actual key
    portal_type = models.CharField(choices=[('client', 'Client'), ('vendor', 'Vendor')])
    is_active = models.BooleanField(default=True)
    rate_limit = models.IntegerField(default=1000)  # requests per hour
    created_at = models.DateTimeField(auto_now_add=True)
```

**Portal User Whitelist Model (in ERP):**
```python
class PortalUserWhitelist(models.Model):
    """GW Admin registers which emails can log into portals.
    NOT linked to ClientContact/VendorContact — independent list."""
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15, blank=True)
    portal_type = models.CharField(choices=[('client', 'Client'), ('vendor', 'Vendor')])
    # For client portal users:
    client_code = models.ForeignKey('projects.ClientCard', null=True, blank=True, on_delete=models.SET_NULL)
    # For vendor portal users:
    vendor_code = models.ForeignKey('supply.VendorCard', null=True, blank=True, on_delete=models.SET_NULL)
    warehouse_codes = models.JSONField(default=list, blank=True)  # vendor: which warehouses they can see
    project_ids = models.JSONField(default=list, blank=True)  # optional: restrict to specific projects
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

**API Endpoints (v1):**

| Group | Endpoint | Method | Portal | Purpose |
|-------|----------|--------|--------|---------|
| Auth | `/api/v1/auth/verify-email/` | POST | Both | Check if email is in PortalUserWhitelist |
| Auth | `/api/v1/auth/send-otp/` | POST | Both | Send 6-digit OTP to whitelisted email (5-min expiry, 3 attempts) |
| Auth | `/api/v1/auth/verify-otp/` | POST | Both | Validate OTP, return session token |
| Projects | `/api/v1/projects/` | GET | Both | List projects (filtered by whitelist's client_code or vendor warehouse_codes) |
| Projects | `/api/v1/projects/{id}/` | GET | Both | Project detail (includes thread_visibility setting) |
| Projects | `/api/v1/projects/{id}/daily-ops/` | GET | Client | Daily space utilization |
| Projects | `/api/v1/projects/{id}/documents/` | GET | Both | Project documents (signed GCS URLs) |
| Quotations | `/api/v1/quotations/` | GET | Client | List quotations for client |
| Quotations | `/api/v1/quotations/{id}/` | GET | Client | Quotation detail with locations + items (client rates only) |
| Quotations | `/api/v1/quotations/{id}/respond/` | POST | Client | Accept/reject quotation |
| Disputes | `/api/v1/disputes/` | GET/POST | Both | List or create disputes (bidirectional) |
| Disputes | `/api/v1/disputes/{id}/` | GET | Both | Dispute detail + activity |
| Disputes | `/api/v1/disputes/{id}/comments/` | GET/POST | Both | Thread comments on dispute |
| Queries | `/api/v1/queries/` | GET/POST | Both | GW team raises queries FROM ERP → visible in portal. Client/vendor responds. |
| RFQ | `/api/v1/rfqs/` | GET | Vendor | RFQ inbox (filtered by vendor_code via VendorContact traversal) |
| RFQ | `/api/v1/rfqs/{id}/` | GET | Vendor | RFQ detail |
| RFQ | `/api/v1/rfqs/{id}/respond/` | POST | Vendor | Submit quoted rate |
| Rate Cards | `/api/v1/rate-cards/{project_id}/` | GET | Both | Current rate card (filtered by role) |
| Agreements | `/api/v1/escalations/` | GET | Client | Escalation notices (client acknowledgment) |
| Agreements | `/api/v1/renewals/` | GET | Both | Renewal notices (client-side + vendor agreement renewal) |
| Warehouses | `/api/v1/warehouses/` | GET | Vendor | Vendor's warehouses |
| LR | `/api/v1/lorry-receipts/` | GET | Vendor | LRs for vendor projects |
| Uploads | `/api/v1/uploads/notify/` | POST | Both | Notify ERP of new file uploaded to portal bucket (retry-until-success) |
| Threads | `/api/v1/threads/{project_id}/` | GET | Both | Get message thread for project |
| Threads | `/api/v1/threads/{project_id}/messages/` | POST | Both | Post message (portal user or GW team) |
| Notifications | `/api/v1/notifications/push/` | POST | Internal | ERP pushes notification to portal |
| Dashboard | `/api/v1/dashboard/summary/` | GET | Both | Aggregated counts across all accessible projects |
| Profile | `/api/v1/profile/` | GET | Both | Company details |
| Admin | `/api/v1/admin/portal-users/` | GET/POST/PATCH | Internal | GW admin manages portal user whitelist |

**Dispute model changes needed in ERP (`operations/models.py`):**
```python
# Add to DisputeLog:
raised_by_external = models.CharField(max_length=200, blank=True)  # "Client: John Doe" or "Vendor: Ravi Kumar"
raised_by_portal = models.CharField(
    max_length=10, choices=[('client', 'Client'), ('vendor', 'Vendor'), ('internal', 'Internal')],
    default='internal'
)
invoice_number = models.CharField(max_length=100, blank=True)  # client enters exact invoice number
```

**Dispute flow (bidirectional):**
- Client/vendor raises dispute in portal → API creates DisputeLog in ERP with `raised_by_portal='client'/'vendor'` + `raised_by_external='Client: Name'`
- Visible to: coordinator, manager, controller, director, admin in ERP
- GW team can also raise queries FROM ERP against client/vendor → reflected in respective portal
- Comments flow back and forth between ERP and portal

**Critical data isolation rules (enforced in API views):**
- Client portal: ONLY access data where project's client_code matches requesting user's client_code
- Vendor portal: ONLY access data where project's vendor_warehouse.vendor_code matches requesting user's vendor_code
- Client NEVER sees: vendor rates, vendor costs, vendor billing
- Vendor NEVER sees: client rates, client billing, quotation pricing
- Monthly Billing: NOT exposed via API at all (ERP-internal only)

**RFQ API filtering fix:**
- RFQ endpoint filters by `vendor_contact__vendor_code == requesting_vendor_code` (traverses VendorContact → VendorCard) rather than requiring exact contact match. This ensures all RFQs sent to ANY contact at that vendor company are visible.

**OTP email delivery:**
- OTP sending happens via ERP API (`/api/v1/auth/send-otp/`) — ERP sends OTP using its existing Gmail API infrastructure (`gmail/services.py` EmailService). This keeps email infra centralized in ERP.

**Existing code to reuse:**
- `projects/models.py` — ProjectCode model (line ~50)
- `projects/models_client.py` — ClientCard, ClientContact, ClientGST
- `projects/models_quotation.py` — Quotation, QuotationAcceptanceToken (public accept pattern at views_quotation.py)
- `operations/models.py` — DisputeLog, DisputeComment, DailySpaceUtilization
- `operations/models_agreements.py` — EscalationTracker, AgreementRenewalTracker
- `operations/models_lr.py` — LorryReceipt
- `supply/models.py` — VendorCard, VendorWarehouse, RFQ, RFQVendorMapping
- `accounts/models.py` — Notification model (reuse notification_type choices)
- `gmail/services.py` — EmailService for OTP delivery

---

### Phase 2: Client Portal (separate Django project)

**New repo:** `godamwale-client-portal/`

**Tech:** Django 5.2 + HTMX + Alpine.js — responsive from day one (mobile-compatible, future Android app possible)

**Portal-Local Models (client_db):**

```python
# auth — portal users are independently managed by GW Admin via ERP whitelist
PortalUser          — email (unique), name, phone, client_code (str ref to ERP),
                      designation, is_active, last_login_at
OTPSession          — email, otp_hash (SHA256), expires_at, attempts_count, created_at
LoginSession        — user (FK), session_token (UUID), created_at, expires_at,
                      ip_address, user_agent, is_active

# messaging — enterprise-grade project-scoped threads (NOT WhatsApp clone)
ProjectThread       — project_id (str ref to ERP), project_name (cached),
                      thread_visibility (isolated/vendor_in_client, synced from ERP),
                      created_at, is_archived, last_message_at
ThreadMessage       — thread (FK), sender_type (client/gw_team/vendor),
                      sender_name, sender_designation,
                      body (text), attachments (JSON: [{name, url, size, type}]),
                      is_read_by_client (bool), is_read_by_gw (bool),
                      is_pinned (bool), reply_to (self FK, nullable),
                      created_at, edited_at
ThreadParticipant   — thread (FK), user (FK), role (member/admin), joined_at

# documents & uploads
DocumentUpload      — user (FK), project_id, doc_type (general/approval/agreement),
                      file_url (GCS), file_name, file_size, uploaded_at,
                      synced_to_erp (bool), erp_sync_at,
                      sync_retry_count (int), last_sync_attempt (datetime)

# disputes — raised in portal, visible in ERP
PortalDispute       — user (FK), project_id, title, description,
                      invoice_number (CharField — exact invoice # for the project),
                      category (operations/billing/documentation/other),
                      priority (low/medium/high),
                      erp_dispute_id (str — synced back from ERP after creation),
                      status (open/in_progress/resolved/closed),
                      created_at, resolved_at

# change requests
ChangeRequest       — user (FK), entity_type (company/contact/gst),
                      field_name, old_value, new_value,
                      status (pending/approved/rejected),
                      reviewed_by, reviewed_at, created_at

# notifications
PortalNotification  — user (FK), notification_type, title, message,
                      project_id, link_url, is_read, created_at

# audit
AuditLog            — user (FK), action, resource_type, resource_id,
                      ip_address, details (JSON), created_at
```

**Screens:**

| Screen | Route | Description |
|--------|-------|-------------|
| Login | `/login/` | Email input → OTP verify → Dashboard |
| Dashboard | `/` | Aggregate: project count, open disputes, pending escalations, unread messages across all projects |
| My Projects | `/projects/` | Active projects with status badges (Active/Notice Period). Search/filter. |
| Past Projects | `/projects/past/` | Inactive projects (read-only access, historical view) |
| Project Detail | `/projects/{id}/` | Tabs: Overview, Conversations, Documents, Disputes |
| Project Overview | `/projects/{id}/overview/` | Daily ops chart, current rate card, agreement status, escalation notices |
| Project Conversation | `/projects/{id}/conversation/` | Enterprise thread with GW team. Text + file attachments. Reply threading. Pinned messages. Search. When `vendor_in_client` mode: vendor messages shown with distinct styling. |
| Project Documents | `/projects/{id}/documents/` | Agreements, uploaded docs. Upload new docs. Download links. |
| Project Disputes | `/projects/{id}/disputes/` | List disputes (portal-raised + GW-raised queries). Raise new dispute with invoice number. Comment thread per dispute. |
| Quotations | `/quotations/` | Received quotations, accept/reject, revision history |
| Quotation Detail | `/quotations/{id}/` | Full quotation view (client pricing only), accept/reject |
| Notifications | `/notifications/` | All notifications with read/unread |
| Profile | `/profile/` | Company info (read-only), request changes |

**Removed from client portal:** Billing tab (Monthly Billing is ERP-internal only)

---

### Phase 3: Vendor Portal (separate Django project)

**New repo:** `godamwale-vendor-portal/`

**Tech:** Django 5.2 + HTMX + Alpine.js — responsive from day one

**Portal-Local Models (vendor_db):**

```python
# auth — independently managed by GW Admin
PortalUser          — email, name, phone, vendor_code (str ref to ERP),
                      warehouse_codes (JSON), designation, is_active, last_login_at
OTPSession          — same as client
LoginSession        — same as client

# messaging — enterprise-grade threads
ProjectThread       — same as client (project-scoped, includes thread_visibility)
ThreadMessage       — thread (FK), sender_type (vendor/gw_team/client),
                      sender_name, sender_designation,
                      body, attachments (JSON), is_read_by_vendor, is_read_by_gw,
                      is_pinned, reply_to (self FK), created_at
ThreadParticipant   — same as client

# vendor-specific uploads — replaces email-based invoice/MIS submission
InvoiceUpload       — user (FK), project_id, service_month (date),
                      file_url (GCS), file_name, invoice_number,
                      amount, status (uploaded/acknowledged/processed),
                      uploaded_at, acknowledged_at,
                      synced_to_erp (bool), sync_retry_count, last_sync_attempt
MISUpload           — user (FK), project_id, service_month,
                      file_url (GCS), file_name,
                      status (uploaded/reviewed/accepted/rejected),
                      reviewer_notes, uploaded_at,
                      synced_to_erp (bool), sync_retry_count, last_sync_attempt
WarehouseDocUpload  — user (FK), warehouse_code, doc_type,
                      file_url (GCS), file_name, uploaded_at,
                      synced_to_erp (bool), sync_retry_count, last_sync_attempt
RFQResponseDraft    — user (FK), rfq_id, quoted_rate, notes,
                      attachment_url, is_submitted, created_at, submitted_at

# disputes — same pattern as client
PortalDispute       — user (FK), project_id, title, description,
                      invoice_number, category, priority,
                      erp_dispute_id, status, created_at, resolved_at

# same shared models
ChangeRequest       — same as client
PortalNotification  — same as client
AuditLog            — same as client
```

**Screens:**

| Screen | Route | Description |
|--------|-------|-------------|
| Login | `/login/` | Email + OTP (whitelisted emails only) |
| Dashboard | `/` | Aggregate: warehouses count, active projects, pending RFQs, unread messages, open disputes |
| My Warehouses | `/warehouses/` | List warehouses with capacity, status |
| Warehouse Detail | `/warehouses/{code}/` | Profile, capacity, commercial terms, documents, upload docs |
| My Projects | `/projects/` | Active projects using vendor's warehouses |
| Past Projects | `/projects/past/` | Inactive projects (read-only) |
| Project Detail | `/projects/{id}/` | Tabs: Overview, Conversation, Uploads, Disputes |
| Project Overview | `/projects/{id}/overview/` | Agreement status, renewal notices |
| Project Conversation | `/projects/{id}/conversation/` | Enterprise thread with GW team. When `vendor_in_client`: also shows "Client Conversation" tab. |
| Project Uploads | `/projects/{id}/uploads/` | Upload invoices, MIS per month per project (replaces email). Status tracking (uploaded → acknowledged → processed). |
| Project Disputes | `/projects/{id}/disputes/` | Raise disputes with invoice number. View GW-raised queries. Comment threads. |
| RFQ Inbox | `/rfqs/` | Received RFQs (all RFQs sent to ANY contact at this vendor company) |
| RFQ Detail | `/rfqs/{id}/` | RFQ details, submit response (rate + notes + attachment) |
| Lorry Receipts | `/lorry-receipts/` | View LRs for vendor's projects |
| Notifications | `/notifications/` | All notifications |
| Profile | `/profile/` | Company info (read-only), request changes |

**Removed from vendor portal:** Billing tab (MonthlyBilling is ERP-internal only)

---

### Phase 4: Thread Sync & Enterprise Messaging

**Enterprise-grade messaging (NOT a WhatsApp clone):**

```
CLIENT PORTAL                    SARAL ERP                      VENDOR PORTAL
─────────────                    ─────────                      ──────────────
ProjectThread (client_db)   ←→   ThreadMessageMirror      ←→   ProjectThread (vendor_db)
ThreadMessage (client_db)        (ERP backup copy)              ThreadMessage (vendor_db)
                                 + unified thread viewer
```

**Per project, TWO independent threads exist:**
1. **Client Thread** — stored in client_db, visible to Client Portal + ERP
2. **Vendor Thread** — stored in vendor_db, visible to Vendor Portal + ERP

**GW team in ERP sees BOTH threads** in a unified project view (via API calls to both portals).

**Three-party visibility (per-project config):**

Add to ProjectCode model in ERP:
```python
thread_visibility = models.CharField(
    max_length=20,
    choices=[
        ('isolated', 'Isolated — two separate threads'),
        ('vendor_in_client', 'Vendor can see client thread'),
    ],
    default='isolated'
)
```

**When `isolated` (default):**
- Client portal: sees client thread only (client + GW messages)
- Vendor portal: sees vendor thread only (vendor + GW messages)
- GW in ERP: sees both threads side-by-side, can forward messages between them

**When `vendor_in_client`:**
- Client portal: sees client thread (client + GW + vendor messages — vendor shown with distinct badge)
- Vendor portal: sees vendor thread (private with GW) AND client thread (three-party — read + write)
- GW in ERP: unified view, all three parties visible
- Vendor still has private thread with GW for sensitive discussions (rates, complaints, etc.)

**Message flow:**
- Client posts message → stored in client_db → ERP notified via webhook → GW sees in ERP → ERP stores mirror copy
- GW replies to client thread → API POST to client portal → stored in client_db → client sees in portal
- Vendor posts in vendor thread → stored in vendor_db → ERP notified → GW sees in ERP → ERP stores mirror copy
- If `vendor_in_client`: vendor can also post in client thread → stored in client_db → visible to client + GW
- GW can forward a message from one thread to another (replaces WhatsApp bridge role)

**ERP-side message backup (ThreadMessageMirror):**
```python
class ThreadMessageMirror(models.Model):
    """Async backup of all portal messages. If portal DB is lost, messages survive."""
    portal_type = models.CharField(choices=[('client', 'Client'), ('vendor', 'Vendor')])
    project_id = models.CharField(max_length=20)
    thread_type = models.CharField(max_length=20)  # client_thread / vendor_thread
    sender_type = models.CharField(max_length=20)
    sender_name = models.CharField(max_length=200)
    body = models.TextField()
    attachments = models.JSONField(default=list)
    original_created_at = models.DateTimeField()
    mirrored_at = models.DateTimeField(auto_now_add=True)
```

**Thread features (enterprise-grade):**
- Threaded replies (reply_to FK — reply to specific messages, not just linear chat)
- File attachments (images, PDFs, Excel) stored in respective portal's GCS bucket
- Read receipts (is_read_by_client/gw/vendor)
- Full-text search within thread
- Pin important messages (is_pinned flag)
- @mention GW team members (resolved via ERP user list API)
- Notification on new message (in-app + email digest option)
- Message edit (within 15-min window)

---

### Phase 5: ERP UI Changes (Thread Viewer + Portal Admin)

**New views inside Saral ERP:**

**A. Thread Viewer (for GW operations team):**
- Project detail page gets new **"Conversations"** tab
- Shows two sub-tabs: **Client Thread** | **Vendor Thread**
- Each shows messages from the respective portal (fetched via API)
- GW team can type replies (sent to respective portal API)
- GW team can forward messages between threads
- Unread message count shown as badge on project list
- When `vendor_in_client`: client thread shows all three parties' messages

**B. Portal User Admin (for GW admin/directors):**
- New screen: **Portal User Management** — CRUD for PortalUserWhitelist
- Add new portal user: email, name, portal_type, client_code/vendor_code, warehouse_codes
- Activate/deactivate portal users
- View login history and audit logs per portal user
- Bulk onboard (CSV upload for new client/vendor contacts)

**C. Dispute Inbox (enhanced):**
- Existing dispute list shows new column: "Source" (Internal / Client Portal / Vendor Portal)
- Filter by source
- Portal-raised disputes show `raised_by_external` name and `invoice_number`
- GW team can raise queries against client/vendor from ERP → pushed to respective portal

**Files to modify in ERP:**
- `projects/models.py` — add `thread_visibility` field to ProjectCode
- `operations/models.py` — add `raised_by_external`, `raised_by_portal`, `invoice_number` to DisputeLog
- `projects/urls.py` — add conversation routes + portal admin routes
- `projects/views.py` — add thread viewer views (API consumer)
- `templates/projects/project_detail.html` — add Conversations tab
- New templates: `templates/projects/project_conversations.html`, `templates/api/portal_user_admin.html`
- New migration for ThreadMessageMirror, PortalUserWhitelist

---

## Upload Sync — Retry Until Success

When a portal uploads a file and needs to notify ERP:

```
Portal uploads file to GCS bucket
    ↓
POST to /api/v1/uploads/notify/ on ERP
    ↓
Success? → Mark synced_to_erp=True, done
    ↓
Failure? → Increment sync_retry_count, schedule retry
    ↓
Retry schedule: 30s → 1min → 5min (exponential backoff)
    ↓
3 consecutive failures? → ALERT: flag as potential code/infra issue
    → Send notification to GW admin in ERP
    → Mark upload as "sync_failed" with error details
    → Do NOT keep retrying indefinitely (it's likely a code bug or infra issue)
    ↓
Daily reconciliation job: compare portal GCS bucket contents vs ERP's known uploads
    → Flag any mismatches for manual review
```

**Implementation:** Use Django-Q or Celery for background retry. Each upload model (InvoiceUpload, MISUpload, DocumentUpload, WarehouseDocUpload) has `synced_to_erp`, `sync_retry_count`, `last_sync_attempt` fields.

---

## ERP Availability & Portal Resilience

**Problem:** Both portals depend on ERP API for data. If ERP's Cloud Run instance is down (deploy, crash, cold start), portals show empty pages.

**Solution — multi-layer resilience:**

1. **Cloud Run min-instances:** Set `min-instances=1` on ERP Cloud Run service to eliminate cold starts. This keeps at least one instance always warm.

2. **Portal-side data caching:** Portal caches last-fetched data in its own DB with TTL:
   - Project list, project details: cache in portal DB, refresh every 5 minutes
   - Rate cards, agreement status: cache in portal DB, refresh every 15 minutes
   - Stale data shown with "Last updated X minutes ago" badge during ERP outages
   - Conversations already stored in portal DB — survive ERP downtime natively

3. **API health check:** Portal pings `/api/v1/health/` on page load. If ERP is down:
   - Show cached data with "ERP temporarily unavailable" notice
   - Disable write operations (dispute creation, document upload) until ERP is back
   - Queue write operations locally for replay when ERP recovers

4. **Zero-downtime deploys:** Use Cloud Run's revision-based traffic splitting for blue-green deploys.

---

## Security Model

| Layer | Implementation |
|-------|---------------|
| Network | 3 separate Cloud Run instances. Same GCP project, Cloud Run service-to-service IAM auth. |
| API Auth | API key per portal (SHA256 hashed, stored in ERP). `X-API-Key` + `X-Portal-Type` headers. |
| Email Whitelist | Only emails registered in PortalUserWhitelist can authenticate. GW Admin manages the list. |
| User Auth | Email + OTP: 6-digit code, 5-min expiry, 3 max attempts, SHA256 hashed storage. OTP sent via ERP's Gmail API. |
| Session | Session token (UUID) in HttpOnly + Secure + SameSite=Strict cookie. 24hr expiry. |
| Data Isolation | API enforces: client sees only their projects, vendor sees only their warehouses' projects. |
| File Isolation | Each portal has own GCS bucket. ERP bucket not directly accessible to portals. |
| Rate Limiting | DRF throttling: 100 req/min per user, 1000 req/hr per API key. |
| Audit | Every API call logged. Every portal action in AuditLog. |

---

## Deployment

| Component | Cloud Run Service | Database | GCS Bucket |
|-----------|------------------|----------|------------|
| Saral ERP | `saral-erp` (min-instances=1) | `erp_prod` (Cloud SQL) | `saral-erp-media-prod` |
| Client Portal | `gw-client-portal` | `client_portal_db` (Cloud SQL) | `gw-client-portal-media` |
| Vendor Portal | `gw-vendor-portal` | `vendor_portal_db` (Cloud SQL) | `gw-vendor-portal-media` |

All three use the same GCP project, same region, Dockerized Django deployments.

---

## Project Lifecycle Management

| Project Status | Portal Behavior |
|----------------|----------------|
| **Active** | Full access: conversations, disputes, uploads, documents, quotations |
| **Notice Period** | Full access + "Notice Period" badge shown prominently. Conversation shows notice period dates. |
| **Inactive** | Moves to "Past Projects" section. Read-only: can view conversations, documents, dispute history. Cannot: post new messages, raise disputes, upload files. |

---

## Zoho-Inspired Enhancements

Based on forensic analysis of Zoho ERP demo (66-min, 16 modules, 240+ reports) — see `zoho_analysis/output/` for full reports. Below are Zoho features adapted to enhance all 3 portals.

### A. Security Hardening (from Security Audit — CRITICAL gaps identified)

The Zoho security comparison revealed these gaps in Saral ERP that MUST be addressed before exposing API to external portals:

| Priority | Enhancement | Zoho Has | Saral Status | Action |
|----------|-------------|----------|--------------|--------|
| CRITICAL | MFA/2FA | TOTP + SMS + Zoho OneAuth | NOT IMPLEMENTED | Add `django-otp` to ERP. For portals, OTP login IS the 2FA (email-based). |
| CRITICAL | Rate Limiting | API rate limits per org | NOT IMPLEMENTED | Add `django-ratelimit` to ERP endpoints. DRF throttling for API. All 3 systems. |
| HIGH | CSP Headers | Content-Security-Policy | NOT CONFIGURED | Add `django-csp` to all 3 Django projects. |
| HIGH | Secret Manager | Zoho internal key mgmt | `.env` files | Migrate ERP + portals to Google Secret Manager for production secrets. |
| MEDIUM | Cloud Armor WAF | Enterprise DDoS | GCP default only | Enable Cloud Armor in front of all 3 Cloud Run services. |
| MEDIUM | File Upload Validation | Server-side validation | Size-only (10MB) | Add MIME type validation + virus scan for all portal uploads. |
| MEDIUM | API Key Rotation | Managed internally | No rotation mechanism | Add key rotation API: generate new key, grace period, deactivate old. |
| LOW | Encryption Upgrade | AES-256 | Fernet (AES-128-CBC) | Upgrade to AES-256-GCM for token storage in ERP. |

### B. Client Portal Enhancements (inspired by Zoho Customer Portal)

Zoho's Customer Portal offers: view transactions, download statements, collaboration space, quotation acceptance, automated reminders, dashboard KPIs.

**B1. Dashboard KPIs (Zoho-style cards)**
Zoho shows: Outstanding Receivables, Overdue Invoices, Avg Days to Pay, Net P&L.
Our client dashboard should show KPI cards:
- Active Projects count
- Open Disputes count (with "X overdue" badge)
- Pending Escalations (approaching/overdue)
- Upcoming Renewals (next 60 days)
- Unread Messages count
- Recent Activity feed (last 5 actions across all projects)

**B2. Document Downloads (Zoho has statement downloads)**
Even without billing, clients need downloadable documents:
- Rate card PDF (current rates for each project)
- Agreement documents (download from ERP's ProjectDocument)
- Quotation PDF (already exists — reuse QuotationAcceptanceToken PDF generation pattern from `projects/views_quotation.py`)
- Dispute summary report (PDF export of all disputes for a project)

**B3. Automated Notifications (Zoho has payment reminders)**
Replace Zoho's payment reminders with Godamwale-relevant automated alerts:
- Escalation approaching (30 days before effective date) → portal notification + email
- Agreement renewal due (60 days before end date) → portal notification + email
- New quotation received → portal notification
- Dispute status changed → portal notification
- New message in conversation → portal notification (real-time) + email digest (daily/weekly configurable)

**B4. Report Scheduling (Zoho: "Schedule & Share")**
Allow clients to schedule automated email reports:
- Weekly project summary (active projects, open items)
- Monthly dispute summary
- Configurable: frequency (weekly/monthly), day of week, email recipients
- Portal model: `ScheduledReport — user (FK), report_type, frequency, day_of_week, recipients (JSON), is_active`

**B5. Activity Timeline (Zoho: "Activity logs per user")**
Project-level activity timeline showing all events:
- "Dispute #D-001 raised by you" — timestamp
- "GW team replied to your message" — timestamp
- "Quotation QT-042 sent to you" — timestamp
- "Agreement escalation 3% applied" — timestamp
- Filterable by type: disputes, messages, documents, agreements

### C. Vendor Portal Enhancements (inspired by Zoho Vendor Portal)

Zoho's Vendor Portal offers: upload purchase bills, view transactions, MSME details, bank details for payout, RFQ response with comparison.

**C1. Dashboard KPIs**
- Active Warehouses count
- Active Projects count
- Pending RFQs (awaiting response)
- Open Disputes count
- Invoice Upload Status (this month: X uploaded, Y pending, Z acknowledged)
- Unread Messages count

**C2. Invoice Upload Calendar View**
Zoho tracks invoice status. Enhance our upload tracking:
- Calendar grid showing each month × project → upload status (uploaded/pending/acknowledged/processed)
- Visual: green (processed), yellow (uploaded/waiting), red (overdue — past deadline, not uploaded)
- Deadline configurable per project from ERP (e.g., "invoice due by 5th of next month")

**C3. Vendor Bank Details (Zoho stores for payout)**
Add to vendor profile:
- Bank name, account number, IFSC, account holder name
- UPI ID (optional)
- Stored in portal DB (encrypted), synced to ERP for payment processing
- Change request workflow for bank detail updates (fraud prevention)

**C4. MSME Details (Zoho captures for compliance)**
If vendor is MSME-registered:
- MSME registration number, category (Micro/Small/Medium), certificate upload
- Displayed on vendor profile in ERP
- Important for compliance: MSME vendors must be paid within 45 days (legal requirement)

**C5. RFQ Response Enhancement**
Zoho has multi-vendor bidding with comparison & award. Enhance our RFQ:
- Vendor sees: requirement details, deadline, city, area needed
- Vendor responds: quoted rate, availability date, special terms, attachment
- **New in ERP:** RFQ Comparison View — side-by-side comparison of all vendor responses for GW team, sortable by rate, with "Award" button
- Notification to vendor when awarded or not

### D. Saral ERP Enhancements (for portal management)

**D1. Unified Notification Center (Zoho: bell icon with badge count)**
ERP already has a Notification model. Enhance:
- Real-time badge count on project list (unread portal messages per project)
- Notification categories: portal_message, portal_dispute, portal_upload, portal_query
- Quick-action from notification (click → go to conversation/dispute)

**D2. Portal Analytics Dashboard (Zoho: 240+ reports)**
New ERP dashboard for portal health:
- Active portal users (client + vendor)
- Messages per day (trend chart)
- Disputes raised (portal vs internal, trend)
- Upload compliance (% vendors uploading invoices on time)
- Average response time (GW team reply to portal message)
- Login activity (logins per day, active users)

**D3. Transaction Locking (Zoho: prevents editing historical entries)**
Relevant for portal data:
- Lock disputes after resolution (no further comments)
- Lock uploads after processing (no re-upload)
- Lock RFQ responses after award
- Already partially exists in billing (`edit_locked_at`) — extend pattern

**D4. Bulk Portal User Onboarding (inspired by Zoho's CSV import)**
Zoho supports "Bulk import via sample CSV templates (25MB max)."
- GW Admin can upload CSV: email, name, phone, portal_type, client_code/vendor_code
- Validate all emails, client/vendor codes against ERP
- Preview before commit
- Send welcome email with first OTP to all new users

---

## Implementation Order

1. **Phase 1: ERP API layer + Security Hardening** — `api/` app with DRF, API key auth, PortalUserWhitelist, OTP via Gmail, rate limiting (`django-ratelimit`), CSP headers (`django-csp`), MFA for ERP (`django-otp`), Secret Manager migration
2. **Phase 2: Client Portal MVP** — Auth + Dashboard (KPI cards: projects/disputes/escalations/messages) + Projects + Conversations (enterprise threads). Responsive from day one.
3. **Phase 3: Client Portal Full** — Disputes (with invoice #), queries, quotation accept/reject, document downloads (rate card PDF, agreements), escalation/renewal notices, activity timeline
4. **Phase 4: Vendor Portal MVP** — Auth + Dashboard (KPI cards: warehouses/projects/RFQs/uploads) + Warehouses + Projects + Conversations
5. **Phase 5: Vendor Portal Uploads** — Invoice/MIS upload per project with calendar view (replaces email), retry-until-success sync, upload deadline tracking
6. **Phase 6: Vendor Portal Full** — RFQ response + ERP-side RFQ comparison view, disputes, LR view, renewal notices, vendor bank details, MSME details
7. **Phase 7: ERP Thread Viewer + Portal Admin** — GW team conversation UI + portal user management (CRUD + bulk CSV onboarding) + unified notification center with badge counts
8. **Phase 8: Three-Party Threads** — thread_visibility config, vendor-in-client mode
9. **Phase 9: Notifications + Automation** — Push notifications from ERP to portals, automated escalation/renewal alerts, email digests (daily/weekly configurable), scheduled report emails
10. **Phase 10: Polish + Analytics** — Search, project lifecycle (past projects), vendor invoice reconciliation, portal analytics dashboard (ERP), transaction locking, Cloud Armor WAF, load testing, file upload MIME validation

---

## Verification

After each phase:

**Core functionality:**
1. Run Django `check` and `test` commands on all three projects
2. Test API endpoints via Postman/httpie with valid and invalid API keys
3. Verify email whitelist: non-whitelisted email gets rejected at OTP step
4. Verify data isolation: client portal cannot access vendor data and vice versa
5. Test OTP flow end-to-end (send via Gmail API → verify → session → API calls)
6. Test thread messaging: post from portal → appears in ERP → reply from ERP → appears in portal
7. Test three-party thread: set project to `vendor_in_client`, verify vendor sees client thread with distinct styling
8. Test dispute from portal: client raises with invoice #, dispute appears in ERP with external raiser info
9. Test GW query from ERP: coordinator raises query against client → appears in client portal
10. Test upload retry: simulate ERP API failure, verify retry queue works, verify alert after 3 failures
11. Test ERP downtime: bring ERP API down, verify portals show cached data gracefully
12. Test project lifecycle: inactive project → past projects section, read-only, no new messages/disputes
13. Verify MonthlyBilling is NOT accessible via any portal API endpoint
14. Verify file uploads go to correct GCS bucket and ERP receives sync notification
15. Load test API with concurrent requests to verify rate limiting works

**Security (from Zoho audit):**
16. Verify MFA works on ERP login (TOTP via django-otp)
17. Verify rate limiting: 100+ rapid requests get throttled with 429 response
18. Verify CSP headers present on all pages (check via browser dev tools)
19. Verify secrets load from Google Secret Manager in production (not .env)
20. Verify file upload MIME validation: reject .exe, .bat, allow .pdf, .xlsx, .jpg, .png, .docx

**Zoho-inspired features:**
21. Verify dashboard KPIs: correct counts for projects, disputes, escalations, unread messages
22. Verify document download: rate card PDF, agreement PDF, quotation PDF all downloadable
23. Verify automated notifications: escalation approaching → notification appears in portal
24. Verify scheduled reports: configure weekly summary → email received on schedule
25. Verify activity timeline: actions across all types shown chronologically per project
26. Verify vendor upload calendar: correct month × project grid with status colors
27. Verify RFQ comparison view in ERP: all vendor responses side-by-side, award button works
28. Verify bulk user onboarding: CSV upload → preview → create → welcome emails sent
29. Verify portal analytics dashboard: login count, message volume, dispute trends accurate
