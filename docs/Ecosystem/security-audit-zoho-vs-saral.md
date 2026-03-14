SECURITY AUDIT REPORT
Zoho ERP vs Saral ERP
Classification: CONFIDENTIAL
Date: March 08, 2026
Scope: Security posture comparison based on demo analysis + codebase audit
Sources: Zoho Trust Center (training knowledge, cutoff May 2025) + Saral ERP source code
# Executive Summary
This security audit compares the security postures of Zoho ERP (cloud SaaS) and Saral ERP (self-hosted on GCP Cloud Run). Zoho ERP benefits from enterprise-grade infrastructure, third-party certifications (SOC 2, ISO 27001), and dedicated security teams. Saral ERP implements strong web security defaults via Django's security framework and custom audit trails, but lacks several enterprise security features (MFA, rate limiting, CSP, API key rotation).
## Risk Summary
# A. Data Protection
## Zoho ERP
Encryption at Rest: AES-256 for all customer data. Keys managed by Zoho (not customer-managed).
Encryption in Transit: TLS 1.2+ enforced. HSTS with long max-age.
Data Residency: India DC in Mumbai (IN1). Customer can choose data center region.
Data Isolation: Multi-tenant with logical isolation. Each org has unique org_id.
Backup: Automated, geo-redundant. Customer data recoverable per SLA.
## Saral ERP
Encryption at Rest: Fernet (AES-128-CBC + HMAC-SHA256) for OAuth tokens and API secrets. Database encryption delegated to GCP Cloud SQL (Google-managed encryption).
Encryption in Transit: HSTS 1 year with preload + subdomains. SECURE_SSL_REDIRECT=True. Proxy SSL header configured for Cloud Run.
Data Residency: GCP region (configurable). Cloud SQL + GCS in same region.
Data Isolation: Single-tenant per deployment. Complete data isolation by design.
Backup: GCP Cloud SQL automated backups. No application-level backup strategy detected.
## Gap Analysis
Saral uses AES-128 (Fernet) vs Zoho's AES-256. Consider upgrading to AES-256-GCM.
Saral's single-tenant model provides inherently stronger data isolation.
Neither platform offers customer-managed encryption keys (CMEK) by default.
# B. Identity & Access Management
## Zoho ERP
SSO: Zoho Accounts, SAML 2.0 for enterprise federation.
MFA: TOTP (authenticator apps), SMS, push notification via Zoho OneAuth.
RBAC: Custom roles with per-module granularity (view/create/edit/delete). Location restriction.
Session: Configurable timeout. IP whitelisting available for orgs.
User Types: Users (full module access, ₹ per user/month) vs Employees (limited, cheaper).
## Saral ERP
Auth: Django session-based authentication. Custom User model with 14 hardcoded roles.
MFA: NOT IMPLEMENTED. Critical security gap.
RBAC: 14 roles across 5 tiers (Admin → Executive → Management → Execution → External). Property-based permissions (is_admin, can_see_margins, can_approve_billing).
Session: 12-hour timeout (SESSION_COOKIE_AGE=43200). Browser-close expiry enabled. Secure, HttpOnly cookies in production.
Impersonation: Admin-only with 30-minute auto-expiry. Full audit logging (admin_user, target_user, started_at, ended_at, ip_address, reason).
Password: PasswordHistory model tracks all changes (hash, timestamp, IP, changed_by).
## Recommendations for Saral
CRITICAL: Implement TOTP-based MFA using django-otp or django-two-factor-auth.
MEDIUM: Add IP whitelisting for admin accounts.
LOW: Consider SAML 2.0 / OIDC for enterprise customers.
# C. Application Security
## Zoho ERP
OWASP Top 10: Claimed protection across all categories. Regular penetration testing.
CSP: Content Security Policy headers implemented.
Rate Limiting: API rate limits enforced per organization.
Input Validation: Server-side validation with Zoho's proprietary framework.
## Saral ERP
CSRF: CsrfViewMiddleware enabled globally. CSRF_COOKIE_SECURE=True in production.
XSS: Django template auto-escaping (default). No custom |safe usage detected in audit.
Clickjacking: X-Frame-Options: DENY.
Content-Type Sniffing: SECURE_CONTENT_TYPE_NOSNIFF=True.
CSP: NOT CONFIGURED. Missing Content-Security-Policy header.
Rate Limiting: NOT IMPLEMENTED. No django-ratelimit or similar.
File Upload: 10MB limit (DATA_UPLOAD_MAX_MEMORY_SIZE + FILE_UPLOAD_MAX_MEMORY_SIZE).
Startup Validation: Production deployment blocked if DEBUG=True, default SECRET_KEY, ALLOWED_HOSTS=["*"], or SSL misconfigured.
## Recommendations for Saral
CRITICAL: Add rate limiting (django-ratelimit) on all API endpoints and login.
HIGH: Implement CSP headers (django-csp package).
MEDIUM: Add file type validation for uploads (not just size).
# D. Infrastructure Security
## Zoho ERP
Data Centers: Zoho-owned and operated. India DC: Mumbai (IN1). Global: US, EU, AU, China.
DDoS Protection: Enterprise-grade DDoS mitigation.
Network: Segmented networks, firewalls, IDS/IPS.
SOC: 24/7 Security Operations Center.
## Saral ERP
Hosting: Google Cloud Run (serverless containers). Auto-scaling, managed infrastructure.
Database: Cloud SQL (managed PostgreSQL) with Unix socket connection in production.
Storage: Google Cloud Storage (saral-erp-media-prod bucket).
Task Queue: Google Cloud Tasks (no Redis/RabbitMQ dependency).
DDoS: GCP-managed DDoS protection (Cloud Armor available but not confirmed configured).
Secrets: Uses python-decouple (.env files). Google Secret Manager available but usage unclear.
## Recommendations for Saral
MEDIUM: Enable Cloud Armor WAF for DDoS protection on Cloud Run.
MEDIUM: Migrate from .env to Google Secret Manager for all secrets.
LOW: Consider multi-region Cloud SQL replica for disaster recovery.
# E. Compliance & Certifications
# F. Audit & Monitoring
## Zoho ERP
[49:13] "Activity logs and audit trail per user — what date, what time, what activity, which user."
User-level filtering of audit logs demonstrated in transcript.
SIEM integration: Zoho has internal SOC. Customer SIEM integration not demonstrated.
## Saral ERP
10+ dedicated audit models:
ProjectCodeChangeLog — Field-level project changes with IP address tracking
ProjectNameChangeLog — Client name changes with reason
PasswordHistory — Password changes (hash, timestamp, changed_by, IP)
ImpersonationLog — Admin impersonation sessions (start, end, IP, reason)
ErrorLog — Application errors with resolution tracking
QuotationAudit — 12 action types for quotation lifecycle with old/new JSON values
LRAuditLog — Lorry receipt changes with old/new JSON diffs
SyncLog — Unified integration sync audit (progress, record counts, API calls)
EscalationLog — Agreement escalation workflow actions
AgreementRenewalLog — Renewal tracking audit
AgreementEvent — Adobe Sign webhook events (idempotent)
Assessment: Saral ERP has STRONGER audit trail depth than what was demonstrated for Zoho ERP. The field-level change tracking with old/new JSON values and IP logging is enterprise-grade.
# G. Business Continuity
# H. Third-Party Risk
## Zoho ERP
Open Exchange Rate: Currency exchange rates (customer data exposed: none).
Yodlee: Bank feed aggregation (bank credentials flow through Yodlee).
Payment Gateways: 7+ gateways process financial transactions.
Shipping Partners: 6+ shipping aggregators receive order/address data.
Google Maps: Distribution beat management (location data).
Risk: Yodlee is the highest-risk third party due to bank credential handling.
## Saral ERP
Google Cloud Platform: Infrastructure provider (compute, storage, database).
Zoho Bigin: CRM data sync (customer PII).
Tally ERP: Accounting data sync (financial records).
Adobe Sign: E-signature (agreement documents).
Google Ads API: Marketing data (no PII).
Gmail API: Email content (highest PII risk).
Callyzer: Call records (phone numbers, durations).
Risk: Gmail API is the highest-risk integration due to full email content access.
# I. Known Incidents & Vulnerabilities
## Zoho Ecosystem
ManageEngine (Zoho subsidiary) critical CVEs 2020-2022:
CVE-2021-44077 — ServiceDesk Plus RCE (pre-auth)
CVE-2021-40539 — ADSelfService Plus auth bypass
CVE-2022-47966 — Multiple ManageEngine products RCE
All affected on-premise products, NOT cloud ERP.
No known breaches of Zoho cloud ERP platform as of May 2025.
Zoho Trust Center: https://www.zoho.com/trust.html
## Saral ERP
No external vulnerability reports (private codebase, single deployment).
Internal security measures are code-auditable (advantage of self-hosted).
Django security updates: Django 5.2.11 is current LTS (security patches applied).
# Overall Security Recommendations for Saral ERP
## CRITICAL (Implement Immediately)
1. MFA/2FA — Implement TOTP-based multi-factor authentication using django-otp or django-two-factor-auth. This is the single biggest security gap.
2. Rate Limiting — Add django-ratelimit to login endpoints, API endpoints, and public-facing URLs. Without this, brute-force attacks are unrestricted.
## HIGH (Implement Within 30 Days)
3. CSP Headers — Add django-csp with a strict Content-Security-Policy. Prevents XSS even if template escaping is bypassed.
4. Secret Management — Migrate from .env files to Google Secret Manager for all production secrets (SECRET_KEY, ENCRYPTION_KEY, OAuth credentials).
## MEDIUM (Implement Within 90 Days)
5. Cloud Armor WAF — Enable GCP Cloud Armor in front of Cloud Run for DDoS protection and WAF rules.
6. File Upload Validation — Add MIME type validation and virus scanning for uploaded files.
7. API Key Rotation — Implement automated rotation for third-party API keys (Bigin, Adobe Sign, etc.).
## LOW (Plan for Next Quarter)
8. Encryption Upgrade — Upgrade from Fernet (AES-128-CBC) to AES-256-GCM for token storage.
9. Multi-Region DR — Deploy Cloud SQL read replica in a second GCP region.
10. SOC 2 Preparation — If Saral ERP will be offered to external customers, begin SOC 2 Type II preparation.

