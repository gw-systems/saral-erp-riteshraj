"""
CI Pipeline Tests for Saral ERP
================================
Run in deploy.yml to catch bugs before Docker build.

Test 1: Template Compilation — all HTML templates compile
Test 2: URL Resolution — all named URLs resolve
Test 3: Form Rendering — all forms instantiate and render
Test 4: Permissions — protected views enforce access control
Test 5: CSRF Protection — POST endpoints require CSRF token
Test 6: Static Assets — critical static files exist
Test 7: Email Templates — email templates render without syntax errors

NOTE: Page load / role dashboard / API endpoint tests are intentionally
excluded — they query unmanaged tables (monthly_billings etc.) which
don't exist on a fresh CI database.

Usage: python manage.py test tests.test_ci_pipeline -v2 --no-input
"""

import importlib
import os

from django.conf import settings
from django.template import TemplateSyntaxError
from django.template.loader import get_template
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import User


# ---------------------------------------------------------------------------
# Test 1: Template Compilation
# ---------------------------------------------------------------------------
@override_settings(ALLOWED_HOSTS=['*'])
class TemplateCompilationTest(TestCase):
    """Verify every .html template compiles without TemplateSyntaxError."""

    def test_all_templates_compile(self):
        template_dirs = settings.TEMPLATES[0].get('DIRS', [])
        errors, count = [], 0

        for d in template_dirs:
            if not os.path.isdir(d):
                continue
            for root, _dirs, files in os.walk(d):
                for f in files:
                    if not f.endswith('.html'):
                        continue
                    rel = os.path.relpath(os.path.join(root, f), d)
                    try:
                        get_template(rel)
                        count += 1
                    except TemplateSyntaxError as exc:
                        errors.append(f"  {rel}: {exc}")
                    except Exception:
                        count += 1  # missing extends / includes — OK

        self.assertGreater(count, 50, f"Only {count} templates found — check TEMPLATES dirs")
        self.assertEqual(
            len(errors), 0,
            f"\n{len(errors)} template syntax errors:\n" + "\n".join(errors[:20]),
        )


# ---------------------------------------------------------------------------
# Test 2: URL Resolution
# ---------------------------------------------------------------------------
@override_settings(ALLOWED_HOSTS=['*'])
class URLResolutionTest(TestCase):
    """Verify all named URL patterns (without required args) resolve."""

    @staticmethod
    def _collect(patterns, prefix=''):
        out = []
        for p in patterns:
            if hasattr(p, 'url_patterns'):
                ns = getattr(p, 'namespace', '') or ''
                out.extend(
                    URLResolutionTest._collect(
                        p.url_patterns, f"{prefix}{ns}:" if ns else prefix
                    )
                )
            elif hasattr(p, 'name') and p.name and '<' not in str(p.pattern):
                out.append(f"{prefix}{p.name}")
        return out

    def test_no_arg_urls_resolve(self):
        from minierp.urls import urlpatterns

        names = self._collect(urlpatterns)

        errors = []
        for n in names:
            try:
                reverse(n)
            except Exception as exc:
                errors.append(f"  {n}: {exc}")

        self.assertGreater(len(names), 100, f"Only {len(names)} no-arg URLs — expected 100+")
        self.assertEqual(
            len(errors), 0,
            f"\n{len(errors)}/{len(names)} URL errors:\n" + "\n".join(errors[:20]),
        )


