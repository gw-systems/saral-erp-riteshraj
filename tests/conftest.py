"""
Shared test fixtures and configuration
"""
import pytest
from django.contrib.auth import get_user_model
from supply.models import Location, CityCode
from projects.models import ProjectCode
from projects.models_client import ClientCard
from supply.models import VendorCard

User = get_user_model()


@pytest.fixture
def admin_user(db):
    """Create admin user for testing"""
    return User.objects.create_user(
        username='admin_test',
        email='admin@test.com',
        password='testpass123',
        role='admin'
    )


@pytest.fixture
def finance_user(db):
    """Create finance manager user"""
    return User.objects.create_user(
        username='finance_test',
        email='finance@test.com',
        password='testpass123',
        role='finance_manager'
    )


@pytest.fixture
def operations_user(db):
    """Create operations user"""
    return User.objects.create_user(
        username='ops_test',
        email='ops@test.com',
        password='testpass123',
        role='operations_coordinator'
    )


@pytest.fixture
def test_location(db):
    """Create test location"""
    return Location.objects.create(
        state='Maharashtra',
        city='Mumbai',
        location='Test Warehouse Location',
        region='West',
        is_active=True,
        pincode='400001'
    )


@pytest.fixture
def test_city_code(db):
    """Create test city code"""
    return CityCode.objects.create(
        city_name='Mumbai',
        state_code='MH',
        city_code='MUM',
        is_active=True
    )


@pytest.fixture
def test_client(db):
    """Create test client"""
    return ClientCard.objects.create(
        client_legal_name='Test Client Private Limited',
        client_is_active=True,
        client_trade_name='Test Client',
        client_short_name='TC'
    )


@pytest.fixture
def test_vendor(db):
    """Create test vendor"""
    return VendorCard.objects.create(
        vendor_legal_name='Test Vendor Private Limited',
        vendor_is_active=True,
        vendor_trade_name='Test Vendor',
        vendor_short_name='TV'
    )


@pytest.fixture
def test_project(db, test_client, admin_user):
    """Create test project"""
    return ProjectCode.objects.create(
        series_type='WAAS',
        code='TEST001',  # Set manually for tests
        project_status='active',
        state='MH',
        client_card=test_client,
        operation_coordinator=admin_user
    )