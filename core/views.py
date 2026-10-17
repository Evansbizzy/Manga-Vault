import logging
from pathlib import Path

from django.http import FileResponse, HttpResponse
from django.views.generic import TemplateView, DetailView
from django.views import View
from django.shortcuts import render, get_object_or_404
from .models import Manga, Chapter, Volume
from .scrapers import get_scraper
from .utils.downloads import download_chapter, download_volume

logger = logging.getLogger(__name__)


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
