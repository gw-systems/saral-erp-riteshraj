# Cloud Tasks Deployment Guide

This guide covers the deployment of the ERP system with Google Cloud Tasks for async task execution on Cloud Run.

## Overview

The ERP has been migrated from Celery + Redis to Google Cloud Tasks for production-grade async task execution. This provides:

- **No Redis needed** - Saves ~$60/month on Memorystore
- **Auto-scaling** - Tasks scale with Cloud Run
- **Reliable execution** - Automatic retries with exponential backoff
- **Long-running tasks** - Up to 30 minutes per task
- **Cost-effective** - ~$15-25/month for 500-600 syncs/day

## Architecture

```
User Request → Django View → Cloud Tasks API → Task Queue → Cloud Run Worker Endpoint → Sync Logic
                                                                ↓
                                                           Cloud SQL Database
```

## Prerequisites

1. Google Cloud Project with billing enabled
2. Cloud Run service deployed
3. Cloud SQL PostgreSQL instance
4. gcloud CLI installed and authenticated

## Step 1: Enable Required APIs

```bash
# Enable Cloud Tasks API
gcloud services enable cloudtasks.googleapis.com

# Enable Cloud Scheduler API (for periodic tasks)
gcloud services enable cloudscheduler.googleapis.com
```

## Step 2: Create Cloud Tasks Queue

```bash
# Set your project ID
export PROJECT_ID="your-project-id"
export REGION="us-central1"

# Create default queue
gcloud tasks queues create default \
    --location=$REGION \
    --max-dispatches-per-second=10 \
    --max-concurrent-dispatches=100 \
    --max-attempts=3 \
    --min-backoff=10s \
    --max-backoff=300s
```

## Step 3: Configure Service Account Permissions

```bash
# Get your Cloud Run service account
export SERVICE_ACCOUNT="your-service-account@$PROJECT_ID.iam.gserviceaccount.com"

# Grant Cloud Tasks permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/cloudtasks.enqueuer"

# Grant Cloud Run invoker permissions (for tasks to call worker endpoints)
gcloud run services add-iam-policy-binding erp-service \
    --region=$REGION \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/run.invoker"
```

## Step 4: Update Environment Variables

Add these to your Cloud Run service:

```bash
# Update .env or Secret Manager
USE_CLOUD_TASKS=true
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1
CLOUD_TASKS_QUEUE=default
CLOUD_TASKS_SERVICE_URL=https://your-service-url.run.app
GCP_SERVICE_ACCOUNT=your-service-account@your-project.iam.gserviceaccount.com
```

Update via gcloud:

```bash
gcloud run services update erp-service \
    --region=$REGION \
    --set-env-vars="USE_CLOUD_TASKS=true,GCP_PROJECT_ID=$PROJECT_ID,GCP_LOCATION=$REGION,CLOUD_TASKS_QUEUE=default,CLOUD_TASKS_SERVICE_URL=https://your-service-url.run.app,GCP_SERVICE_ACCOUNT=$SERVICE_ACCOUNT"
```

## Step 5: Deploy Updated Code

```bash
# Install new dependencies
pip install -r requirements.txt

# Deploy to Cloud Run
gcloud run deploy erp-service \
    --source . \
    --region=$REGION \
    --platform=managed \
    --allow-unauthenticated \
    --timeout=1800 \
    --memory=2Gi \
    --cpu=2
```

## Step 6: Create Cloud Scheduler Jobs (Periodic Tasks)

### Bigin Incremental Sync (Every 5 minutes)
```bash
gcloud scheduler jobs create http bigin-incremental-sync \
    --location=$REGION \
    --schedule="*/5 * * * *" \
    --uri="https://your-service-url.run.app/integrations/bigin/workers/sync-all-modules/" \
    --http-method=POST \
    --message-body='{"run_full": false, "triggered_by_user": "scheduler"}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --headers="Content-Type=application/json"
```

### Bigin Full Sync (Daily at 3 AM)
```bash
gcloud scheduler jobs create http bigin-full-sync \
    --location=$REGION \
    --schedule="0 3 * * *" \
    --time-zone="Asia/Kolkata" \
    --uri="https://your-service-url.run.app/integrations/bigin/workers/sync-all-modules/" \
    --http-method=POST \
    --message-body='{"run_full": true, "triggered_by_user": "scheduler"}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --headers="Content-Type=application/json"
```

### Bigin Token Refresh (Every hour)
```bash
gcloud scheduler jobs create http bigin-token-refresh \
    --location=$REGION \
    --schedule="0 * * * *" \
    --uri="https://your-service-url.run.app/integrations/bigin/workers/refresh-token/" \
    --http-method=POST \
    --message-body='{}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --headers="Content-Type=application/json"
```

