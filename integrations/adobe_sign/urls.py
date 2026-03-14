"""
Adobe Sign URL Configuration
"""

from django.urls import path
from . import views

app_name = 'adobe_sign'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Document Templates (Admin)
    path('templates/', views.template_list, name='template_list'),
    path('templates/create/', views.template_create, name='template_create'),
    path('templates/<uuid:template_id>/edit/', views.template_edit, name='template_edit'),
    path('templates/<uuid:template_id>/delete/', views.template_delete, name='template_delete'),

    # Agreement Workflow - Backoffice
    path('agreements/add/', views.agreement_add, name='agreement_add'),
    path('agreements/<uuid:agreement_id>/edit/', views.agreement_edit, name='agreement_edit'),
    path('agreements/<uuid:agreement_id>/submit/', views.agreement_submit, name='agreement_submit'),
    path('agreements/<uuid:agreement_id>/replace-document/', views.replace_document, name='replace_document'),
    path('agreements/<uuid:agreement_id>/recall/', views.agreement_recall, name='agreement_recall'),
    path('agreements/<uuid:agreement_id>/recall-from-signing/', views.agreement_recall_from_signing, name='agreement_recall_from_signing'),
    path('agreements/<uuid:agreement_id>/resubmit/', views.agreement_resubmit, name='agreement_resubmit'),

    # Agreement Workflow - Admin (Director)
    path('agreements/pending/', views.pending_agreements, name='pending_agreements'),
    path('agreements/<uuid:agreement_id>/review/', views.agreement_review, name='agreement_review'),
    path('agreements/<uuid:agreement_id>/approve/', views.agreement_approve, name='agreement_approve'),
    path('agreements/<uuid:agreement_id>/reject/', views.agreement_reject, name='agreement_reject'),
    path('agreements/<uuid:agreement_id>/send-to-client/', views.send_to_client, name='send_to_client'),

    # Agreement Details
    path('agreements/<uuid:agreement_id>/', views.agreement_detail, name='agreement_detail'),
    path('agreements/<uuid:agreement_id>/events/', views.agreement_events, name='agreement_events'),
    path('agreements/<uuid:agreement_id>/download/', views.download_signed_document, name='download_signed'),

    # AJAX endpoints
    path('agreements/<uuid:agreement_id>/sync-status/', views.sync_agreement_status, name='sync_status'),
    path('agreements/<uuid:agreement_id>/authoring-url/', views.get_authoring_url, name='get_authoring_url'),
    path('agreements/<uuid:agreement_id>/director-signing-url/', views.get_director_signing_url, name='get_director_signing_url'),
    path('agreements/<uuid:agreement_id>/send-reminder/', views.send_reminder, name='send_reminder'),
    path('agreements/<uuid:agreement_id>/cancel/', views.cancel_agreement, name='cancel_agreement'),

    # Settings
    path('settings/', views.settings_view, name='settings'),
    path('settings/test-connection/', views.test_connection, name='test_connection'),

    # Webhook (Adobe Sign sends events here)
    path('webhook/', views.adobe_webhook, name='webhook'),
]
