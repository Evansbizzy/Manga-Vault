import logging
import hashlib
from pathlib import Path

from django.core.cache import cache
from django.contrib.auth.views import LoginView
from django.http import FileResponse, HttpResponse
from django.views.generic import TemplateView, DetailView
from django.views import View
from django.shortcuts import render, get_object_or_404
from .models import Manga, Chapter, Volume
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


def page_not_found(request, exception):
    return render(request, '404.html', status=404)


class IndexView(TemplateView):
    template_name = 'core/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['manga_list'] = Manga.objects.all().order_by('-created_at')[:12]
        return context


class SearchPageView(View):
    def get(self, request):
        return render(request, 'core/search.html')


class LibraryPageView(TemplateView):
    template_name = 'core/library.html'


class MangaDetailPageView(DetailView):
    model = Manga
    template_name = 'core/manga_detail.html'
    context_object_name = 'manga'


class ReaderPageView(View):
    def get(self, request, chapter_id):
        chapter = get_object_or_404(Chapter, id=chapter_id)
        return render(request, 'core/reader.html', {
            'chapter': chapter,
            'manga': chapter.manga,
        })


class DownloadChapterFileView(View):
    """Create or reuse a chapter CBZ and stream it to the browser."""

    def get(self, request, chapter_id):
        chapter = get_object_or_404(Chapter, id=chapter_id)
        try:
            if chapter.file_path and Path(chapter.file_path).is_file():
                return FileResponse(
                    open(chapter.file_path, 'rb'),
                    as_attachment=True,
                    filename=Path(chapter.file_path).name,
                )
            file_path = download_chapter(chapter)
        except Exception as exc:
            logger.error("Download failed for chapter %s: %s", chapter_id, exc)
            return HttpResponse(f'Download failed: {exc}', status=500,
                                content_type='text/plain')

        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=file_path.name)


class DownloadVolumeFileView(View):
    """Create or reuse a volume CBZ and stream it to the browser."""

    def get(self, request, volume_id):
        volume = get_object_or_404(Volume, id=volume_id)
        manga = volume.manga
        chapters = volume.chapters.all().order_by('chapter_number')

        if not chapters.exists():
            return HttpResponse('No chapters in this volume.', status=404,
                                content_type='text/plain')

        try:
            if volume.file_path and Path(volume.file_path).is_file():
                file_path = Path(volume.file_path)
            else:
                file_path = download_volume(volume)
        except Exception as exc:
            logger.error("Download failed for volume %s: %s", volume_id, exc)
            return HttpResponse(f'Download failed: {exc}', status=500,
                                content_type='text/plain')
        return FileResponse(open(file_path, 'rb'), as_attachment=True, filename=file_path.name)
