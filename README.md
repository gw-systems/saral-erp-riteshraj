# Saral ERP

Warehouse-as-a-Service ERP managing 460+ projects across India.

---

## Quick Start
```bash
git clone https://github.com/godamwale/saral-erp.git
cd saral-erp
python3.11 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file (see Configuration)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Access: http://127.0.0.1:8000

---

## Tech Stack

- **Backend:** Django 5.0, Python 3.11
- **Database:** PostgreSQL 15
- **Cache/Queue:** Redis 7, Celery
- **Frontend:** Tailwind CSS, Vanilla JS

---

## Configuration

Create `.env` file in project root:
```env
# Django
SECRET_KEY=<generate-using-command-below>
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_NAME=erp
DATABASE_USER=admin
DATABASE_PASSWORD=<your-password>
DATABASE_HOST=localhost
DATABASE_PORT=5432

# Redis & Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0

# Timezone
TIME_ZONE=Asia/Kolkata
```

**Generate SECRET_KEY:**
```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

---

## Database Setup
```bash
# Create database
createdb erp

# Or via psql:
sudo -u postgres psql
CREATE DATABASE erp;
CREATE USER admin WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE erp TO admin;
\q

# Run migrations
python manage.py migrate
```

---

## Project Structure
```
accounts/         # User auth, role-based permissions
projects/         # Warehouse project management (460 projects)
operations/       # Daily entries, monthly billing, disputes, project cards
dashboards/       # Role-specific dashboards
integrations/     # Bigin CRM sync
```

---

## Key Models

**User** - Custom model with `role` field (9 roles: admin, coordinator, manager, controller, finance, backoffice, sales, warehouse)

**ProjectCode** - Warehouse projects with client/vendor/location/billing configuration

**DailySpaceUtilization** - Daily space tracking per project

**ProjectCard** - Rate cards with vendor/client pricing (storage/handling/transport/VAS)

**MonthlyBilling** - Monthly billing with multi-level approval workflow

**DisputeLog** - Dispute tracking with 7-day TAT

---

## Role-Based Access

Implemented via `@role_required` decorator in `accounts/permissions.py`

| Role | Access |
|------|--------|
| Coordinator | Own projects, daily entries, raise disputes |
| Manager | All projects, team performance |
| Controller | Billing approval (Level 1) |
| Finance | Billing approval (Level 2) |
| Backoffice | Project setup, rate cards |

---

## Running the Application

**Development:**
```bash
python manage.py runserver
```

**With Background Tasks:**
```bash
# Terminal 1: Celery Worker
celery -A minierp worker --loglevel=info

# Terminal 2: Celery Beat (scheduled tasks)
celery -A minierp beat --loglevel=info
```

---

## LR Local Runbook

Use this flow when you want to test LR DOCX/PDF generation locally with the redesigned `LR.docx` template.

**Minimal `.env` values**
```env
SECRET_KEY=local-dev-secret-key-for-saral-erp-minimum-fifty-characters-long-12345
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

USE_CLOUD_SQL=False
DB_NAME=erp
DB_USER=admin
DB_PASSWORD=Godam@123
DB_HOST=localhost
DB_PORT=5434

ZOHO_CLIENT_ID=local-dummy-zoho-client-id
ZOHO_CLIENT_SECRET=local-dummy-zoho-client-secret
ZOHO_REDIRECT_URI=http://localhost:8000/oauth2callback/

DISABLE_BIGIN_SYNC_LOCAL=True
USE_CLOUD_TASKS=False
```

**Local setup**
```bash
python -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
docker start saral-lr-db
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py createcachetable django_cache_table
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

**Deterministic LR sample data**
```bash
venv\Scripts\python.exe manage.py shell -c "from accounts.models import User; from projects.models import ProjectCode; from operations.models_lr import LorryReceipt, LRLineItem; user=User.objects.get(username='admin'); project=ProjectCode.objects.get(project_id='DUMMYLR01'); lr,_=LorryReceipt.objects.update_or_create(lr_number='GW-9999', defaults={'lr_date':'2026-03-14','project':project,'from_location':'Mumbai','to_location':'Pune','vehicle_no':'MH12AB1234','vehicle_type':'32 FT OPEN','delivery_office_address':'Godamwale Delivery Hub\\nGate 3, Bhosari MIDC, Pune','consignor_name':'Dummy Consignor Pvt Ltd','consignor_address':'Plot 18, TTC Industrial Area, Navi Mumbai','consignee_name':'Dummy Consignee Industries','consignee_address':'Warehouse 4, Chakan Phase 2, Pune','consignor_gst_no':'27AAAAA0000A1Z5','consignee_gst_no':'27BBBBB0000B1Z6','invoice_no':'INV-42','gst_paid_by':'transporter','mode_of_packing':'Loose Cartons','value':'250000','remarks':'Handle with care','insurance_company':'ICICI Lombard','insurance_policy_no':'PL-9981','insurance_date':'14/03/2026','insurance_amount':'250000','insurance_risk':'Transit Risk','created_by':user,'last_modified_by':user,'is_deleted':False}); LRLineItem.objects.filter(lr=lr).delete(); LRLineItem.objects.create(lr=lr, packages='12', description='Cartons of garments', actual_weight='980 KG', charged_weight='1000 KG', amount='12500', order=1); print(lr.id)"
```

**Verification URLs**
- DOCX: `http://127.0.0.1:8000/operations/lr/<LR_ID>/download-docx/`
- PDF: `http://127.0.0.1:8000/operations/lr/<LR_ID>/download-pdf/`

**PDF conversion**
- Cloud Run / Linux: LibreOffice (`soffice`)
- Local Windows: LibreOffice first, then Microsoft Word / `docx2pdf` fallback

---

## Pre-Deployment Check
```bash
python pre_deploy_check.py
```

Verifies security config, migrations, database connection, static files.

---

## Testing
```bash
python manage.py test
python manage.py test operations  # specific app
```

---

## 📚 Documentation

Comprehensive documentation is available in the [`docs/`](docs/) directory:

- **[Quick Start Guide](docs/QUICKSTART.md)** - Get started quickly
- **[Security Fixes Report](docs/SECURITY_FIXES_APPLIED.md)** - Complete security audit results (282 fixes)
- **[Deployment Guide](docs/DEPLOYMENT_READY.md)** - Production deployment checklist
- **[Cloud Tasks Setup](docs/CLOUD_TASKS_DEPLOYMENT.md)** - Worker deployment guide
- **[Integration Setup Guides](docs/)** - Bigin, Gmail, TallySync, Google Ads, etc.

See the [Documentation Index](docs/README.md) for all available guides.

---

## 🔒 Security Status

✅ **Production Ready** - All security issues resolved

- **282/282 security issues fixed** (100% complete)
- All worker endpoints OIDC authenticated
- Input validation with Pydantic
- Financial data uses Decimal precision
- Transaction atomicity for all database operations
- No credentials in source code

See [SECURITY_FIXES_APPLIED.md](docs/SECURITY_FIXES_APPLIED.md) for details.

---

## License

Proprietary - Godamwale Warehousing Solutions
