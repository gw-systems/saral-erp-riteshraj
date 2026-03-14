# Saral ERP - Google Cloud Run Deployment Guide

This guide walks you through deploying the Saral ERP Django application to Google Cloud Run.

## Prerequisites

1. Google Cloud Platform account
2. `gcloud` CLI installed and configured
3. Docker installed locally (for testing)
4. A Google Cloud Project created

## Architecture Overview

The application will use:
- **Cloud Run**: For hosting the Django application
- **Cloud SQL (PostgreSQL)**: For the database
- **Cloud Memorystore (Redis)**: For Celery task queue
- **Secret Manager**: For storing sensitive credentials
- **Cloud Build**: For CI/CD (optional)

## Step-by-Step Deployment

### 1. Set Up Google Cloud Project

```bash
# Set your project ID
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"

# Set the project
gcloud config set project $PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable sql-component.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable redis.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### 2. Create Cloud SQL Instance

```bash
# Create PostgreSQL instance
gcloud sql instances create saral-erp-db \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=$REGION

# Create database
gcloud sql databases create erp --instance=saral-erp-db

# Create database user
gcloud sql users create admin \
    --instance=saral-erp-db \
    --password=YOUR_SECURE_PASSWORD

# Get the connection name
gcloud sql instances describe saral-erp-db --format='value(connectionName)'
# Save this value - you'll need it for deployment
```

### 3. Create Redis Instance (Cloud Memorystore)

```bash
# Create Redis instance for Celery
gcloud redis instances create saral-erp-redis \
    --size=1 \
    --region=$REGION \
    --redis-version=redis_7_0

# Get the Redis host
gcloud redis instances describe saral-erp-redis --region=$REGION --format='value(host)'

# Construct Redis URL: redis://[HOST]:6379/0
```

### 4. Store Secrets in Secret Manager

```bash
# Create secrets
echo -n "your-django-secret-key" | gcloud secrets create django-secret-key --data-file=-
echo -n "your-database-password" | gcloud secrets create db-password --data-file=-
echo -n "redis://YOUR_REDIS_HOST:6379/0" | gcloud secrets create redis-url --data-file=-
echo -n "your-zoho-client-id" | gcloud secrets create zoho-client-id --data-file=-
echo -n "your-zoho-client-secret" | gcloud secrets create zoho-client-secret --data-file=-

# Grant Cloud Run access to secrets
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member=serviceAccount:$PROJECT_ID@appspot.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor
```

### 5. Update Configuration Files

Update the following files with your project-specific values:

**deploy.sh:**
- `PROJECT_ID`
- `REGION`
- `CLOUD_SQL_CONNECTION_NAME`

**cloudbuild.yaml:**
- `_CLOUD_SQL_CONNECTION_NAME` (in substitutions)

### 6. Build and Deploy

#### Option A: Manual Deployment (using deploy.sh)

```bash
# Make the script executable
chmod +x deploy.sh

# Edit deploy.sh with your configuration
nano deploy.sh

# Run deployment
./deploy.sh
```

#### Option B: Using Cloud Build

```bash
# Submit build to Cloud Build
gcloud builds submit --config cloudbuild.yaml \
    --substitutions=_CLOUD_SQL_CONNECTION_NAME="your-project:region:instance-name"
```

### 7. Run Database Migrations

After deployment, you need to run Django migrations:

```bash
# Get a Cloud Run service URL
export SERVICE_URL=$(gcloud run services describe saral-erp --region=$REGION --format='value(status.url)')

# Run migrations (you'll need to create a Cloud Run Job for this)
# First, create a migration job
gcloud run jobs create saral-erp-migrate \
    --image=gcr.io/$PROJECT_ID/saral-erp \
    --region=$REGION \
    --add-cloudsql-instances=your-project:region:instance-name \
    --set-env-vars="USE_CLOUD_SQL=true,CLOUD_SQL_CONNECTION_NAME=your-project:region:instance-name,DB_NAME=erp,DB_USER=admin" \
    --set-secrets="DB_PASSWORD=db-password:latest" \
    --command=python \
    --args="manage.py,migrate"

# Execute the migration job
gcloud run jobs execute saral-erp-migrate --region=$REGION --wait
```

### 8. Create Django Superuser

```bash
# Create a superuser job
gcloud run jobs create saral-erp-createsuperuser \
    --image=gcr.io/$PROJECT_ID/saral-erp \
    --region=$REGION \
    --add-cloudsql-instances=your-project:region:instance-name \
    --set-env-vars="USE_CLOUD_SQL=true,CLOUD_SQL_CONNECTION_NAME=your-project:region:instance-name,DB_NAME=erp,DB_USER=admin,DJANGO_SUPERUSER_USERNAME=admin,DJANGO_SUPERUSER_EMAIL=admin@example.com,DJANGO_SUPERUSER_PASSWORD=your-admin-password" \
    --set-secrets="DB_PASSWORD=db-password:latest" \
    --command=python \
    --args="manage.py,createsuperuser,--noinput"

