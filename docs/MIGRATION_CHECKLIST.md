# Celery to Cloud Tasks Migration - Final Checklist

## ✅ Backend Migration Complete

### Infrastructure
- [x] Created `integration_workers/` package with Cloud Tasks client
- [x] Created worker endpoints for all 6 apps
- [x] Removed all Celery tasks files
- [x] Removed Celery configuration files
- [x] Updated all views to use Cloud Tasks
- [x] Updated management commands
- [x] Removed Celery/Redis from requirements.txt
- [x] Added google-cloud-tasks to requirements.txt
- [x] Updated .env.example with Cloud Tasks variables
- [x] Updated settings.py with Cloud Tasks config

### Code Quality
- [x] Django system check passes with no errors
- [x] All imports are correct
- [x] No remaining Celery references
- [x] No remaining Redis references
- [x] Fixed all indentation errors
- [x] Created comprehensive documentation

## 📋 Next Steps for Deployment

### 1. Local Testing
- [ ] Set `USE_CLOUD_TASKS=false` in local .env
- [ ] Run `python manage.py runserver`
- [ ] Test manual sync triggers
- [ ] Verify worker endpoints respond correctly
- [ ] Check logs for errors

### 2. Staging Deployment
- [ ] Update staging environment variables
- [ ] Enable Cloud Tasks API in GCP
- [ ] Create Cloud Tasks queue
- [ ] Deploy code to Cloud Run staging
- [ ] Configure service account permissions
- [ ] Create Cloud Scheduler jobs
- [ ] Test all sync operations
- [ ] Monitor for 24-48 hours

### 3. Production Deployment
- [ ] Review and update production environment variables
- [ ] Create production Cloud Tasks queue
- [ ] Deploy code to Cloud Run production
- [ ] Configure production service account permissions
- [ ] Create production Cloud Scheduler jobs
- [ ] Verify all scheduled tasks run correctly
- [ ] Monitor for 24 hours

### 4. Cleanup (After Successful Deployment)
- [ ] Delete old Redis instance (if exists)
- [ ] Delete old Celery worker service (if exists)
- [ ] Remove Celery monitoring/alerting (if exists)
- [ ] Update team documentation
- [ ] Archive old Celery configuration backups

## 🔍 Verification Steps

### Local Development
```bash
# 1. Check for errors
python manage.py check

# 2. Run migrations (if any)
python manage.py migrate

# 3. Start development server
python manage.py runserver

# 4. Test worker endpoints
curl -X POST http://localhost:8000/integrations/google-ads/workers/sync-all-accounts/ \
  -H "Content-Type: application/json" \
  -d '{"sync_yesterday": true, "sync_current_month_search_terms": true}'
```

### Production Verification
```bash
# 1. Check Cloud Tasks queue
gcloud tasks queues describe default --location=us-central1

# 2. Check Cloud Scheduler jobs
gcloud scheduler jobs list --location=us-central1

# 3. View logs
gcloud run services logs read erp-service --region=us-central1 --limit=100

# 4. Trigger manual sync
gcloud scheduler jobs run bigin-incremental-sync --location=us-central1
```

## 📊 Success Metrics

### Performance
- [ ] Task creation latency < 100ms
- [ ] Sync completion time improved vs Celery
- [ ] No failed tasks due to infrastructure issues

### Cost
- [ ] Monthly bill reduced by ~$40-60
- [ ] No Redis costs
- [ ] Cloud Tasks within free tier

### Reliability
- [ ] All scheduled syncs running on time
- [ ] No missed sync jobs
- [ ] Automatic retry working correctly
- [ ] Error logging functioning properly

## 🆘 Rollback Plan (If Needed)

If critical issues occur in production:

1. **Immediate**: Set `USE_CLOUD_TASKS=false` in environment
2. **Deploy**: Redeploy previous version with Celery (from git history)
3. **Restore**: Start Redis instance if deleted
4. **Start**: Launch Celery worker service
5. **Verify**: Check all syncs are working
6. **Investigate**: Debug issues in staging before retry

## 📝 Documentation

Created documentation:
- [x] [CLOUD_TASKS_DEPLOYMENT.md](./CLOUD_TASKS_DEPLOYMENT.md) - Complete deployment guide
- [x] [MIGRATION_SUMMARY.md](./MIGRATION_SUMMARY.md) - Detailed migration documentation
- [x] [MIGRATION_CHECKLIST.md](./MIGRATION_CHECKLIST.md) - This checklist

## 🎯 Migration Status

**Backend Migration: ✅ COMPLETE**

- All code changes implemented
- All tests passing
- Documentation complete
- Ready for deployment testing

**Next Phase: Deployment & Testing**

Follow the deployment guide in [CLOUD_TASKS_DEPLOYMENT.md](./CLOUD_TASKS_DEPLOYMENT.md) for step-by-step instructions.

---

## Contact & Support

For issues during deployment:
1. Check [CLOUD_TASKS_DEPLOYMENT.md](./CLOUD_TASKS_DEPLOYMENT.md) troubleshooting section
2. Review Cloud Run logs
3. Check Cloud Tasks queue metrics
4. Contact DevOps team if issues persist

**Last Updated**: 2026-02-08
