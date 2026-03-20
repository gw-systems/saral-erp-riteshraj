"""
Custom throttling classes for rate limiting.
"""
from rest_framework.throttling import UserRateThrottle


class AdminRateThrottle(UserRateThrottle):
    """
    Rate limiting for admin endpoints.
    More restrictive than regular user endpoints to prevent brute force attacks.
    """
    scope = 'admin'
    rate = '10/minute'  # 10 requests per minute for admin endpoints

    def get_cache_key(self, request, view):
        """
        Generate cache key based on IP address and admin token.
        """
        # Use IP address as identifier since admin doesn't have user accounts
        ident = request.META.get('REMOTE_ADDR')
        if not ident:
            ident = 'unknown'

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }
