from django.conf import settings


def site_url(request):
    return {
        'SITE_URL': settings.SITE_URL,
        'SITE_CONTACT_EMAIL': settings.SITE_CONTACT_EMAIL,
    }
