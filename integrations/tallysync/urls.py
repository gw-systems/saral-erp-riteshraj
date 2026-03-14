from django.urls import path
from . import views, views_api, workers

app_name = 'tallysync'

urlpatterns = [

    path('test-library/', views.test_library, name='test_library'),

    # Settings (Admin/Director only)
    # path('settings/', views.settings, name='settings'),  # DEPRECATED: Use integrations hub instead

    # Dashboard views
    path('reconciliation/', views.reconciliation_dashboard, name='reconciliation_dashboard'),
    path('reconciliation/detail/', views.reconciliation_detail, name='reconciliation_detail'),
    path('project-profitability/', views.project_profitability_dashboard, name='project_profitability_dashboard'),
    path('project-profitability/<str:project_id>/', views.project_detail, name='project_detail'),
    path('client-profitability/', views.client_profitability_dashboard, name='client_profitability_dashboard'),
    path('vendor-profitability/', views.vendor_profitability_dashboard, name='vendor_profitability_dashboard'),
    path('cost-centre-profitability/', views.cost_centre_profitability_dashboard, name='cost_centre_profitability_dashboard'),
    path('cash-liquidity/', views.cash_liquidity_dashboard, name='cash_liquidity_dashboard'),
    path('aging-report/', views.aging_report_dashboard, name='aging_report_dashboard'),
    path('gst-compliance/', views.gst_compliance_dashboard, name='gst_compliance_dashboard'),
    path('operations/', views.operations_dashboard, name='operations_dashboard'),
    
    # API endpoints - Financial Analytics
    path('api/executive-summary/', views_api.api_executive_summary, name='api_executive_summary'),
    path('api/revenue-breakdown/', views_api.api_revenue_breakdown, name='api_revenue_breakdown'),
    path('api/company-summary/', views_api.api_company_summary, name='api_company_summary'),
    path('api/monthly-trend/', views_api.api_monthly_trend, name='api_monthly_trend'),
    path('api/chart-monthly-trend/', views_api.api_chart_data_monthly_trend, name='api_chart_monthly_trend'),

    
    # API endpoints - Project Analytics
    path('api/project-profitability/', views_api.api_project_profitability, name='api_project_profitability'),
    path('api/client-profitability/', views_api.api_client_profitability, name='api_client_profitability'),
    path('api/vendor-profitability/', views_api.api_vendor_profitability, name='api_vendor_profitability'),
    path('api/cost-centre-profitability/', views_api.api_cost_centre_profitability, name='api_cost_centre_profitability'),
    path('api/project/<str:project_id>/', views_api.api_project_detail, name='api_project_detail'),
    path('api/project/<str:project_id>/lifecycle/', views_api.api_project_lifecycle, name='api_project_lifecycle'),
    path('api/top-projects/', views_api.api_top_projects, name='api_top_projects'),
    path('api/voucher/<int:voucher_id>/', views_api.api_voucher_detail, name='api_voucher_detail'),
    
    # API endpoints - Cash Flow
    path('api/cash-flow-summary/', views_api.api_cash_flow_summary, name='api_cash_flow_summary'),
    path('api/cash-flow-trend/', views_api.api_cash_flow_trend, name='api_cash_flow_trend'),
    path('api/receivables/', views_api.api_receivables, name='api_receivables'),
    path('api/payables/', views_api.api_payables, name='api_payables'),
    
    # API endpoints - Companies
    path('api/companies/', views_api.api_companies, name='api_companies'),
    path('api/discover-companies/', views_api.api_discover_companies, name='api_discover_companies'),

    # API endpoints - Aging Report
    path('api/receivables-aging/', views_api.api_receivables_aging, name='api_receivables_aging'),
    path('api/payables-aging/', views_api.api_payables_aging, name='api_payables_aging'),
    path('api/aging-summary/', views_api.api_aging_summary, name='api_aging_summary'),
    path('api/party-aging-detail/', views_api.api_party_aging_detail, name='api_party_aging_detail'),
    path('api/project-aging-download/', views_api.api_project_aging_download, name='api_project_aging_download'),
    path('api/party-aging-download/', views_api.api_party_aging_download, name='api_party_aging_download'),

    # API endpoints - GST
    path('api/gst-summary/', views_api.api_gst_summary, name='api_gst_summary'),
    path('api/gst-monthly-return/', views_api.api_gst_monthly_return, name='api_gst_monthly_return'),
    path('api/gst-by-state/', views_api.api_gst_by_state, name='api_gst_by_state'),
    
    # API endpoints - Salesperson
    path('api/salesperson-performance/', views_api.api_salesperson_performance, name='api_salesperson_performance'),
    path('api/salesperson/<str:salesperson_name>/', views_api.api_salesperson_detail, name='api_salesperson_detail'),
    path('api/salesperson-financial-summary/', views_api.api_salesperson_financial_summary, name='api_salesperson_financial_summary'),
    path('sales-financial-detail/', views.sales_financial_detail, name='sales_financial_detail'),
    path('salesperson/<str:salesperson_name>/', views.salesperson_detail_dashboard, name='salesperson_detail'),
    path('vendor/<str:vendor_name>/', views.vendor_detail_dashboard, name='vendor_detail'),


    
    # API endpoints - Ledger Analytics
    path('api/tds-summary/', views_api.api_tds_summary, name='api_tds_summary'),
    path('api/bank-transactions/', views_api.api_bank_transactions, name='api_bank_transactions'),
    path('api/vendor-expenses/', views_api.api_vendor_expenses, name='api_vendor_expenses'),
    path('api/vendor/<str:vendor_name>/', views_api.api_vendor_detail, name='api_vendor_detail'),
    path('api/customer-revenue/', views_api.api_customer_revenue, name='api_customer_revenue'),

    # API endpoints - Enhanced Features
    path('api/detailed-gst-breakdown/', views_api.api_detailed_gst_breakdown, name='api_detailed_gst_breakdown'),
    path('api/payment-mode-analysis/', views_api.api_payment_mode_analysis, name='api_payment_mode_analysis'),
    path('api/ledger-groups-summary/', views_api.api_ledger_groups_summary, name='api_ledger_groups_summary'),
    path('api/income-statement-groups/', views_api.api_income_statement_groups, name='api_income_statement_groups'),
    path('api/group-hierarchy/', views_api.api_group_hierarchy, name='api_group_hierarchy'),

    # Sync triggers (user-facing)
    path('api/trigger-sync/', views_api.api_trigger_sync, name='api_trigger_sync'),
    path('api/trigger-full-sync/', views_api.api_trigger_full_sync, name='api_trigger_full_sync'),
    path('api/sync-logs/', views_api.api_sync_logs, name='api_sync_logs'),
    path('api/sync-logs/<int:batch_id>/', views_api.api_sync_log_detail, name='api_sync_log_detail'),

    # Admin utilities
    path('test-connection/', views_api.tally_connection_test, name='tally_connection_test'),
    path('api/network-diagnostic/', views_api.api_network_diagnostic, name='api_network_diagnostic'),
    path('sync-progress/', views.sync_progress, name='sync_progress'),
    path('stop-sync/', views.stop_sync, name='stop_sync'),
    path('force-stop-sync/', views.force_stop_sync, name='force_stop_sync'),

    # Cloud Tasks worker endpoints
    path('workers/sync-tally-data/', workers.sync_tally_data_worker, name='worker_sync_tally_data'),
    path('workers/full-reconciliation/', workers.full_reconciliation_worker, name='worker_full_reconciliation'),
]