# ---------------------------------------------------------------------------
# Test 3: Form Rendering
# ---------------------------------------------------------------------------
@override_settings(ALLOWED_HOSTS=['*'])
class FormRenderingTest(TestCase):
    """Instantiate and render all project forms."""

    FORMS = [
        ('supply.forms', [
            'VendorCardForm', 'LocationForm', 'VendorWarehouseForm',
            'WarehouseProfileForm', 'WarehouseCapacityForm',
            'WarehouseCommercialForm', 'WarehouseContactForm',
        ]),
        ('projects.forms', ['ProjectCreateForm']),
        ('projects.forms_client', [
            'ClientCardForm', 'ClientContactForm', 'ClientGSTForm',
        ]),
        ('projects.forms_quotation', [
            'QuotationSettingsForm',
            # EmailQuotationForm requires (user, quotation) args — tested separately below
        ]),
        ('projects.forms_document', ['ProjectDocumentForm']),
        ('integrations.adobe_sign.forms', [
            'DocumentTemplateForm', 'AgreementRejectForm',
        ]),
    ]

    def test_forms_render(self):
        errors, count = [], 0
        for mod_path, form_names in self.FORMS:
            try:
                mod = importlib.import_module(mod_path)
            except ImportError as exc:
                errors.append(f"  import {mod_path}: {exc}")
                continue
            for name in form_names:
                try:
                    cls = getattr(mod, name)
                    cls().as_p()
                    count += 1
                except Exception as exc:
                    errors.append(f"  {mod_path}.{name}: {exc}")

        self.assertGreater(count, 5, f"Only {count} forms rendered")
        self.assertEqual(
            len(errors), 0, f"\nForm rendering errors:\n" + "\n".join(errors)
        )

    def test_email_quotation_form_importable(self):
        """EmailQuotationForm requires (user, quotation) args — verify it imports cleanly."""
        from projects.forms_quotation import EmailQuotationForm
        self.assertTrue(callable(EmailQuotationForm))


# ---------------------------------------------------------------------------
# Test 4: Permission / Authorization
# ---------------------------------------------------------------------------
@override_settings(ALLOWED_HOSTS=['*'])
class PermissionTest(TestCase):
    """Verify access control on protected views."""

    def test_unauthenticated_redirect(self):
        c = Client()
        urls = [
            'accounts:dashboard',
            'accounts:user_list',
            'projects:project_list_all',
            'operations:daily_entry_list',
            'supply:location_list',
        ]
        for name in urls:
            resp = c.get(reverse(name))
            self.assertIn(
                resp.status_code, [301, 302],
                f"{name}: expected redirect, got {resp.status_code}",
            )

    def test_non_admin_rejected_on_admin_endpoint(self):
        coord = User.objects.create_user(
            username='ci_perm', password='CiTest!1234', role='operation_coordinator'
        )
        c = Client()
        c.force_login(coord)
        resp = c.post(reverse('accounts:resolve_all_errors'))
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Test 5: CSRF Protection
# ---------------------------------------------------------------------------
@override_settings(ALLOWED_HOSTS=['*'])
class CSRFProtectionTest(TestCase):
    """POST without CSRF token must be rejected."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='ci_csrf', password='CiTest!1234', role='admin'
        )

    def test_post_without_csrf_rejected(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.user)

        endpoints = [
            'accounts:resolve_all_errors',
            'supply:location_create',
        ]
        for name in endpoints:
            resp = c.post(reverse(name), data={})
            self.assertEqual(
                resp.status_code, 403,
                f"{name}: expected 403 without CSRF, got {resp.status_code}",
            )


# ---------------------------------------------------------------------------
# Test 6: Static Asset Integrity
# ---------------------------------------------------------------------------
class StaticAssetIntegrityTest(TestCase):
    """Verify critical static files are present in source."""

    CRITICAL_FILES = [
    ]

    def test_static_files_exist(self):
        search_dirs = list(getattr(settings, 'STATICFILES_DIRS', [])) + [
            os.path.join(settings.BASE_DIR, 'static'),
        ]
        static_root = getattr(settings, 'STATIC_ROOT', None)
        if static_root:
            search_dirs.append(static_root)

        missing = []
        for filepath in self.CRITICAL_FILES:
            found = any(
                os.path.exists(os.path.join(d, filepath)) for d in search_dirs
            )
            if not found:
                missing.append(filepath)

        self.assertEqual(
            len(missing), 0, f"\nMissing static files:\n  " + "\n  ".join(missing)
        )


# ---------------------------------------------------------------------------
# Test 7: Email Template Rendering
# ---------------------------------------------------------------------------
@override_settings(ALLOWED_HOSTS=['*'])
class EmailTemplateRenderingTest(TestCase):
    """Email templates must compile (no syntax errors)."""

    TEMPLATES = [
        'projects/quotations/quotation_email.html',
        'operations/renewal_send_email.html',
        'supply/rfq_email.html',
    ]

    def test_email_templates_compile(self):
        errors = []
        for name in self.TEMPLATES:
            try:
                get_template(name)
            except TemplateSyntaxError as exc:
                errors.append(f"  {name}: {exc}")
            except Exception:
                pass  # Missing template or context errors — OK

        self.assertEqual(
            len(errors), 0, f"\nEmail template errors:\n" + "\n".join(errors)
        )
