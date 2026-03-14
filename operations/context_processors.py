"""
Context processors for operations app
Makes data available in all templates
"""

from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from operations.models import InAppAlert


def notifications(request):
    """
    Add unread notification count to all templates
    Available as {{ unread_notifications_count }}
    """
    if not request.user.is_authenticated:
        return {
            'unread_notifications_count': 0,
            'recent_notifications': [],
        }

    # Cache notifications for 60 seconds per user
    cache_key = f'user_notifications_{request.user.id}'
    cached_data = cache.get(cache_key)

    if cached_data is None:
        cutoff = timezone.now() - timedelta(days=30)

        unread_count = InAppAlert.objects.filter(
            user=request.user,
            is_read=False,
            created_at__gte=cutoff
        ).count()

        recent_notifications = list(
            InAppAlert.objects.filter(
                user=request.user,
                created_at__gte=cutoff
            )
            .order_by('-created_at')[:5]
            .values('id', 'title', 'message', 'created_at', 'is_read', 'alert_type')
        )

        cached_data = {
            'unread_notifications_count': unread_count,
            'recent_notifications': recent_notifications,
        }
        cache.set(cache_key, cached_data, 60)

    return cached_data