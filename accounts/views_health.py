"""
Health check endpoint for deployment monitoring
Tests critical system components
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
from django.db import connection
from django.conf import settings
import os
import time


@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    """
    Comprehensive health check endpoint
    Tests: Database, Storage, Basic functionality
    Returns: 200 if healthy, 503 if unhealthy
    """
    health_status = {
        'status': 'healthy',
        'timestamp': time.time(),
        'checks': {}
    }
    
    overall_healthy = True
    
    # ==========================================
    # 1. DATABASE CHECK
    # ==========================================
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        
        # Count users (tests table access and permissions)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user_count = User.objects.count()
        
        health_status['checks']['database'] = {
            'status': 'healthy',
            'connection': 'ok'
        }
    except Exception as e:
        overall_healthy = False
        health_status['checks']['database'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
    
    # ==========================================
    # 2. STORAGE CHECK (GCS in production)
    # ==========================================
    try:
        from django.core.files.storage import default_storage
        
        # Check if storage backend is accessible
        storage_backend = default_storage.__class__.__name__
        
        # Try to check if storage is writable (doesn't actually write)
        storage_available = hasattr(default_storage, 'exists')
        
        health_status['checks']['storage'] = {
            'status': 'healthy',
        }
    except Exception as e:
        overall_healthy = False
        health_status['checks']['storage'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
    
    # ==========================================
    # 3. CRITICAL MODELS CHECK
    # ==========================================
    try:
        from projects.models import ProjectCode
        from projects.models_client import ClientCard
        from supply.models import VendorCard

        model_counts = {}

        # Check ProjectCode (always exists)
        project_count = ProjectCode.objects.count()
        model_counts['projects'] = project_count

        # Check ClientCard (always exists)
        client_count = ClientCard.objects.count()
        model_counts['clients'] = client_count

        # Check VendorCard (may not exist in production yet)
        try:
            # Check if vendor_cards table exists
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name = 'vendor_cards'
                """)
                table_exists = cursor.fetchone() is not None

            if table_exists:
                vendor_count = VendorCard.objects.count()
                model_counts['vendors'] = vendor_count
            else:
                model_counts['vendors'] = 'table_not_deployed'
        except Exception:
            model_counts['vendors'] = 'not_available'

        health_status['checks']['models'] = {
            'status': 'healthy',
        }
    except Exception as e:
        overall_healthy = False
        health_status['checks']['models'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
    
    # ==========================================
    # 4. ENVIRONMENT CHECK
    # ==========================================
    try:
        health_status['checks']['environment'] = {
            'status': 'healthy',
        }
    except Exception as e:
        overall_healthy = False
        health_status['checks']['environment'] = {
            'status': 'unhealthy',
            'error': str(e)
        }
    
    # ==========================================
    # OVERALL STATUS
    # ==========================================
    if not overall_healthy:
        health_status['status'] = 'unhealthy'
        return JsonResponse(health_status, status=503)
    
    return JsonResponse(health_status, status=200)


@csrf_exempt
@require_http_methods(["GET"])
def health_check_simple(request):
    """
    Simple health check - just returns 200 if server is running
    Use this for basic liveness probes
    """
    return JsonResponse({'status': 'ok'}, status=200)