| Risk Area | Zoho ERP | Saral ERP | Recommendation |
|---|---|---|---|
| Unauthorized Access | LOW — SSO, MFA, RBAC | MEDIUM — No MFA, session-only auth | Implement TOTP-based MFA in Saral |
| Data Breach | LOW — AES-256, Zoho DCs, SOC 2 | MEDIUM — Fernet encryption, GCP managed | Consider AES-256-GCM upgrade for token storage |
| API Abuse | LOW — Rate limiting, API keys | HIGH — No rate limiting detected | Add Django-ratelimit to all API endpoints |
| XSS/Injection | LOW — OWASP protections | LOW — Django auto-escaping, CSRF | Add CSP headers to Saral |
| Insider Threat | MEDIUM — Activity logs | LOW — 10+ audit models, impersonation logging | Saral has better audit depth |
| Supply Chain | MEDIUM — Zoho ecosystem dependency | LOW — Open source stack, GCP managed | Monitor Zoho subsidiary CVEs |
| Compliance | LOW — SOC 2, ISO, GDPR | MEDIUM — No certifications | Consider SOC 2 for Saral if customer-facing |
| Business Continuity | LOW — Geo-redundant, RPO<1hr | MEDIUM — Single GCP region assumed | Implement multi-region for Saral |


| Certification | Zoho ERP | Saral ERP |
|---|---|---|
| SOC 2 Type II | YES (Zoho Corp) | NO |
| ISO 27001 | YES | NO |
| ISO 27017 (Cloud Security) | YES | NO (inherits from GCP) |
| ISO 27018 (PII in Cloud) | YES | NO |
| GDPR | YES (compliant) | Partial (data export possible) |
| HIPAA | NOT for ERP specifically | NO |
| India DPDP Act 2023 | In Progress | Not assessed |
| PCI DSS | Via payment gateways | N/A (no payment processing) |


| Metric | Zoho ERP | Saral ERP |
|---|---|---|
| RPO (Recovery Point Objective) | <1 hour (claimed) | Cloud SQL PITR: minutes |
| RTO (Recovery Time Objective) | <4 hours (claimed) | Cloud Run: seconds (auto-scaling) |
| Backup Strategy | Geo-redundant, automated | Cloud SQL automated, single region |
| Disaster Recovery | Cross-DC failover | Manual (single GCP region assumed) |
| SLA | 99.9% uptime (standard) | GCP Cloud Run: 99.95% |
| Data Export | Available per module | Direct DB access (full export) |
