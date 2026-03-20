from django.urls import path
from django.urls import include
from . import views
from . import views_adhoc
from . import views_monthly_billing
from . import views_lr
from . import views_porter_invoice



app_name = 'operations'

urlpatterns = [
    # ============================================================================
    # DAILY ENTRY ROUTES
    # ============================================================================
    path('daily-entry/', views.daily_entry_list, name='daily_entry_list'),
    path('daily-entry/single/', views.daily_entry_single, name='daily_entry_single'),
    path('daily-entry/bulk/', views.daily_entry_bulk, name='daily_entry_bulk'),
    path('daily-entry/<int:entry_id>/edit/', views.daily_entry_edit, name='daily_entry_edit'),
    path('daily-entry/bulk-edit/', views.daily_entry_bulk_edit, name='daily_entry_bulk_edit'),
    path('daily-entry/history/<str:project_id>/', views.daily_entry_history, name='daily_entry_history'),
    path('daily-entry/all-history/', views.daily_entry_all_history, name='daily_entry_all_history'), 

    
    # ============================================================================
    # MIS TRACKING ROUTES
    # ============================================================================
    path('mis/', views.mis_dashboard, name='mis_dashboard'),
    path('mis/<str:project_id>/mark-sent/', views.mis_mark_sent, name='mis_mark_sent'),
    path('mis/history/<str:project_id>/', views.mis_history, name='mis_history'),
    path('mis/all-history/', views.mis_all_history, name='mis_all_history'),


    
    # ============================================================================
    # DISPUTE ROUTES
    # ============================================================================
    path('disputes/', views.dispute_list, name='dispute_list'),
    path('disputes/analysis/', views.dispute_analysis, name='dispute_analysis'),
    path('disputes/create/', views.dispute_create, name='dispute_create'),
    path('disputes/<int:pk>/', views.dispute_detail, name='dispute_detail'),
    path('disputes/<int:pk>/edit/', views.dispute_edit, name='dispute_edit'),
    path('disputes/<int:dispute_id>/comment/', views.dispute_add_comment, name='dispute_add_comment'),
    path('disputes/<int:pk>/status/', views.dispute_update_status, name='dispute_update_status'),
    path('disputes/<int:pk>/priority/', views.dispute_update_priority, name='dispute_update_priority'),
    path('disputes/<int:pk>/assign/', views.dispute_assign, name='dispute_assign'),

    
    # ============================================================================
    # HOLIDAY ROUTES
    # ============================================================================
    path('holidays/', views.holiday_list, name='holiday_list'),
    path('holidays/create/', views.holiday_create, name='holiday_create'),
    path('holidays/<int:holiday_id>/edit/', views.holiday_edit, name='holiday_edit'),
    path('holidays/<int:holiday_id>/delete/', views.holiday_delete, name='holiday_delete'),

    # ============================================================================
    # Coordinator Performance
    # ============================================================================
    path('coordinator-performance/', views.coordinator_list_view, name='coordinator_list'),
    path('coordinator/<int:coordinator_id>/detail/', views.coordinator_detail_view, name='coordinator_detail'),
    path('pending-entries/', views.pending_entries_view, name='pending_entries_detail'),


    # Calendar moved to activity_logs app at /activity/

    # API Endpoints
    path('api/get-previous-day-data/', views.get_previous_day_data, name='get_previous_day_data'),
    path('api/daily-entry/update-inline/', views.daily_entry_update_inline, name='daily_entry_update_inline'),


    # ============================================================================
    # ADHOC BILLING
    # ============================================================================
    path('adhoc-billing/', views_adhoc.adhoc_billing_list, name='adhoc_billing_list'),
    path('adhoc-billing/create/', views_adhoc.adhoc_billing_create, name='adhoc_billing_create'),
    path('adhoc-billing/<int:entry_id>/', views_adhoc.adhoc_billing_detail, name='adhoc_billing_detail'),
    path('adhoc-billing/<int:entry_id>/edit/', views_adhoc.adhoc_billing_edit, name='adhoc_billing_edit'),
    path('adhoc-billing/<int:entry_id>/delete/', views_adhoc.adhoc_billing_delete, name='adhoc_billing_delete'),
    path('adhoc-billing/<int:entry_id>/mark-billed/', views_adhoc.adhoc_billing_mark_billed, name='adhoc_billing_mark_billed'),
    path('adhoc-billing/<int:entry_id>/update-status/', views_adhoc.adhoc_update_status, name='adhoc_update_status'),



    # ============================================================================
    # MONTHLY BILLING
    # ============================================================================
    # Dashboard
    path('monthly-billing/', views_monthly_billing.billing_dashboard, name='monthly_billing_dashboard'),
    
    # CRUD Operations
    path('monthly-billing/create/<str:project_id>/', views_monthly_billing.billing_create, name='monthly_billing_create'),
    path('monthly-billing/<int:billing_id>/', views_monthly_billing.billing_detail, name='monthly_billing_detail'),
    path('monthly-billing/<int:billing_id>/edit/', views_monthly_billing.billing_edit, name='monthly_billing_edit'),
    path('monthly-billing/<int:billing_id>/delete/', views_monthly_billing.billing_delete, name='monthly_billing_delete'),
    path('monthly-billing/<int:billing_id>/recall/', views_monthly_billing.billing_recall, name='monthly_billing_recall'),

    # Document Operations
    path('monthly-billing/<int:billing_id>/document/<str:field_name>/preview/', views_monthly_billing.monthly_billing_document_preview, name='monthly_billing_document_preview'),
    path('monthly-billing/<int:billing_id>/document/<str:field_name>/download/', views_monthly_billing.monthly_billing_document_download, name='monthly_billing_document_download'),

    # Workflow Actions
    path('monthly-billing/<int:billing_id>/submit/', views_monthly_billing.billing_submit, name='monthly_billing_submit'),
    path('monthly-billing/<int:billing_id>/controller-review/', views_monthly_billing.controller_review, name='monthly_billing_controller_review'),
    path('monthly-billing/<int:billing_id>/finance-review/', views_monthly_billing.finance_review, name='monthly_billing_finance_review'),


    # ============================================================================
    # LORRY RECEIPT (LR / CONSIGNMENT NOTE)
    # ============================================================================
    path('lr/', views_lr.lr_list, name='lr_list'),
    path('lr/create/', views_lr.lr_create, name='lr_create'),
    path('lr/<int:lr_id>/', views_lr.lr_detail, name='lr_detail'),
    path('lr/<int:lr_id>/edit/', views_lr.lr_edit, name='lr_edit'),
    path('lr/<int:lr_id>/delete/', views_lr.lr_delete, name='lr_delete'),
    path('lr/<int:lr_id>/download-docx/', views_lr.lr_download_docx, name='lr_download_docx'),
    path('lr/<int:lr_id>/download-pdf/', views_lr.lr_download_pdf, name='lr_download_pdf'),
    path('lr/<int:lr_id>/download-image/', views_lr.lr_download_image, name='lr_download_image'),


    # ============================================================================
    # PORTER INVOICE EDITOR
    # ============================================================================
    path('porter-invoices/', views_porter_invoice.porter_invoice_dashboard, name='porter_invoice_dashboard'),
    path('porter-invoices/batch/', views_porter_invoice.porter_invoice_batch, name='porter_invoice_batch'),
    path('porter-invoices/single/', views_porter_invoice.porter_invoice_single, name='porter_invoice_single'),
    path('porter-invoices/<int:session_id>/', views_porter_invoice.porter_invoice_detail, name='porter_invoice_detail'),
    path('porter-invoices/<int:session_id>/download-zip/', views_porter_invoice.porter_invoice_download_zip, name='porter_invoice_download_zip'),
    path('porter-invoices/file/<int:file_id>/download/', views_porter_invoice.porter_invoice_download_file, name='porter_invoice_download_file'),
    path('porter-invoices/api/extract/', views_porter_invoice.porter_invoice_extract_api, name='porter_invoice_extract_api'),
    path('porter-invoices/api/edit/', views_porter_invoice.porter_invoice_edit_api, name='porter_invoice_edit_api'),
    path('porter-invoices/api/edit-upload/', views_porter_invoice.porter_invoice_edit_upload_api, name='porter_invoice_edit_upload_api'),
    path('porter-invoices/api/drive/subfolders/', views_porter_invoice.porter_invoice_drive_subfolders_api, name='porter_invoice_drive_subfolders_api'),
    path('porter-invoices/api/drive/upload-batch/', views_porter_invoice.porter_invoice_drive_upload_batch_api, name='porter_invoice_drive_upload_batch_api'),
    path(
        'courier/',
        include(('operations.courier.urls', 'courier'), namespace='courier'),
    ),
]
