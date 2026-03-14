# Saral ERP - Quick Start Guide

## Local Development

### Using Docker Compose (Recommended)

```bash
# Start all services (Django, PostgreSQL, Redis, Celery)
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Access the application
open http://localhost:8080

# View logs
docker-compose logs -f web

# Stop all services
docker-compose down
```

### Without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Set up PostgreSQL and Redis locally
# Update .env file with local credentials

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver 8080

# In separate terminals, start Celery
celery -A minierp worker -l info
celery -A minierp beat -l info
```

## Cloud Run Deployment

### Prerequisites Checklist

- [ ] Google Cloud account with billing enabled
- [ ] `gcloud` CLI installed
- [ ] Docker installed
- [ ] Project ID ready

### Quick Deployment (3 Steps)

**Step 1: Set up infrastructure**

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"

# Enable APIs and create resources
gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com sql-component.googleapis.com redis.googleapis.com secretmanager.googleapis.com

# Create Cloud SQL instance
gcloud sql instances create saral-erp-db --database-version=POSTGRES_15 --tier=db-f1-micro --region=$REGION
gcloud sql databases create erp --instance=saral-erp-db
gcloud sql users create admin --instance=saral-erp-db --password=YOUR_PASSWORD

# Create Redis instance
gcloud redis instances create saral-erp-redis --size=1 --region=$REGION

# Store secrets
echo -n "your-secret-key" | gcloud secrets create django-secret-key --data-file=-
echo -n "YOUR_PASSWORD" | gcloud secrets create db-password --data-file=-
echo -n "redis://REDIS_IP:6379/0" | gcloud secrets create redis-url --data-file=-
```

**Step 2: Update configuration**

Edit `deploy.sh`:
- Set `PROJECT_ID`
- Set `CLOUD_SQL_CONNECTION_NAME` (from: `gcloud sql instances describe saral-erp-db --format='value(connectionName)'`)

**Step 3: Deploy**

```bash
chmod +x deploy.sh
./deploy.sh
```

### Post-Deployment

```bash
# Run migrations
gcloud run jobs execute saral-erp-migrate --region=$REGION --wait

# Create superuser
gcloud run jobs execute saral-erp-createsuperuser --region=$REGION --wait

# Get your app URL
gcloud run services describe saral-erp --region=$REGION --format='value(status.url)'
```

## Configuration Files Overview

| File | Purpose |
|------|---------|
| `Dockerfile` | Container image definition |
| `docker-compose.yml` | Local development environment |
| `requirements.txt` | Python dependencies |
| `deploy.sh` | Manual deployment script |
| `cloudbuild.yaml` | CI/CD configuration |
| `.env.example` | Environment variables template |
| `CLOUD_RUN_SETUP.md` | Detailed deployment guide |

## Environment Variables

Copy `.env.example` to `.env` and update with your values:

```bash
cp .env.example .env
nano .env  # Edit with your values
```

Key variables:
- `SECRET_KEY`: Django secret (generate with: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`)
- `DB_PASSWORD`: Database password
- `REDIS_URL`: Redis connection string
- `ZOHO_CLIENT_ID` / `ZOHO_CLIENT_SECRET`: Zoho Bigin API credentials

## Testing the Deployment

```bash
# Check service status
gcloud run services describe saral-erp --region=$REGION

# View logs
gcloud run services logs read saral-erp --region=$REGION --limit=50

# Test the endpoint
curl https://YOUR_SERVICE_URL/
```

## Common Commands

### Local (Docker Compose)

```bash
# Rebuild after code changes
docker-compose up -d --build

# Run Django commands
docker-compose exec web python manage.py <command>

# Database backup
docker-compose exec db pg_dump -U admin erp > backup.sql

# Database restore
docker-compose exec -T db psql -U admin erp < backup.sql
```

### Cloud Run

```bash
# Update service
gcloud run services update saral-erp --region=$REGION --set-env-vars KEY=VALUE

# Scale up/down
gcloud run services update saral-erp --region=$REGION --min-instances=1 --max-instances=10

# Delete service
gcloud run services delete saral-erp --region=$REGION
```

## Monitoring

### Local
- Django: http://localhost:8080/admin/
- Database: Use tools like pgAdmin or DBeaver (localhost:5432)
- Redis: Use RedisInsight (localhost:6379)

### Cloud Run
- Logs: Cloud Console → Cloud Run → Service → Logs
- Metrics: Cloud Console → Cloud Run → Service → Metrics
- Database: Cloud Console → SQL → saral-erp-db

## Support

For issues or questions:
1. Check `CLOUD_RUN_SETUP.md` for detailed troubleshooting
2. Review Cloud Run logs: `gcloud run services logs read saral-erp --region=$REGION`
3. Verify environment variables are set correctly

## Cost Estimates

Typical monthly costs for small deployment:
- Cloud Run: $0-10 (with generous free tier)
- Cloud SQL (db-f1-micro): ~$15
- Cloud Memorystore (1GB): ~$30
- **Total: ~$45-55/month**

For production, consider upgrading to:
- Cloud SQL: db-g1-small (~$50)
- Cloud Memorystore: 5GB (~$150)