# Execute the superuser job
gcloud run jobs execute saral-erp-createsuperuser --region=$REGION --wait
```

### 9. Update CSRF Trusted Origins

```bash
# Get your service URL
export SERVICE_URL=$(gcloud run services describe saral-erp --region=$REGION --format='value(status.url)')

# Update the service with CSRF_TRUSTED_ORIGINS
gcloud run services update saral-erp \
    --region=$REGION \
    --set-env-vars="CSRF_TRUSTED_ORIGINS=$SERVICE_URL"
```

### 10. Deploy Celery Workers (Optional)

For background tasks (Zoho Bigin sync), you'll need to deploy Celery workers:

```bash
# Create Celery worker service
gcloud run jobs create saral-erp-celery-worker \
    --image=gcr.io/$PROJECT_ID/saral-erp \
    --region=$REGION \
    --add-cloudsql-instances=your-project:region:instance-name \
    --set-env-vars="USE_CLOUD_SQL=true,CLOUD_SQL_CONNECTION_NAME=your-project:region:instance-name,DB_NAME=erp,DB_USER=admin" \
    --set-secrets="DB_PASSWORD=db-password:latest,REDIS_URL=redis-url:latest" \
    --command=celery \
    --args="-A,minierp,worker,-l,info"

# For Celery Beat (scheduler)
gcloud run jobs create saral-erp-celery-beat \
    --image=gcr.io/$PROJECT_ID/saral-erp \
    --region=$REGION \
    --set-secrets="REDIS_URL=redis-url:latest" \
    --command=celery \
    --args="-A,minierp,beat,-l,info"
```

Note: For production, consider using Cloud Tasks or Cloud Scheduler instead of Celery Beat for scheduled tasks.

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | Random string |
| `DEBUG` | Debug mode | `false` |
| `ALLOWED_HOSTS` | Allowed hostnames | `your-app.run.app` |
| `USE_CLOUD_SQL` | Use Cloud SQL | `true` |
| `CLOUD_SQL_CONNECTION_NAME` | Cloud SQL connection | `project:region:instance` |
| `DB_NAME` | Database name | `erp` |
| `DB_USER` | Database user | `admin` |
| `DB_PASSWORD` | Database password | Stored in Secret Manager |
| `REDIS_URL` | Redis URL | `redis://host:6379/0` |
| `ZOHO_CLIENT_ID` | Zoho API client ID | From Zoho console |
| `ZOHO_CLIENT_SECRET` | Zoho API secret | From Zoho console |
| `CSRF_TRUSTED_ORIGINS` | CSRF trusted origins | `https://your-app.run.app` |

## Testing Locally with Docker

```bash
# Build the Docker image
docker build -t saral-erp .

# Run locally
docker run -p 8080:8080 \
    -e DEBUG=true \
    -e SECRET_KEY=test-key \
    -e DB_HOST=localhost \
    -e DB_NAME=erp \
    -e DB_USER=admin \
    -e DB_PASSWORD=password \
    saral-erp
```

## Monitoring and Logging

```bash
# View logs
gcloud run services logs read saral-erp --region=$REGION --limit=50

# View metrics in Cloud Console
gcloud run services describe saral-erp --region=$REGION
```

## Cost Optimization Tips

1. **Use minimum instances wisely**: Set `--min-instances=0` for development, `--min-instances=1` for production
2. **Right-size your Cloud SQL instance**: Start with `db-f1-micro` and scale up as needed
3. **Enable Cloud SQL automatic storage increase**: Prevents over-provisioning
4. **Use Redis for caching**: Reduces database load
5. **Set up Cloud CDN**: For static file serving (if using Cloud Storage)

## Troubleshooting

### Common Issues

1. **502 Bad Gateway**
   - Check Cloud Run logs: `gcloud run services logs read saral-erp --region=$REGION`
   - Verify Cloud SQL connection name is correct
   - Ensure secrets are accessible

2. **Database connection errors**
   - Verify Cloud SQL instance is running
   - Check database credentials in Secret Manager
   - Ensure Cloud Run has access to Cloud SQL

3. **Static files not loading**
   - Run `collectstatic` during build (already in Dockerfile)
   - Verify Whitenoise is configured correctly

## Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud SQL Documentation](https://cloud.google.com/sql/docs)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Django on Cloud Run Guide](https://cloud.google.com/python/django/run)

## Security Recommendations

1. Never commit `.env` files or secrets to version control
2. Use Secret Manager for all sensitive data
3. Enable VPC connector for Cloud Run to Cloud SQL communication
4. Set up Cloud Armor for DDoS protection
5. Enable Cloud Run authentication for admin endpoints
6. Use Cloud IAM for fine-grained access control
7. Regularly update dependencies in requirements.txt
8. Enable Cloud SQL automated backups

## Continuous Deployment with Cloud Build

To set up automatic deployments on git push:

```bash
# Connect your repository
gcloud alpha builds triggers create cloud-source-repositories \
    --repo=saral-erp \
    --branch-pattern="^main$" \
    --build-config=cloudbuild.yaml
```

Now every push to the `main` branch will trigger an automatic deployment.
