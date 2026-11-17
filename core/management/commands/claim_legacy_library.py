from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Manga


class Command(BaseCommand):
    help = 'Assign ownerless legacy manga records and their related library data to one account.'

    def add_arguments(self, parser):
        parser.add_argument('username', help='Existing account that will own the legacy library')

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(**{user_model.USERNAME_FIELD: options['username']})
        except user_model.DoesNotExist as exc:
            raise CommandError(f"No account found for {options['username']!r}.") from exc

        count = Manga.objects.filter(owner__isnull=True).update(owner=user)
        self.stdout.write(self.style.SUCCESS(
            f'Assigned {count} legacy manga record(s) and their related data to {user_model.USERNAME_FIELD}={options["username"]!r}.'
        ))
