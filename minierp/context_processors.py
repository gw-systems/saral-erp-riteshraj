from django.conf import settings

def app_branding(request):
    """
    Add application branding to all templates
    """
    return {
        'APP_NAME': settings.APP_NAME,
        'APP_VERSION': settings.APP_VERSION,
        'APP_FULL_NAME': settings.APP_FULL_NAME,
    }