#!/usr/bin/env python
"""
Test health check against staging database
"""
import os
import sys
import django

# Set up Django environment with staging database
# Use local TCP connection via Cloud SQL Proxy (not Unix socket)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'minierp.settings')
os.environ['USE_CLOUD_SQL'] = 'False'  # Use TCP connection for local proxy
os.environ['DB_NAME'] = 'erp_staging'
os.environ['DB_USER'] = 'admin_staging'
os.environ['DB_PASSWORD'] = 'Godam@123'
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_PORT'] = '5433'  # Cloud SQL Proxy is running on 5433
os.environ['SECRET_KEY'] = 'test-key-for-health-check'
os.environ['DEBUG'] = 'False'

# GCS settings (not actually used in health check but might be imported)
os.environ['GS_BUCKET_NAME'] = 'test-bucket'
os.environ['GS_PROJECT_ID'] = 'test-project'

django.setup()

# Import and test health check
from accounts.views_health import health_check
from django.test import RequestFactory
import json

print("Testing health check against staging database...")
print("=" * 60)

factory = RequestFactory()
request = factory.get('/accounts/health/')

try:
    response = health_check(request)
    print(f"✅ Status Code: {response.status_code}")
    print(f"\n📋 Response Body:")
    print(json.dumps(json.loads(response.content), indent=2))

    if response.status_code == 200:
        print("\n✅ Health check PASSED - safe to deploy!")
        sys.exit(0)
    else:
        print("\n❌ Health check FAILED - do not deploy yet")
        sys.exit(1)
except Exception as e:
    print(f"\n❌ Error running health check: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
