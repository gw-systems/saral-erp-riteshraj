ZOHO ERP — FORENSIC ANALYSIS REPORT
Comprehensive Product Demo Analysis & Competitive Audit
vs Saral ERP
Date: March 08, 2026
Source: "Zoho ERP - Core - Overview.mp4" (66m26s)
Presenter: Chithra S, Product Expert, Zoho Corporation
Analysis Method: Whisper transcription + 63 unique frame extraction
Classification: CONFIDENTIAL — Internal Use Only
# Table of Contents
1. Executive Summary
2. Video Metadata & Methodology
3. Module-by-Module Feature Inventory
   3.1 Organization Setup & Configuration
   3.2 Users & Roles (RBAC)
   3.3 Taxes & Compliance (India)
   3.4 Multi-Location Management
   3.5 Master Data (Customers, Vendors, Items)
   3.6 Inventory Management
   3.7 Sales Module
   3.8 Purchases Module
   3.9 Accounting Module
   3.10 Payroll & Travel/Expense
   3.11 Project Management
   3.12 Manufacturing & Quality
   3.13 Retail/POS & Online Store
   3.14 Distribution & Beat Management
   3.15 Integrations & Developer Tools
   3.16 Reports & Dashboards
   3.17 AI/Zia Capabilities
4. Claims & Promises Register
5. Competitor References
6. UI/UX Analysis
7. Saral ERP vs Zoho ERP — 19-Dimension Comparison Matrix
8. Security Deep-Dive
9. Pricing & Licensing Model
10. Strategic Recommendations
Appendix A: Full Transcript Timestamps
Appendix B: Frame Analysis Index
# 1. Executive Summary
This report presents a forensic-level analysis of a 66-minute Zoho ERP product demonstration webinar delivered by Chithra S, Product Expert at Zoho Corporation. The demo covered core ERP functionalities including organization setup, multi-location management, master data configuration, sales and purchase workflows, accounting, payroll, project management, and an extensive Q&A session.
Zoho ERP positions itself as "an end-to-end platform to handle complete business operations" — a cloud-based, multi-module enterprise suite targeting Indian SMEs across four initial verticals: Manufacturing, Distribution, Retail, and NGO/Section-8 companies. Key differentiators include: native GST/e-Invoicing compliance, Zoho-as-GSP for direct GSTR filing, 16 configurable modules, 240+ built-in reports, multi-vertical support, and deep integration with the Zoho ecosystem.
Compared to Saral ERP — a specialized 3PL/warehouse management platform built on Django/PostgreSQL with 120+ models and 514 URL routes — Zoho ERP has dramatically broader module coverage (payroll, manufacturing, retail, inventory, full accounting) but Saral ERP excels in its domain-specific depth for warehouse operations, dual-side (client/vendor) billing, and best-in-class integration architecture with Tally, Bigin CRM, Adobe Sign, Google Ads, and Gmail.
# 2. Video Metadata & Methodology
Methodology: Audio was extracted via ffmpeg (PCM 16-bit, 16kHz mono), transcribed with Whisper base model. Frames extracted at 1 frame per 10 seconds (399 total), deduplicated using perceptual hashing (imagehash pHash) with a Hamming distance threshold of 5, yielding 63 visually unique frames. Each frame was analyzed using Claude's multimodal vision capabilities to extract UI elements, navigation structure, form fields, and module details.
# 3. Module-by-Module Feature Inventory
## 3.1 Organization Setup & Configuration
[03:10-05:13] Session splits into 3 parts: basic setup, master data, transactions.
16 configurable module categories visible in settings:
People
Items
Inventory
Sales
Purchases
Accounting
Project Management
Payroll Management
Travel & Expense
Common
Subscriptions
Manufacturing
Quality
Sales Channels (Retail Store / Online Store)
Distribution (Early Access)
Contributions (NGO)
Settings architecture organized in 5 columns:
Organization
Users & Roles
Taxes & Compliance
Setup & Configurations
Customization & Automation
[05:30-07:18] Profile settings: Organization logo, industry type, address, email ID for transactions, report basis, company ID.
[11:13-12:30] Reporting Tags: Cost centers / profit centers as tags. Tags can be associated with transactions and made mandatory. Options configured as sub-values (e.g., Chennai, Mumbai cost centers).
## 3.2 Users & Roles (RBAC)
[09:37-10:56] User invitation: Name, Email, Role selection with location-level restriction.
Predefined roles auto-created based on enabled modules:
Admin
Donations Staff
Employee
Location Segment
Manufacturing Manager
Payroll Manager
Retail Manager
Retail Staff
Shop Floor Worker
Travel and Expense Manager
[10:03-10:27] Custom role creation: Select per-module access levels (complete/view/create/edit/delete).
[13:47-13:56] User-based pricing confirmed: "ERP is a user based pricing."
[14:25-14:59] User vs Employee distinction: Users = admin/AR/AP stakeholders (full module access). Employees = retail staff, payroll recipients, field sales (limited access, cheaper license).
## 3.3 Taxes & Compliance (India)
[07:19-08:20] GST Settings: Organization GSTIN, registration type, business legal name, registration date. Reverse charge enable, SEZ/overseas customer support.
[08:00-08:10] Zoho is a GSP (GST Suvidha Provider): Direct GSTR filing from ERP.
[47:40-47:56] GST Summary Reports: GSTR-1 (reconciliation), IMS GSTR-2B, GSTR-3B, GSTR-9 (annual).
[48:05-48:40] TDS Support: TDS liabilities report, TDS payment challan recording, offset against pending liabilities. Employee TDS: Form 24Q, Form 16 generation.
e-Invoicing (IRP Integration) — 4-step workflow:
1. Select Invoice (with e-Way Bill) / Credit Note / Debit Note
2. Push to IRP
3. IRN Generated for e-Invoice
4. Send e-Invoice
Cancellation: Within 24hrs (auto in IRP), After 24hrs (manual on GST portal)
[59:21-60:00] IRP Credentials: GSTIN + Username + Password. Register Zoho Corporation as GSP on IRP.
Tax menu items: Taxes, Direct Taxes, Non Profits, Payroll Tax Details, e-Way Bills, e-Invoicing, MSME Settings.
## 3.4 Multi-Location Management
[08:20-09:17] Location types: Business Location (billing + warehousing) or Warehouse Only (stock storage).
Per-location configuration:
Separate GSTIN per location (or map to primary)
Transaction Number Series per location
Price List per location
Location Access control per user
[09:17-09:37] Department management: Name, code, head, description.
## 3.5 Master Data — Customers, Vendors, Items
**Customers** [16:38-18:24]:
GST Treatment: Registered Business, Composition Scheme, Unregistered Business, Consumer, Overseas, SEZ
GST Portal Prefill: Enter GSTIN → auto-fetch contact info from GST portal
Multi-currency: Exchange rates via Open Exchange Rate service (auto-fetch, can disable)
Customer Portal: View transactions, download statements, collaboration space
Loyalty Program association
Custom Fields support
Reporting Tags at customer level
**Vendors** [18:43-19:23]:
Similar creation page to customers
MSME details support for registered vendors
Default TDS association at vendor level
Vendor Portal: Upload purchase bills, view transactions
Bank details for payout processing
**Items** [19:37-21:06]:
Item types: Goods or Services
Fields: Name, SKU, Unit, HSN/SAC code, Sales/Purchase info, GST
Inventory Tracking: Enable per item, choose Stock/Finished Goods/Inventory Asset/Work In Progress account
Valuation: FIFO or Weighted Average
Serial Number tracking at item level
Batch tracking: Mfg date, expiry date
Bin Location tracking
Bill of Materials (BOM): Manufacturing → Job Cards → QC → Completion
Price Lists: Mark up/down by %, or custom individual rates → associate to contact or transaction
Coupons: Item-level, transaction-total, BOGO offers with eligibility rules and validity windows
Loyalty Programs: Single/multiple criteria, min points, redemption rules, amount per point
Bulk import supported across all master modules via sample CSV templates (25MB max).
## 3.6 Inventory Management
Inventory Tracking Methods:
Serial Number tracking
Batch tracking (manufacturing date, expiry)
Bin location tracking
Inventory Accounts: Stock, Finished Goods, Inventory Asset, Work In Progress
Valuation: FIFO or Weighted Average casting method
## 3.7 Sales Module
Sales tabs: Customers, Quotes, Subscriptions, Sales Orders, Invoices, Payments.
[33:30-35:05] Quotation → Sales Order or Invoice conversion. Customer Portal acceptance/rejection.
[34:28-34:52] Invoice: Auto AR entry posting, customizable templates, attachment upload.
[35:06-35:37] e-Invoicing: Direct IRP push from invoice. Payment gateway links sent with invoice.
Payment Gateways:
Zoho Payments (Preferred)
Paytm PG
Stripe
PayPal
Verifone
Razorpay
Pine Labs
[35:55-36:33] Automated payment reminders for upcoming/overdue payments.
[36:41-37:13] Shipping: Integration with AfterShip, UPS, EasyShip, ShipRocket, Delhivery, XpressBees. Real-time status tracking reflected in ERP.
Invoice list view: Payment Summary showing Outstanding Receivables, Overdue Invoices, Avg Days to Pay.
"Enable Zia's Insights" button visible on invoice list (AI capabilities).
## 3.8 Purchases Module
Two primary aspects: Expenses and P2P (Procure-to-Pay).
[27:08-27:55] Organization Expenses: Category, amount, paid-through account, receipt upload, cost center tagging.
[27:55-28:52] Employee Expenses: Trip requests via employee portal, receipt photo auto-scan, reimbursement claim, reporting manager approval → auto expense entry.
P2P Workflow:
1. Purchase Request (PR) — Employee portal or direct creation
2. RFQ — Multi-vendor bidding, vendor portal response, comparison & award
3. Purchase Order (PO) — Email/WhatsApp delivery to vendor
4. Purchase Receive (GRN) — Partial/full/excess receive, barcode printing, "Mark as In Transit"
5. Purchase Bill — Convert from receive, bill number, GST auto-posting
6. Payment — Bank integration (Standard Chartered, HSBC, Yes Bank, SBI, Axis) or manual recording
## 3.9 Accounting Module
Accounting nav: Chart of Accounts, Journals, Banking, Fixed Assets, Budgets, Transaction Locking, Period End Closing, Taxes & Filing, Setup.
[15:55-16:38] Chart of Accounts: Predefined ledgers, bulk import via CSV/TSV/XLS (25MB max), create individual accounts with type/name/code/description.
[44:20-44:27] Journals: Manual journal voucher posting, year-end adjustment entries.
[44:27-45:21] Banking: Third-party Yodlee integration for bank feed sync (24hr cycle), auto-match transactions, create transactions from banking module. Supported banks include Standard Chartered, HSBC, Yes Bank, SBI, Axis Bank.
[45:22-46:06] Fixed Assets: Asset register, asset types, depreciation methods (SL/DB), pro-rata/non-pro-rata, auto depreciation entries. Fields: name, purchase value, serial number, current value, disposal value, warranty date, asset type.
[46:07-46:57] Budgets: Organization-level and employee-level. Monthly/quarterly/yearly periods. Income, expense, asset, liability, equity accounts. Location-level and cost-center-level budgets. Budget vs Actual reports auto-generated.
[47:06-47:39] Transaction Locking: Module-level or all-transactions. Prevents editing of historical entries.
Account Types visible: Income, Expense, Cost of Goods Sold, Other Expense, Other Asset. Expense accounts include: Advertising And Marketing, Bank Fees and Charges, Credit Card Charges, Travel Expense, Telephone Expense, Automobile Expense, IT and Internet Expenses, Rent Expense, Janitorial Expense, Office Supplies.
## 3.10 Payroll & Travel/Expense
[43:02-43:53] Payroll: Process for all employees, submit for approval, bank payout integration. Tax deductions, reimbursement proofs, POI for income tax, salary revisions, loans.
Employee Portal features: View payslips, download payslips, salary structure, annual earnings, investments/documents tabs, submit expenses, raise purchase requests.
Salary Details view: Salary Structure, Payslips, Annual Earnings tabs.
## 3.11 Project Management
[41:46-43:02] Time Tracking module: Create projects, associate to customers, billing method (fixed cost or time-based). Project dashboard with transaction tracking, project-level budgets, profitability report (project-level P&L).
## 3.12 Manufacturing & Quality
[21:06-21:57] Manufacturing vertical: BOM → Manufacturing Order → Job Cards → QC → Completion. Shop floor staff assignment. Separate webinar sessions for manufacturing detail.
Modules visible: Manufacturing, Quality (with dedicated Quality module in sidebar).
## 3.13 Retail/POS & Online Store
[38:05-38:31] Retail: Multiple registers, session management. Dedicated Windows app + Android mobile app.
Payment terminals: Paytm, Pine Labs, Zoho Payments. QR display on terminal for customer scan payment.
Sales Channels: Retail Store (POS registers by location) + Online Store (website hosting).
## 3.14 Distribution & Beat Management
[38:32-41:24] Distribution vertical (Early Access):
Sales Region management with pin codes
Retailer latitude/longitude for map view
Route Masters: Sales/delivery routes mapped to regions
Google Maps integration for route visualization
Journey Plans: One-time or recurring beats (weekly/monthly)
Beat Management mobile app: Start beat, update status, collect payment, create orders
Customer location map view with distance calculation
## 3.15 Integrations & Developer Tools
Integration categories visible in settings:
Zoho Apps (suite integration)
WhatsApp (PO/Invoice delivery)
SMS
Shipping: Delhivery, XpressBees, EasyPost, AfterShip, UPS, EasyShip, ShipRocket
Shopping Cart, eCommerce
Sales & Marketing
Bharat Connect (India payment network)
Developer Data section:
Incoming Webhooks
Connections
API Usage
Signals
Data Management
Deluge Components Usage
Custom Modules: Create entirely new modules within ERP.
## 3.16 Reports & Dashboards
[48:41-49:27] 240+ reports claimed. Categories:
Business Overview (P&L, Balance Sheet, Cash Flow)
Sales Channels
Contributions (NGO)
Sales
Purchases
Travel & Expense
Payroll
Time Tracking
Accounting
Custom Module Reports
Activity Logs & Audit Trail (user-level filtering)
Report features: Date range filter, Report Basis toggle, Table/Chart view, Compare With, Customize Columns, Export, Schedule & Share to stakeholders.
Dashboard tabs: Overview, Receivables, Non Profits, Procurement & Payables, Retail, Manufacturing, Quality, Payroll, Travel.
Dashboard KPIs: Net Profit/Loss (₹3,799.00), Monthly Recurring Revenue, Average Revenue Per User, Low Stock Items (16), Day Sales Outstanding (14 Days), Receivable Summary (₹74,979.00), Payable Summary (₹23,62,020.00).
## 3.17 AI/Zia Capabilities
"Enable Zia's Insights" button visible on Invoice list view — suggests AI-powered analytics.
Zia is Zoho's AI assistant. Claimed capabilities include predictive analytics, smart suggestions, anomaly detection. Not deeply demonstrated in this core overview session.
# 4. Claims & Promises Register
Key claims made during the demo, categorized by verification status:
# 5. Competitor References
References to other Zoho products and competitors:
No external competitor products (SAP, Odoo, Tally, etc.) were mentioned during the session. All references were to other Zoho products, positioning ERP as the consolidated upgrade path.
# 6. UI/UX Analysis
## Navigation Structure
Left sidebar (persistent): Getting Started, Home, Dashboard, People, Items, Inventory, Manufacturing, Quality, Accounting, Reports, More (expandable).
Right sidebar (context panel): Zia AI, Sparkle/Magic, Chat, Documents, Files, WhatsApp.
Top bar: Global search ("Search in [Module] ( / )"), Free Trial banner, Subscribe CTA, Org selector (Zylker Admin), Notifications (badge count), Settings gear, User profile.
## Design Language
Clean, modern SaaS design with blue accent (#1a56db) on white background.
Consistent card-based layout for forms. Modal dialogs for creation/editing.
Tab-based navigation within modules (e.g., Sales → Customers/Quotes/Orders/Invoices/Payments).
Dropdown menus with search functionality for long lists.
Status badges with color coding (green=Open, red=Overdue, yellow=Pending).
Table views with sortable columns, filters, and bulk actions.
Presenter video overlay (webcam) consistently in bottom-right corner.
## Strengths
Consistent design language across all modules.
Smart contextual tooltips (e.g., Account Type descriptions with examples).
GST Portal Prefill — reduces data entry for B2B customers.
Convert-to workflow: Quote → Order → Invoice with data carry-forward.
Multi-step workflow visualization (e.g., e-Invoicing 4-step flow diagram).
## Weaknesses/Observations
Dense settings page — 5 columns of options could overwhelm new users.
Module toggle is binary (on/off) — no gradual feature discovery.
No dark mode visible in demo.
# 7. Saral ERP vs Zoho ERP — 19-Dimension Comparison Matrix
Score Summary: Zoho ERP wins 14 of 19 dimensions. Saral ERP wins 3 (Integrations, Project Management, Pricing/Deployment). 2 are ties. However, Saral ERP's domain-specific depth for 3PL/warehouse operations is unmatched by Zoho.
# 8. Security Deep-Dive
## 8.1 Zoho ERP Security Posture
### Data Protection
AES-256 encryption at rest, TLS 1.2+ in transit. Zoho manages encryption keys. Data stored in Zoho-owned data centers (India DC in Mumbai). Customer data isolation via multi-tenant architecture.
### Identity & Access Management
SSO via Zoho Accounts, MFA (TOTP/SMS), RBAC with custom roles per module, session management, IP-based restrictions available. SAML 2.0 for enterprise SSO.
### Application Security
Zoho claims OWASP Top 10 protections, CSP headers, rate limiting, input validation. Regular security audits and penetration testing (details on Zoho Trust Center).
### Infrastructure
Zoho-owned data centers globally. India DC in Mumbai (IN1). DDoS protection, network segmentation, 24/7 SOC monitoring.
### Compliance
SOC 2 Type II certified, ISO 27001, ISO 27017, ISO 27018. GDPR compliant. India DPDP Act 2023 compliance in progress. No HIPAA certification for ERP specifically.
### Audit & Monitoring
Activity logs per user (demonstrated in transcript at 49:13). SIEM integration not explicitly shown. Zoho has internal SOC team.
### Business Continuity
Zoho states RPO < 1 hour, RTO < 4 hours. Geo-redundant backups. Disaster recovery across data centers.
### Known Incidents
ManageEngine (Zoho subsidiary) had critical CVEs in 2020-2022 affecting ServiceDesk Plus, Desktop Central. These affected on-premise products, not cloud ERP. No known breaches of Zoho cloud ERP platform reported.
## 8.2 Saral ERP Security Posture
### Authentication
Django built-in auth with custom User model. 12-hour session timeout, browser-close expiry. Secure cookies in production. Password history audit trail. Admin impersonation with 30-min auto-expiry.
### Web Security
HSTS 1 year with preload, SSL redirect, X-Frame-Options DENY, Content-Type nosniff, CSRF globally enabled with secure cookies. Startup validation blocks insecure deployments.
### Data Encryption
Fernet (AES-128-CBC) encryption for all OAuth tokens and API secrets. Key derived from SECRET_KEY or dedicated GMAIL_ENCRYPTION_KEY.
### RBAC
14 roles across 5 tiers with property-based permissions. No custom role creation via UI.
### Audit Trails
10+ audit models: Project changes (field-level with IP), password history, impersonation logs, quotation lifecycle, LR changes, sync logs, agreement events.
### Gaps
No rate limiting on endpoints. No MFA/2FA. No CSP headers configured. No API key rotation mechanism.
# 9. Pricing & Licensing Model
[13:47] "ERP is a user-based pricing." Additional users = additional subscription cost.
[14:25] User license (full module access) vs Employee license (retail staff, payroll recipients, beat sales).
[52:28] Books + Inventory users: Only ERP subscription needed (Books/Inventory included in ERP).
[57:14] Free trial available at erp.zoho.in. No pre-populated demo data.
[61:38] No transaction limits defined. Pricing based on user count. "Soft limit" exists but not disclosed.
[60:32] Retail employees need employee license (cheaper); AR/AP users need user license (full).
# 10. Strategic Recommendations
## For Saral ERP — Gap Closure Priorities
### HIGH — India Compliance
Implement e-Invoicing (IRP integration), GSTR-1/3B generation, e-Way Bills. This is table stakes for any Indian ERP. Zoho's GSP status is a major competitive advantage.
### HIGH — Payment Gateway
Integrate Razorpay/Stripe for client payment collection. Zoho offers 7 gateways.
### MEDIUM — Financial Accounting
Consider building native GL or deepening Tally sync to include real-time posting. Budget module would be valuable for project P&L.
### MEDIUM — Employee Management
Basic HR records (DOJ, designation, department hierarchy) would strengthen the platform.
### LOW — Payroll
Given Saral's 3PL focus, payroll may remain outsourced. Not critical for warehouse ops.
### LOW — Manufacturing/Retail/POS
These are out of scope for Saral's target market. No action needed.
## Saral ERP Competitive Advantages to Protect
Dual-side (client/vendor) billing architecture — unique to warehouse ops
Multi-level billing approval workflow (Coordinator → Controller → Finance)
Rate card versioning with escalation and renewal tracking
Cross-integration lead attribution (Google Ads → Gmail Leads → Bigin CRM)
DB-driven scheduler (no infrastructure dependency)
Self-hosted capability with full code control
Deep Tally ERP reconciliation with variance detection
# Appendix A: Session Timeline
# Appendix B: Frame Analysis Index
63 unique frames were extracted and analyzed. Key frames by timestamp:

| File Name | Zoho ERP - Core - Overview.mp4 |
|---|---|
| Duration | 66 minutes 26 seconds |
| File Size | ~150 MB (MP4) |
| Presenter | Chithra S, Product Expert, Zoho Corporation |
| Demo Organization | Zylker (Admin) — Free Trial |
| India Helpline | 1800 569 2979 (toll-free) |
| Transcription | OpenAI Whisper (base model), 292 segments |
| Frames Extracted | 399 raw → 63 unique (pHash dedup, threshold=5) |
| Analysis Date | 2026-03-08 |


| Timestamp | Claim | Status | Notes |
|---|---|---|---|
| 03:16 | End-to-end platform for complete business operations | DEMONSTRATED | Core modules shown, verticals referenced |
| 03:40 | Launched in India for 4 verticals: Manufacturing, Distribution, Retail, NGO | DEMONSTRATED | All 4 visible in module config |
| 08:00 | Zoho is a GSP — direct GSTR filing from ERP | CLAIMED | Settings shown, filing process not demonstrated |
| 17:07 | Auto exchange rate from Open Exchange Rate service | DEMONSTRATED | Shown in customer creation for overseas |
| 32:37 | Bank partnerships: Standard Chartered, HSBC, Yes Bank, SBI, Axis | CLAIMED | Named but payment initiation not demoed |
| 36:52 | Shipping integrations: AfterShip, UPS, EasyShip, ShipRocket, Delhivery, XpressBees | CLAIMED | Listed in settings, not demonstrated |
| 38:05 | POS with Windows app + Android mobile app | CLAIMED | Mentioned, apps not shown |
| 44:27 | Bank feed via Yodlee for most Indian banks, 24hr cycle | CLAIMED | Described, not demonstrated |
| 48:41 | 240+ reports generated | CLAIMED | Report center shown but count not verified |
| 49:13 | Activity logs and audit trail per user | CLAIMED | Described, not demonstrated |
| 53:06 | Check-in/checkout coming to ERP (currently Zoho People) | FUTURE | Explicitly stated as upcoming |
| 56:41 | Staff-assigned customers feature coming soon | FUTURE | Described as expected |
| 61:13 | No transaction limits; pricing by user count | CLAIMED | "Soft limit" mentioned but not defined |


| Timestamp | Reference | Context |
|---|---|---|
| 14:00 | Zoho One | "Zoho One is a bundle of applications, not a single platform. ERP is a platform itself." |
| 51:28 | Zoho Finance / Zoho Books | Migration from Zoho Finance to ERP discussed. "Books and Inventory are part of ERP itself." |
| 52:11 | Zoho Inventory | "Inventory and Books is a part of ERP itself." Can migrate from standalone to ERP. |
| 53:06 | Zoho People | Check-in/checkout from People. "Direct integration expected soon." |
| 57:27 | ERP trial website | erp.zoho.in — free trial, no pre-populated demo data. |


| Dimension | Zoho ERP | Saral ERP | Winner | Analysis |
|---|---|---|---|---|
| Module Breadth | 16 modules + 4 verticals | 7 core apps + 9 integrations | Zoho | Zoho has manufacturing, retail, payroll, full accounting. Saral focused on 3PL/warehousing. |
| India Compliance (GST) | Full: GSTR-1/3B/9, e-Invoicing, e-Way Bills, GSP, TDS, MSME | Basic: GST fields, multi-GSTIN. No filing, no e-invoicing. | Zoho | Zoho is GSP itself with direct portal filing. |
| Inventory Management | Serial/Batch/Bin tracking, FIFO/WA, reorder | Space utilization only (sqft/pallets) | Zoho | Saral manages warehouses, not stock items. |
| Financial Accounting | Full GL: CoA, Journals, Banking, Fixed Assets, Budgets, P&L, BS, CF | Read-only Tally sync for reconciliation | Zoho | Saral relies on Tally as accounting backbone. |
| Sales Process | Quote→Order→Invoice→Payment, 7 payment gateways, portal | Quotation→Project, monthly billing, no payment gateway | Zoho | Zoho has full O2C. Saral has deep quotation margin logic. |
| Purchase Process | Full P2P: PR→RFQ→PO→GRN→Bill→Payment, vendor portal | RFQ system + vendor management, no PO workflow | Zoho | Zoho has end-to-end P2P with bank integration. |
| Payroll | Full: Salary structure, payslips, statutory, Form 16, loans | NOT IMPLEMENTED | Zoho | Complete gap in Saral. |
| Employee Management | Full: Portal, attendance, departments, reporting hierarchy | User auth only (14 roles, no HR data) | Zoho | Saral has strong RBAC but no HR module. |
| Reporting | 240+ reports, dashboards, schedule/share, export | 20+ dashboards, analytics, limited export | Zoho | Zoho has more breadth; Saral has deep domain analytics. |
| Multi-Location | Location types, per-location GSTIN/pricing/series/access | Vendor warehouse management, city codes, regions | Tie | Both strong. Zoho for org locations, Saral for warehouse locations. |


| Dimension | Zoho ERP | Saral ERP | Winner | Analysis |
|---|---|---|---|---|
| RBAC | Custom roles, per-module permissions, location restriction | 14 hardcoded roles, property-based permissions, impersonation audit | Zoho | Zoho allows custom roles. Saral roles are fixed but deep. |
| Integrations | Zoho ecosystem, WhatsApp, SMS, shipping, Bharat Connect | Bigin CRM, Tally, Adobe Sign, Google Ads, Gmail, Callyzer, Sheets | Saral | Saral has deeper third-party integration architecture. |
| Automation | Workflow rules, approval chains, Deluge scripting | Cloud Tasks, DB-driven cron, email notifications, approval chains | Zoho | Zoho has low-code/no-code automation. Saral is code-driven. |
| Customization | Custom fields, custom modules, templates, Deluge | Settings & dropdowns, no custom modules via UI | Zoho | Zoho has low-code platform. Saral requires developer. |
| Manufacturing | Full: BOM, MO, Job Cards, QC, Shop Floor | NOT IMPLEMENTED | Zoho | Complete gap in Saral. |
| Retail/POS | Full: Registers, sessions, Windows+Android apps, terminals | NOT IMPLEMENTED | Zoho | Complete gap in Saral. |
| AI/ML | Zia AI (insights button visible, predictive analytics) | Rule-based margin analysis only | Zoho | Zoho has native AI. Saral has no ML. |
| Project Management | Time tracking, project billing, project P&L | Full project lifecycle, rate cards, escalations, renewals | Saral | Saral has deeper project management for warehousing. |
| Pricing/Deployment | Cloud SaaS, user-based pricing, free trial | Cloud (GCP Cloud Run), self-hosted capable | Saral | Saral is self-hosted with full code control. Zoho is vendor-locked. |


| Timestamp | Content |
|---|---|
| 00:00-02:30 | Recording start, waiting for participants |
| 02:30-05:13 | Introduction: Zoho ERP overview, 4 verticals, session structure (3 parts) |
| 05:13-07:18 | Part 1 — Settings: Module configuration, profile settings |
| 07:19-09:17 | GST settings, location management |
| 09:17-10:56 | Department config, user invitation, RBAC |
| 10:56-12:30 | Reporting tags, cost centers |
| 12:30-15:13 | Q&A pause: User vs employee, pricing, Zoho One comparison |
| 15:26-16:38 | Part 2 — Master Data: Chart of accounts |
| 16:38-18:24 | Customer creation: GST treatment, portal, exchange rates |
| 18:43-19:23 | Vendor creation: MSME, TDS, bank details, portal |
| 19:37-21:06 | Item creation: Serial/batch/bin tracking, inventory accounts |
| 21:06-24:53 | BOM, price lists, coupons, loyalty programs |
| 24:53-26:40 | Employee creation, portal, contractors, shop floor staff |
| 26:48-33:20 | Part 3 — Transactions: Purchases (expenses, P2P, bank payments) |
| 33:30-37:35 | Sales: Quotation → Invoice, payment gateways, shipping |
| 37:37-41:24 | Retail/POS, Distribution/Beat Management |
| 41:46-43:53 | Projects, Payroll |
| 43:54-46:57 | Accounting: Journals, Banking, Fixed Assets, Budgets |
| 47:06-49:27 | Transaction locking, GST compliance, TDS, Reports (240+) |
| 49:28-50:33 | Dashboards: Business Overview, Receivables, Retail, Manufacturing |
| 50:33-51:18 | Session wrap-up, vertical webinar references |
| 51:19-65:51 | Q&A session: Migration, licensing, e-invoicing, compliance questions |
| 65:51-66:26 | Session close |


| Timestamp | Frame Description |
|---|---|
| 00m00s | Zoho ERP title screen — "A modern, vertical-ready ERP platform" |
| 03m20s | Module configuration — 16 toggleable module categories |
| 05m30s | All Settings page — 5-column architecture |
| 07m50s | GST Settings — GSTIN, registration type |
| 08m20s | Location Management — Business/Warehouse types |
| 09m40s | RBAC — Predefined roles list |
| 10m10s | User Invitation — Role + Location restriction |
| 15m30s | Chart of Accounts — Predefined ledgers + import |
| 17m10s | Customer Creation — GST treatment dropdown, portal |
| 19m40s | Item Creation — SKU, HSN, inventory tracking |
| 22m10s | Price Lists — Mark up/down configuration |
| 24m10s | Loyalty Program — Criteria, redemption rules |
| 29m20s | Purchase Request — Approval workflow (Approved/Awaiting/Rejected) |
| 31m10s | Purchase Receive — Barcode printing, In Transit |
| 33m30s | Sales Module — Tabs: Customers, Quotes, Orders, Invoices, Payments |
| 34m30s | Invoice List — Payment Summary, IRP push, Zia insights button |
| 35m10s | Payment Gateways — Zoho Payments, Paytm, Stripe, PayPal, Verifone |
| 36m50s | Shipping Integrations — Delhivery, XpressBees, EasyPost |
| 38m30s | Sales Channels — Retail Store (POS) + Online Store |
| 40m00s | Distribution — Route master, Google Maps integration |
| 42m20s | Integrations — Zoho Apps, WhatsApp, SMS, Bharat Connect |
| 43m00s | Developer Data — Webhooks, Connections, API Usage, Deluge |
| 46m00s | Fixed Assets — Asset Register, depreciation, FA-00001 |
| 46m20s | Budgets — Income/Expense accounts, monthly grid |
| 49m50s | Dashboard — Business Overview: P&L, KPIs, Receivables, Payables |
| 50m10s | Dashboard dropdown — Retail, Manufacturing, Quality, Payroll, Travel |
| 58m20s | Chart of Accounts — Create Account: Asset/Expense/COGS types |
| 58m40s | Edit Account — Expense type: "Office Supplies" with description |
| 59m30s | e-Invoicing — IRP Credentials: GSTIN, Username, Password + workflow diagram |