### TallySync (Every 30 minutes)
```bash
gcloud scheduler jobs create http tallysync-sync \
    --location=$REGION \
    --schedule="*/30 * * * *" \
    --uri="https://your-service-url.run.app/integrations/tallysync/workers/sync-tally-data/" \
    --http-method=POST \
    --message-body='{"days": 7}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --headers="Content-Type=application/json"
```

### Gmail Leads Sync (Every 15 minutes)
```bash
gcloud scheduler jobs create http gmail-leads-sync \
    --location=$REGION \
    --schedule="*/15 * * * *" \
    --uri="https://your-service-url.run.app/integrations/gmail-leads/workers/sync-all-accounts/" \
    --http-method=POST \
    --message-body='{"force_full": false}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --headers="Content-Type=application/json"
```

### Gmail Sync (Every 15 minutes)
```bash
gcloud scheduler jobs create http gmail-sync \
    --location=$REGION \
    --schedule="*/15 * * * *" \
    --uri="https://your-service-url.run.app/gmail/workers/sync-all-accounts/" \
    --http-method=POST \
    --message-body='{"force_full": false}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --headers="Content-Type=application/json"
```

### Callyzer Daily Sync (Daily at 2 AM)
```bash
gcloud scheduler jobs create http callyzer-sync \
    --location=$REGION \
    --schedule="0 2 * * *" \
    --time-zone="Asia/Kolkata" \
    --uri="https://your-service-url.run.app/integrations/callyzer/workers/sync-all-accounts/" \
    --http-method=POST \
    --message-body='{"days_back": 150}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --headers="Content-Type=application/json"
```

### Google Ads Daily Sync (Daily at 2 AM)
```bash
gcloud scheduler jobs create http google-ads-sync \
    --location=$REGION \
    --schedule="0 2 * * *" \
    --time-zone="Asia/Kolkata" \
    --uri="https://your-service-url.run.app/integrations/google-ads/workers/sync-all-accounts/" \
    --http-method=POST \
    --message-body='{"sync_yesterday": true, "sync_current_month_search_terms": true}' \
    --oidc-service-account-email=$SERVICE_ACCOUNT \
    --headers="Content-Type=application/json"
```

## Step 7: Verify Deployment

### Check Cloud Tasks Queue
```bash
gcloud tasks queues describe default --location=$REGION
```

### Check Cloud Scheduler Jobs
```bash
gcloud scheduler jobs list --location=$REGION
```

### Trigger a Test Sync (Manual)
```bash
# Test Bigin sync
curl -X POST https://your-service-url.run.app/integrations/bigin/api/trigger-sync/ \
    -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    -H "Content-Type: application/json"
```

### Monitor Task Execution
```bash
# View Cloud Run logs
gcloud run services logs read erp-service \
    --region=$REGION \
    --limit=100

# View Cloud Tasks logs
gcloud logging read "resource.type=cloud_tasks_queue" \
    --limit=50 \
    --format=json
```

## Step 8: Cleanup Old Celery/Redis Resources

If you had Celery + Redis deployed:

```bash
# Delete Redis instance (Memorystore)
gcloud redis instances delete redis-instance --region=$REGION

# Remove Celery worker Cloud Run service (if separate)
gcloud run services delete celery-worker --region=$REGION
```

## Troubleshooting

### Tasks not executing
1. Check service account permissions
2. Verify CLOUD_TASKS_SERVICE_URL is correct
3. Check Cloud Run logs for errors

### "Permission denied" errors
```bash
# Re-grant permissions
gcloud run services add-iam-policy-binding erp-service \
    --region=$REGION \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/run.invoker"
```

### Scheduler jobs failing
```bash
# Check scheduler job status
gcloud scheduler jobs describe bigin-incremental-sync --location=$REGION

# Run job manually for testing
gcloud scheduler jobs run bigin-incremental-sync --location=$REGION
```

## Cost Estimation

Based on 500-600 syncs/day:

- Cloud Tasks: ~$0 (free tier: 1M operations/month)
- Cloud Scheduler: ~$3/month (8 jobs)
- Cloud Run execution: ~$10-20/month
- **Total: $15-25/month**

Compare to Celery + Memorystore Redis: $60-85/month

## Migration Checklist

- [x] Create Cloud Tasks queue
- [x] Configure service account permissions
- [x] Update environment variables
- [x] Deploy updated code
- [x] Create Cloud Scheduler jobs
- [ ] Verify all syncs working
- [ ] Monitor for 24 hours
- [ ] Delete old Celery/Redis resources

## Support

For issues or questions:
1. Check Cloud Run logs
2. Check Cloud Tasks queue metrics
3. Review this guide
4. Contact DevOps team

## References

- [Cloud Tasks Documentation](https://cloud.google.com/tasks/docs)
- [Cloud Scheduler Documentation](https://cloud.google.com/scheduler/docs)
- [Cloud Run Documentation](https://cloud.google.com/run/docs)
