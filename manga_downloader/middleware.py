from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


class ProductionLoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG or request.user.is_authenticated or self._is_public_path(request.path_info):
            return self.get_response(request)

        if request.path_info.startswith('/api/'):
            return JsonResponse({'detail': 'Authentication required.'}, status=401)

        login_url = reverse('login')
        return redirect(f'{login_url}?next={request.get_full_path()}')

    @staticmethod
    def _is_public_path(path):
        return (
            path == reverse('login')
            or path == '/robots.txt'
            or path.startswith(settings.STATIC_URL)
            or path.startswith(settings.MEDIA_URL)
        )
