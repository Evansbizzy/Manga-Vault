from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Chapter, Manga


class LibraryOwnershipTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user(username='owner', password='test-password')
        self.other = user_model.objects.create_user(username='other', password='test-password')
        self.manga = Manga.objects.create(
            owner=self.owner,
            title='Private series',
            source='fixture',
            source_id='fixture-private-series',
        )
        self.chapter = Chapter.objects.create(
            manga=self.manga,
            chapter_number='1',
            source_url='https://example.org/chapter/1',
        )
        self.client = APIClient()

    def test_library_only_returns_the_signed_in_users_manga(self):
        self.client.force_login(self.other)
        response = self.client.get('/api/library/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['manga'], [])

    def test_other_user_cannot_view_or_delete_manga(self):
        self.client.force_login(self.other)
        detail = self.client.get(f'/api/manga/{self.manga.pk}/')
        deletion = self.client.delete(f'/api/manga/{self.manga.pk}/delete/')
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(deletion.status_code, 404)
        self.assertTrue(Manga.objects.filter(pk=self.manga.pk).exists())

    def test_other_user_cannot_read_chapters_or_start_downloads(self):
        self.client.force_login(self.other)
        pages = self.client.get(f'/api/chapter/{self.chapter.pk}/pages/')
        download = self.client.post(f'/api/chapter/{self.chapter.pk}/download/')
        self.assertEqual(pages.status_code, 404)
        self.assertEqual(download.status_code, 404)

    def test_library_status_and_labels_can_only_be_changed_by_the_owner(self):
        self.client.force_login(self.other)
        denied = self.client.patch(
            f'/api/manga/{self.manga.pk}/',
            {'library_status': 'reading', 'tags': ['favorite']},
            format='json',
        )
        self.assertEqual(denied.status_code, 404)

        self.client.force_login(self.owner)
        updated = self.client.patch(
            f'/api/manga/{self.manga.pk}/',
            {'library_status': 'reading', 'tags': [' Favorite ', 'favorite', 'Weekend']},
            format='json',
        )
        self.assertEqual(updated.status_code, 200)
        self.manga.refresh_from_db()
        self.assertEqual(self.manga.library_status, 'reading')
        self.assertEqual(self.manga.tags, ['Favorite', 'Weekend'])

    def test_import_requires_an_authenticated_account(self):
        response = self.client.post(
            '/api/import/',
            {'source': 'mangadex', 'source_id': '00000000-0000-0000-0000-000000000000'},
            format='json',
        )
        self.assertEqual(response.status_code, 401)

    def test_same_source_series_can_exist_in_separate_private_libraries(self):
        second_copy = Manga.objects.create(
            owner=self.other,
            title='Private series',
            source='fixture',
            source_id='fixture-private-series',
        )
        self.assertNotEqual(second_copy.pk, self.manga.pk)

    def test_reader_page_is_private(self):
        self.client.force_login(self.other)
        response = self.client.get(f'/reader/{self.chapter.pk}/')
        self.assertEqual(response.status_code, 404)

