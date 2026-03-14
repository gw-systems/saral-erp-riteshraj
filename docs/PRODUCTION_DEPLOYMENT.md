# Production Deployment Guide

## Security Configuration

This application has production-grade security validation that runs at startup. The validation ensures critical security settings are properly configured before the application can run in production.

### Critical Settings (REQUIRED for Production)

These settings **MUST** be configured in production. The application will refuse to start without them:

1. **SECRET_KEY**
   - Must be at least 50 characters long
   - Must NOT be the default `django-insecure-dev-key`
   - Generate a secure key: `python -c "import secrets; print(secrets.token_urlsafe(50))"`

2. **DEBUG**
   - Must be set to `False` in production
   - Never run with `DEBUG=True` in production

3. **ALLOWED_HOSTS**
   - Must contain your production domain(s)
   - Example: `ALLOWED_HOSTS=your-app.run.app,yourdomain.com`

### Optional Integration Settings

These settings are **OPTIONAL**. If not provided, the related features will be disabled with a warning, but the application will still start:

- **GMAIL_LEADS_CLIENT_SECRET** - Gmail Leads integration
- **GOOGLE_ADS_CLIENT_SECRET** - Google Ads integration
- **GOOGLE_ADS_DEVELOPER_TOKEN** - Google Ads API access
- **ADOBE_CLIENT_SECRET** - Adobe Sign integration

### Environment Variables Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set required values:
   ```bash
   # CRITICAL - REQUIRED
   SECRET_KEY=your-secure-50-character-secret-key-here
   DEBUG=False
   ALLOWED_HOSTS=your-production-domain.com

   # OPTIONAL - Set if you want to enable these integrations
   GMAIL_LEADS_CLIENT_SECRET=your-secret-here
   GOOGLE_ADS_CLIENT_SECRET=your-secret-here
   GOOGLE_ADS_DEVELOPER_TOKEN=your-token-here
   ADOBE_CLIENT_SECRET=your-secret-here
   ```

### Validation Checks

The application performs these security checks at server startup:

1. **HTTPS Enforcement** - Redirect URIs must use HTTPS in production
2. **SECRET_KEY Strength** - Must be sufficiently long and unique
3. **Integration Credentials** - Warns if optional credentials are missing
4. **ALLOWED_HOSTS** - Must be configured in production
5. **CSRF Protection** - Warns if CSRF_TRUSTED_ORIGINS is empty

**Note:** Security validation is automatically skipped for management commands (`check`, `migrate`, `makemigrations`, etc.) to avoid blocking development workflows. Validation only runs when starting the actual application server (`runserver`, `gunicorn`, etc.).

### Django Security Checklist

Before deploying, run the deployment check:

```bash
python manage.py check --deploy
```

This will show additional security recommendations for production:

- **SECURE_HSTS_SECONDS** - Enable HTTP Strict Transport Security
- **SECURE_SSL_REDIRECT** - Force HTTPS redirects
- **SESSION_COOKIE_SECURE** - Secure session cookies
- **CSRF_COOKIE_SECURE** - Secure CSRF cookies

These are warnings (not errors) and should be configured based on your deployment infrastructure.

## Production Deployment Steps

1. **Environment Setup**
   ```bash
   # Set environment variables
   export DEBUG=False
   export SECRET_KEY="your-50-character-secret"
   export ALLOWED_HOSTS="your-domain.com"
   ```

2. **Run Security Validation**
   ```bash
   python manage.py check --deploy
   ```

3. **Database Migration**
   ```bash
   python manage.py migrate
   ```

4. **Collect Static Files**
   ```bash
   python manage.py collectstatic --noinput
   ```

5. **Start Application**
   ```bash
   gunicorn minierp.wsgi:application
   ```

## Troubleshooting

### Application Won't Start in Production

**Error:** "SECURITY CONFIGURATION ERRORS - STARTUP BLOCKED"

**Solution:** Check the error messages and ensure all critical settings are configured:
- Set SECRET_KEY (50+ characters)
- Set DEBUG=False
- Set ALLOWED_HOSTS with your domain

### Features Not Working

**Warning:** "WARNING: GMAIL_LEADS_CLIENT_SECRET is not set"

**Solution:** This is expected if you haven't configured that integration. The feature will be disabled but the application will run normally. To enable:
1. Get credentials from Google Cloud Console
2. Add to your .env file
3. Restart the application

### Security Warnings from `--deploy` Check

**Warning:** SECURE_HSTS_SECONDS, SECURE_SSL_REDIRECT, etc.

**Solution:** These are recommendations, not errors. Configure based on your infrastructure:
- If using a load balancer/proxy for SSL termination, some may not be needed
- Review Django security documentation for your specific setup

## Support

For issues or questions:
- Check logs for specific error messages
- Review `.env.example` for required variable formats
- Ensure all environment variables are properly set
