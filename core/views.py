import logging
import hashlib
from pathlib import Path

from django.core.cache import cache
from django.contrib.auth.views import LoginView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, HttpResponse
from django.db.models import Count
from django.db import connection
from django.core.cache import cache
from django.views.generic import TemplateView, DetailView
from django.views import View
from django.shortcuts import render, get_object_or_404
from .models import Manga, Chapter, Volume, ReadingProgress
from .scrapers import get_scraper
from .utils.downloads import download_chapter, download_volume

logger = logging.getLogger(__name__)


class RateLimitedLoginView(LoginView):
    def dispatch(self, request, *args, **kwargs):
        remote_address = request.META.get('REMOTE_ADDR', 'unknown')
        digest = hashlib.sha256(remote_address.encode()).hexdigest()
        self.attempt_key = f'login-attempts:{digest}'
        if cache.get(self.attempt_key, 0) >= 10:
            return HttpResponse('Too many sign-in attempts. Try again later.', status=429)
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        cache.add(self.attempt_key, 0, timeout=900)
        try:
            cache.incr(self.attempt_key)
        except ValueError:
            cache.set(self.attempt_key, 1, timeout=900)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self.attempt_key)
        return super().form_valid(form)


def robots_txt(request):
    return HttpResponse(
        'User-agent: *\n'
        'Allow: /\n'
        'Disallow: /admin/\n'
        'Disallow: /api/\n'
        'Disallow: /library/\n'
        'Disallow: /reader/\n'
        'Disallow: /download/\n',
        content_type='text/plain; charset=utf-8',
    )


def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        cache.set('health-check', 'ok', timeout=15)
        if cache.get('health-check') != 'ok':
            raise RuntimeError('cache read-after-write failed')
    except Exception:
        logger.exception('Health check dependency failed')
        return HttpResponse('unhealthy', status=503, content_type='text/plain; charset=utf-8')
    return HttpResponse('ok', content_type='text/plain; charset=utf-8')


def page_not_found(request, exception):
    return render(request, '404.html', status=404)


class IndexView(TemplateView):
    template_name = 'core/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        manga_query = Manga.objects.filter(owner=self.request.user) if self.request.user.is_authenticated else Manga.objects.none()
        context['manga_list'] = manga_query.annotate(
            chapter_count=Count('chapters', distinct=True),
        ).order_by('-created_at')[:12]
        if self.request.user.is_authenticated:
            context['continue_reading'] = [
                {
                    'progress': progress,
                    'percent': min(
                        100,
                        int((progress.current_page + 1) * 100 / progress.chapter.page_count),
                    ) if progress.chapter.page_count else 0,
                }
                for progress in ReadingProgress.objects.filter(
                    user=self.request.user,
                    completed=False,
                ).select_related('chapter__manga').order_by('-updated_at')[:4]
            ]
        else:
            context['continue_reading'] = []
        return context


class SearchPageView(View):
    def get(self, request):
        return render(request, 'core/search.html')


class AboutPageView(TemplateView):
    template_name = 'core/about.html'


class PrivacyPolicyPageView(TemplateView):
    template_name = 'core/privacy_policy.html'


class TermsOfServicePageView(TemplateView):
    template_name = 'core/terms_of_service.html'


class ContentPolicyPageView(TemplateView):
    template_name = 'core/content_policy.html'


class LibraryPageView(LoginRequiredMixin, TemplateView):
    template_name = 'core/library.html'


class MangaDetailPageView(LoginRequiredMixin, DetailView):
    model = Manga
    template_name = 'core/manga_detail.html'
    context_object_name = 'manga'

    def get_queryset(self):
        return Manga.objects.filter(owner=self.request.user)


class ReaderPageView(LoginRequiredMixin, View):
    def get(self, request, chapter_id):
        chapter = get_object_or_404(Chapter, id=chapter_id, manga__owner=request.user)
        return render(request, 'core/reader.html', {
            'chapter': chapter,
            'manga': chapter.manga,
        })


class DownloadChapterFileView(LoginRequiredMixin, View):
    """Create or reuse a chapter CBZ and stream it to the browser."""

    def get(self, request, chapter_id):
        chapter = get_object_or_404(Chapter, id=chapter_id, manga__owner=request.user)
        try:
            file_path = download_chapter(chapter)
        except ValueError as exc:
            logger.warning("Chapter %s is not downloadable: %s", chapter_id, exc)
            return HttpResponse(f'Download unavailable: {exc}', status=422,
                                content_type='text/plain; charset=utf-8')
        except Exception as exc:
            logger.error("Download failed for chapter %s: %s", chapter_id, exc)
            return HttpResponse(f'Download failed: {exc}', status=502,
                                content_type='text/plain; charset=utf-8')

        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=file_path.name)


class DownloadVolumeFileView(LoginRequiredMixin, View):
    """Create or reuse a volume CBZ and stream it to the browser."""

    def get(self, request, volume_id):
        volume = get_object_or_404(Volume, id=volume_id, manga__owner=request.user)
        manga = volume.manga
        chapters = volume.chapters.all().order_by('chapter_number')

        if not chapters.exists():
            return HttpResponse('No chapters in this volume.', status=404,
                                content_type='text/plain')

        try:
            file_path = download_volume(volume)
        except Exception as exc:
            logger.error("Download failed for volume %s: %s", volume_id, exc)
            return HttpResponse(f'Download failed: {exc}', status=500,
                                content_type='text/plain')
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=file_path.name)
