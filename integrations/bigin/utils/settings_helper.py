"""
Bigin Settings Helper
Resolves configuration: DB settings take priority over environment variables.
"""

from django.conf import settings


def get_bigin_config():
    """
    Get Bigin/Zoho OAuth configuration.
    Priority: Database settings → Environment variables → Empty string
    """
    from integrations.bigin.models import BiginSettings
    db = BiginSettings.load()

    # ============================================================================
    # COMPREHENSIVE BIGIN API SCOPES - COMPLETE COVERAGE
    # ============================================================================
    # This includes ALL available scopes from Bigin API documentation
    # Reference: https://www.bigin.com/developer/docs/apis/v2/scopes.html
    # Last updated: 2026-02-13
    # Future-proof: No need to add more scopes unless Bigin introduces new APIs
    # ============================================================================

    default_scope = ','.join([
        # === USERS MANAGEMENT ===
        'ZohoBigin.users.ALL',                      # Full user management (view, add, update, delete)

        # === ORGANIZATION ===
        'ZohoBigin.org.ALL',                        # Full org access (details, photo upload)

        # === SETTINGS (METADATA & CONFIGURATION) ===
        'ZohoBigin.settings.ALL',                   # Full settings access (all aspects of org)
        'ZohoBigin.settings.modules.ALL',           # Module metadata (list, details, fields)
        'ZohoBigin.settings.roles.ALL',             # Role management
        'ZohoBigin.settings.profiles.ALL',          # Profile management
        'ZohoBigin.settings.fields.ALL',            # Field metadata
        'ZohoBigin.settings.layouts.ALL',           # Layout details
        'ZohoBigin.settings.related_lists.ALL',     # Related list metadata
        'ZohoBigin.settings.custom_views.ALL',      # Custom view metadata
        'ZohoBigin.settings.tags.ALL',              # Tag management (create, update, delete)

        # === MODULES (DATA ACCESS) ===
        'ZohoBigin.modules.ALL',                    # Full access to ALL modules & operations
        'ZohoBigin.modules.contacts.ALL',           # Full Contacts access (CRUD + photos + notes)
        'ZohoBigin.modules.accounts.ALL',           # Full Accounts/Companies access
        'ZohoBigin.modules.products.ALL',           # Full Products access
        'ZohoBigin.modules.deals.ALL',              # Full Deals access (not just READ)
        'ZohoBigin.modules.notes.ALL',              # Full Notes access (create, update, delete)
        'ZohoBigin.modules.attachments.ALL',        # File attachments management

        # === PIPELINES (DEALS/SALES) ===
        'ZohoBigin.modules.Pipelines.ALL',          # Full Pipeline management

        # === BULK OPERATIONS ===
        'ZohoBigin.bulk.ALL',                       # Bulk read/write for large datasets

        # === NOTIFICATIONS ===
        'ZohoBigin.notifications.ALL',              # Instant notifications (enable, update, disable)

        # === QUERY LANGUAGE ===
        'ZohoBigin.coql.READ',                      # COQL (Bigin Query Language) for complex searches
    ])

    return {
        'client_id': db.client_id or getattr(settings, 'ZOHO_CLIENT_ID', ''),
        'client_secret': db.get_decrypted_client_secret() or getattr(settings, 'ZOHO_CLIENT_SECRET', ''),
        'redirect_uri': db.redirect_uri or getattr(settings, 'ZOHO_REDIRECT_URI', ''),
        'auth_url': db.auth_url or 'https://accounts.zoho.com/oauth/v2/auth',
        'token_url': db.token_url or 'https://accounts.zoho.com/oauth/v2/token',
        'scope': db.scope if hasattr(db, 'scope') and db.scope else default_scope,
    }
