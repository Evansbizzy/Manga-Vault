from django.conf import settings
from django.core.checks import Warning, register


@register(deploy=True)
def production_stack_checks(app_configs, **kwargs):
    if settings.DEBUG:
        return []

    warnings = []
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3':
        warnings.append(Warning(
            'Production is configured to use SQLite.',
            hint='Set DATABASE_URL to a PostgreSQL connection URL for hosted multi-user deployments.',
            id='core.W001',
        ))
    if settings.CACHES['default']['BACKEND'].endswith('LocMemCache'):
        warnings.append(Warning(
            'Production cache is process-local.',
            hint='Set REDIS_URL so search results and throttles are shared across web workers.',
            id='core.W002',
        ))
    if settings.ALLOW_LOCAL_TASK_FALLBACK:
        warnings.append(Warning(
            'Local threaded task fallback is enabled in production.',
            hint='Run a Celery worker and leave ALLOW_LOCAL_TASK_FALLBACK unset or false.',
            id='core.W003',
        ))
    return warnings
