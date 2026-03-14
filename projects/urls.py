from django.urls import path
from . import views
from . import views_status
from . import views_client
from . import views_document
from . import views_agreements
from . import views_projectcard
from . import views_quotation
from . import views_oauth


app_name = 'projects'

urlpatterns = [
    # GST State Management (Admin Only)
    path('gst-states/', views.gst_state_list, name='gst_state_list'),
    path('gst-states/create/', views.gst_state_create, name='gst_state_create'),
    path('gst-states/<str:state_code>/edit/', views.gst_state_edit, name='gst_state_edit'),
    path('gst-states/<str:state_code>/delete/', views.gst_state_delete, name='gst_state_delete'),

    # My Projects
    path('my-projects/', views.my_projects_view, name='my_projects'),

    # Project List Views
    path('list/all/', views.project_list_view, name='project_list_all'),
    path('list/active/', views.project_list_view, {'filter_type': 'active'}, name='project_list_active'),
    path('not-started/', views.project_list_not_started, name='project_list_not_started'),
    path('list/pending/', views.project_list_view, {'filter_type': 'pending'}, name='project_list_pending'),
    path('list/unassigned/', views.project_list_view, {'filter_type': 'unassigned'}, name='project_list_unassigned'),
    path('list/inactive/', views.project_list_inactive, name='project_list_inactive'),
    path('list/<str:filter_type>/', views.project_list_view, name='project_list_filtered'),

    # Admin Project Codes Manager
    path('admin/project-codes/', views.admin_project_codes_view, name='admin_project_codes'),
    path('admin/project-codes/update/', views.admin_update_project_field, name='admin_update_project_field'),
    path('admin/project-codes/<str:project_id>/history/', views.admin_project_history, name='admin_project_history'),
    path('admin/project-codes/<str:project_id>/delete/', views.admin_delete_project_code, name='admin_delete_project'),
    path('admin/project-codes/undo/', views.admin_undo_last_change, name='admin_undo_last_change'),
    path('admin/project-codes/check-dependencies/', views.check_project_id_dependencies, name='check_project_id_dependencies'),
    path('admin/project-codes/undo-by-id/', views.admin_undo_change_by_id, name='admin_undo_change_by_id'),
    path('admin/change-logs/', views.all_project_change_logs, name='all_change_logs'),

    # Admin TEMP Project Cleanup
    path('admin/temp-cleanup/', views.admin_temp_project_cleanup_list, name='admin_temp_cleanup'),
    path('admin/temp-cleanup/<str:project_id>/preview/', views.admin_temp_cleanup_preview, name='admin_temp_cleanup_preview'),
    path('admin/temp-cleanup/<str:project_id>/action/', views.admin_temp_project_cleanup_action, name='admin_temp_cleanup_action'),

    # Project Management
    path('create/', views.project_create_view, name='project_create'),
    path('project-mapping/', views.project_mapping_view, name='project_mapping'),
    path('update-managers/', views.update_project_managers, name='update_project_managers'),
    path('bulk-update/', views.bulk_update_managers, name='bulk_update_managers'),
    path('api/mergeable-projects/<str:temp_project_id>/', views.get_mergeable_projects_api, name='mergeable_projects_api'),

    
    # API Endpoints (before project_id catch-all)
    path('api/coordinators/', views.get_coordinators_api, name='get_coordinators_api'),
    path('api/sales-managers/', views.get_sales_managers_api, name='get_sales_managers_api'),

    # Status Management (before project_id catch-all)
    path('status/change/<str:project_id>/', views_status.change_project_status, name='change_status'),
    path('api/status-requirements/', views_status.get_status_transition_requirements, name='status_requirements'),

    # ===== CLIENT ROUTES =====
    path('clients/create/', views_client.client_card_create, name='client_card_create'),
    path('clients/', views_client.client_card_list, name='client_card_list'),
    path('clients/<str:client_code>/edit/', views_client.client_card_edit, name='client_card_edit'),
    path('clients/<str:client_code>/delete/', views_client.client_card_delete, name='client_card_delete'),
    path('clients/<str:client_code>/admin-delete/', views_client.admin_delete_client_card, name='admin_delete_client'),
    path('clients/<str:client_code>/add-contact/', views_client.client_contact_add, name='client_contact_add'),
    path('clients/<str:client_code>/contacts/<int:contact_id>/edit/', views_client.client_contact_edit, name='client_contact_edit'),
    path('clients/<str:client_code>/contacts/<int:contact_id>/delete/', views_client.client_contact_delete, name='client_contact_delete'),
    path('clients/<str:client_code>/add-gst/', views_client.client_gst_add, name='client_gst_add'),
    path('clients/<str:client_code>/gst/<int:gst_id>/edit/', views_client.client_gst_edit, name='client_gst_edit'),
    path('clients/<str:client_code>/gst/<int:gst_id>/delete/', views_client.client_gst_delete, name='client_gst_delete'),
    
    # Client Document Routes
    path('clients/<str:client_code>/documents/upload/', views_client.client_document_upload, name='client_document_upload'),
    path('clients/<str:client_code>/documents/preview/<str:field_name>/', views_client.client_document_preview, name='client_document_preview'),
    path('clients/<str:client_code>/documents/download/<str:field_name>/', views_client.client_document_download, name='client_document_download'),
    path('clients/<str:client_code>/documents/download-all/', views_client.client_document_download_all, name='client_document_download_all'),
    path('clients/<str:client_code>/documents/delete/<str:field_name>/', views_client.client_document_delete, name='client_document_delete'),
    path('clients/<str:client_code>/', views_client.client_card_detail, name='client_card_detail'),

    # Client Project Linking (NEW)
    path('clients/<str:client_code>/link-projects/', views_client.client_link_projects, name='client_link_projects'),
    path('clients/<str:client_code>/', views_client.client_card_detail, name='client_card_detail'),


    # Project Documents
    path('projects/<str:project_id>/documents/', views_document.project_document_upload, name='project_document_upload'),
    path('projects/<str:project_id>/documents/preview/<str:field_name>/', views_document.project_document_preview, name='project_document_preview'),
    path('projects/<str:project_id>/documents/download/<str:field_name>/', views_document.project_document_download, name='project_document_download'),
    path('projects/<str:project_id>/documents/delete/<str:field_name>/', views_document.project_document_delete, name='project_document_delete'),



    # ===== PROJECT CARDS (RATE CARDS / COMMERCIAL AGREEMENTS) =====
    path('project-cards/', views_projectcard.project_card_list, name='project_card_list'),
    path('project-cards/create/', views_projectcard.project_card_create_unified, name='project_card_create'),
    path('project-cards/incomplete/', views_projectcard.incomplete_project_cards_list, name='incomplete_project_cards'),
    path('project-cards/incomplete/count/', views_projectcard.incomplete_project_cards_count, name='incomplete_project_cards_count'),
    path('project-cards/project/<str:project_id>/', views_projectcard.project_card_by_project, name='project_card_by_project'),
    path('project-cards/<int:project_card_id>/', views_projectcard.project_card_detail, name='project_card_detail'),
    path('project-cards/<int:project_card_id>/edit/', views_projectcard.project_card_edit, name='project_card_edit'),
    path('project-cards/<int:project_card_id>/delete/', views_projectcard.project_card_delete, name='project_card_delete'),

    # Rate Cards (alias for project cards)
    path('rate-cards/', views_projectcard.project_card_list, name='rate_card_list'),
    path('rate-cards/create/', views_projectcard.project_card_create_unified, name='rate_card_create'),
    path('rate-cards/project/<str:project_id>/', views_projectcard.project_card_by_project, name='rate_card_by_project'),
    path('rate-cards/<int:project_card_id>/', views_projectcard.project_card_detail, name='rate_card_detail'),
    path('rate-cards/<int:project_card_id>/edit/', views_projectcard.project_card_edit, name='rate_card_edit'),
    path('rate-cards/<int:project_card_id>/delete/', views_projectcard.project_card_delete, name='rate_card_delete'),



    # ===== AGREEMENT MANAGEMENT (ESCALATIONS & RENEWALS) =====
    # Escalation Trackers
    path('escalations/', views_agreements.escalation_tracker_list, name='escalation_tracker_list'),
    path('escalations/create/<int:project_card_id>/', views_agreements.escalation_tracker_create, name='escalation_tracker_create'),
    path('escalations/<int:tracker_id>/', views_agreements.escalation_tracker_detail, name='escalation_tracker_detail'),
    path('escalations/<int:tracker_id>/send-email/', views_agreements.escalation_tracker_send_email, name='escalation_tracker_send_email'),
    path('escalations/<int:tracker_id>/inform-sales/', views_agreements.escalation_tracker_inform_sales, name='escalation_tracker_inform_sales'),
    path('escalations/<int:tracker_id>/inform-finance/', views_agreements.escalation_tracker_inform_finance, name='escalation_tracker_inform_finance'),
    path('escalations/<int:tracker_id>/client-acknowledged/', views_agreements.escalation_tracker_client_acknowledged, name='escalation_tracker_client_acknowledged'),
    path('escalations/<int:tracker_id>/apply-escalation/', views_agreements.escalation_tracker_apply_escalation, name='escalation_tracker_apply_escalation'),
    path('escalations/<int:tracker_id>/update-status/', views_agreements.escalation_tracker_update_status, name='escalation_tracker_update_status'),

    # Renewal Trackers
    path('renewals/', views_agreements.renewal_tracker_list, name='renewal_tracker_list'),
    path('renewals/create/<int:project_card_id>/', views_agreements.renewal_tracker_create, name='renewal_tracker_create'),
    path('renewals/<int:tracker_id>/', views_agreements.renewal_tracker_detail, name='renewal_tracker_detail'),
    path('renewals/<int:tracker_id>/send-email/', views_agreements.renewal_tracker_send_email, name='renewal_tracker_send_email'),
    path('renewals/<int:tracker_id>/inform-sales/', views_agreements.renewal_tracker_inform_sales, name='renewal_tracker_inform_sales'),
    path('renewals/<int:tracker_id>/client-response/', views_agreements.renewal_tracker_client_response, name='renewal_tracker_client_response'),
    path('renewals/<int:tracker_id>/complete-renewal/', views_agreements.renewal_tracker_complete_renewal, name='renewal_tracker_complete_renewal'),
    path('renewals/<int:tracker_id>/update-status/', views_agreements.renewal_tracker_update_status, name='renewal_tracker_update_status'),

    # Quotations
    path('quotations/', views_quotation.quotation_list, name='quotation_list'),
    path('quotations/create/', views_quotation.quotation_create, name='quotation_create'),
    path('quotations/settings/', views_quotation.quotation_settings, name='quotation_settings'),
    path('quotations/dashboard/', views_quotation.quotation_dashboard, name='quotation_dashboard'),
    path('quotations/auto-price/', views_quotation.quotation_auto_price, name='quotation_auto_price'),
    path('quotations/<int:quotation_id>/', views_quotation.quotation_detail, name='quotation_detail'),
    path('quotations/<int:quotation_id>/edit/', views_quotation.quotation_edit, name='quotation_edit'),
    path('quotations/<int:quotation_id>/download-docx/', views_quotation.download_docx, name='quotation_download_docx'),
    path('quotations/<int:quotation_id>/download-pdf/', views_quotation.download_pdf, name='quotation_download_pdf'),
    path('quotations/<int:quotation_id>/send-email/', views_quotation.send_email, name='quotation_send_email'),
    path('quotations/<int:quotation_id>/approve-margin/', views_quotation.quotation_approve_margin, name='quotation_approve_margin'),
    path('quotations/<int:quotation_id>/transition/', views_quotation.quotation_transition, name='quotation_transition'),
    path('quotations/<int:quotation_id>/clone/', views_quotation.quotation_clone, name='quotation_clone'),
    path('quotations/<int:quotation_id>/acceptance-link/', views_quotation.quotation_generate_acceptance_link, name='quotation_acceptance_link'),
    path('quotations/<int:quotation_id>/revisions/<int:revision_number>/', views_quotation.quotation_revision_view, name='quotation_revision_view'),
    path('quotations/accept/<uuid:token>/', views_quotation.quotation_accept_public, name='quotation_accept_public'),

    # Quotation OAuth
    path('quotations/oauth-authorize/', views_oauth.quotation_oauth_authorize, name='quotation_oauth_authorize'),
    path('quotations/oauth-callback/', views_oauth.quotation_oauth_callback, name='quotation_oauth_callback'),
    path('quotations/oauth-disconnect/<int:token_id>/', views_oauth.quotation_oauth_disconnect, name='quotation_oauth_disconnect'),

    # ⚠️ PROJECT DETAIL ROUTES MUST COME LAST (catch-all patterns) ⚠️
    path('<str:project_id>/', views.project_detail_view, name='project_detail'),
    path('<str:project_id>/update-operation-mode/', views.update_operation_mode, name='update_operation_mode'),
    path('<str:project_id>/update-coordinator/', views.update_project_coordinator, name='update_project_coordinator'),
    path('<str:project_id>/update-mis-status/', views.update_mis_status, name='update_mis_status'),
    path('<str:project_id>/update-sales-manager/', views.update_project_sales_manager, name='update_project_sales_manager'),
    path('<str:project_id>/extend-notice/', views_status.extend_notice_period, name='extend_notice_period'),
    path('<str:project_id>/edit/', views.project_edit_view, name='project_edit'),
]