# tests/unit/test_activity_logs.py
import pytest
from django.utils import timezone
from django.test import RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def coordinator(db):
    return User.objects.create_user(
        username='coord1', password='pass', role='operation_coordinator'
    )


@pytest.fixture
def manager(db):
    return User.objects.create_user(
        username='mgr1', password='pass', role='operation_manager'
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username='admin1', password='pass', role='admin'
    )


@pytest.fixture
def controller(db):
    return User.objects.create_user(
        username='ctrl1', password='pass', role='operation_controller'
    )


@pytest.fixture
def activity_log(db, coordinator):
    from activity_logs.models import ActivityLog
    now = timezone.now()
    return ActivityLog.objects.create(
        user=coordinator,
        user_display_name='Coord One',
        role_snapshot='operation_coordinator',
        source='web',
        action_category='create',
        action_type='daily_entry_created',
        module='operations',
        description='Created daily entry for GW-001',
        timestamp=now,
        date=now.date(),
    )


# ── Visibility tests ─────────────────────────────────────────────

class TestVisibility:

    def test_coordinator_sees_only_own_logs(self, db, coordinator, manager):
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(coordinator)
        assert coordinator in visible
        assert manager not in visible

    def test_admin_sees_all(self, db, coordinator, manager, admin_user):
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(admin_user)
        assert coordinator in visible
        assert manager in visible
        assert admin_user in visible

    def test_operation_controller_sees_ops_chain(self, db, coordinator, manager, controller):
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(controller)
        assert coordinator in visible
        assert manager in visible
        assert controller in visible

    def test_operation_manager_sees_coordinators(self, db, coordinator, manager, controller):
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(manager)
        assert coordinator in visible
        assert manager in visible
        assert controller not in visible

    def test_super_user_cannot_see_admin(self, db, admin_user):
        super_user = User.objects.create_user(
            username='su1', password='pass', role='super_user'
        )
        from activity_logs.visibility import get_visible_users
        visible = get_visible_users(super_user)
        assert admin_user not in visible
        assert super_user in visible


# ── log_activity_direct tests ────────────────────────────────────

class TestLogActivityDirect:

    def test_creates_log_entry(self, db, coordinator):
        from activity_logs.utils import log_activity_direct
        from activity_logs.models import ActivityLog
        log_activity_direct(
            user=coordinator,
            source='web',
            action_category='create',
            action_type='test_action',
            module='test',
            description='Test log entry',
        )
        assert ActivityLog.objects.filter(
            user=coordinator, action_type='test_action'
        ).exists()

    def test_never_raises_on_bad_input(self, db):
        from activity_logs.utils import log_activity_direct
        # Should not raise even with None user
        log_activity_direct(
            user=None,
            source='cron',
            action_category='system',
            action_type='test',
            module='test',
            description='test',
        )

    def test_sets_date_from_timestamp(self, db, coordinator):
        from activity_logs.utils import log_activity_direct
        from activity_logs.models import ActivityLog
        log_activity_direct(
            user=coordinator, source='web',
            action_category='create', action_type='dated_test',
            module='test', description='date test',
        )
        log = ActivityLog.objects.get(action_type='dated_test')
        assert log.date == log.timestamp.date()


# ── API view tests ───────────────────────────────────────────────

class TestAPIViews:

    def test_api_month_requires_login(self, client):
        res = client.get('/activity/api/month/')
        assert res.status_code == 302  # redirect to login

    def test_api_month_returns_json(self, db, client, coordinator):
        client.force_login(coordinator)
        res = client.get('/activity/api/month/?year=2026&month=3')
        assert res.status_code == 200
        data = res.json()
        assert 'weeks' in data
        assert 'month_name' in data

    def test_api_day_returns_json(self, db, client, coordinator, activity_log):
        client.force_login(coordinator)
        res = client.get(f'/activity/api/day/{activity_log.date.isoformat()}/')
        assert res.status_code == 200
        data = res.json()
        assert 'users' in data
        assert 'date_display' in data

    def test_api_user_day_unauthorized(self, db, client, coordinator, manager):
        """Coordinator cannot see manager's day detail."""
        client.force_login(coordinator)
        res = client.get(f'/activity/api/user/{manager.pk}/day/2026-03-08/')
        assert res.status_code == 403

    def test_api_user_day_authorized(self, db, client, coordinator, activity_log):
        """Coordinator can see their own day detail."""
        client.force_login(coordinator)
        res = client.get(
            f'/activity/api/user/{coordinator.pk}/day/{activity_log.date.isoformat()}/'
        )
        assert res.status_code == 200

    def test_api_feed_filters_by_visibility(self, db, client, coordinator, manager):
        from activity_logs.models import ActivityLog
        now = timezone.now()
        # Manager log — should NOT be visible to coordinator
        ActivityLog.objects.create(
            user=manager, user_display_name='Mgr', role_snapshot='operation_manager',
            source='web', action_category='create', action_type='mgr_action',
            module='test', description='Manager action',
            timestamp=now, date=now.date(),
        )
        client.force_login(coordinator)
        res = client.get('/activity/api/feed/')
        data = res.json()
        user_ids = [l['user_id'] for l in data['logs']]
        assert manager.pk not in user_ids
