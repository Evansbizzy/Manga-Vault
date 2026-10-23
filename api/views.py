import logging
import re
import requests
from urllib.parse import quote, unquote, urlparse

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.http import FileResponse, Http404, HttpResponse
from django.views import View
from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q
from pathlib import Path
from core.models import Manga, Chapter, Volume, DownloadTask, ReadingProgress
from core.scrapers import get_scraper, list_scrapers, search_all
from core.tasks import (
    download_chapters_task,
    download_volume_task,
    run_download_chapters,
    run_download_volume,
)
from core.models import chapter_sort_key
from core.utils.network import safe_get, validate_public_http_url

logger = logging.getLogger(__name__)

ALLOWED_LANGUAGES = {"en", "fr"}


def _image_proxy_url(image_url, source):
    if not image_url:
        return ""
    return f"/api/proxy-image/?url={quote(image_url, safe='')}&source={quote(source, safe='')}"


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _enqueue_or_run(task_callable, fallback_callable, task_id, *extra_args):
    """
    Try Celery first; fall back to threaded background execution.
    Always returns the *database* task ID so that the frontend can poll it.
    """
    try:
        task_callable.delay(task_id, *extra_args)
        return {"task_id": task_id, "queued": True}
    except Exception as exc:
        logger.warning("Celery unavailable; starting task %s locally: %s", task_id, exc)
        fallback_callable(task_id, *extra_args)
        return {"task_id": task_id, "queued": False}


def _serve_download(path_value: str):
    if not path_value:
        raise Http404("File not found")

    path = Path(path_value)
    downloads_root = Path(settings.DOWNLOADS_DIR).resolve()
    try:
        resolved = path.resolve()
    except (FileNotFoundError, OSError):
        raise Http404("File not found")

    if downloads_root not in resolved.parents and resolved != downloads_root:
        raise Http404("File not found")
    if not resolved.exists():
        raise Http404("File not found")

    return FileResponse(open(resolved, "rb"), as_attachment=True, filename=resolved.name)


def _sync_manga(manga, data, scraper_name):
    manga.title = data.title
    manga.alt_titles = data.alt_titles
    manga.author = data.author
    manga.artist = data.artist
    manga.description = data.description
    manga.cover_url = data.cover_url
    manga.status = data.status
    manga.source = scraper_name
    manga.source_id = data.source_id
    manga.content_type = data.content_type
    manga.save()

    volume_map = {v.volume_number: v for v in manga.volumes.all()}
    existing_chapters = {(c.chapter_number, c.language): c for c in manga.chapters.all()}

    for ch in data.chapters:
        if ch.language not in ALLOWED_LANGUAGES:
            continue

        chapter_key = (ch.number, ch.language)
        chapter = existing_chapters.get(chapter_key)
        if chapter is None:
            chapter = Chapter.objects.create(
                manga=manga,
                chapter_number=ch.number,
                title=ch.title,
                volume=ch.volume or '',
                source_url=ch.source_url,
                language=ch.language,
            )
            existing_chapters[chapter_key] = chapter
        else:
            chapter.title = ch.title
            chapter.volume = ch.volume or ''
            chapter.source_url = ch.source_url
            chapter.language = ch.language
            chapter.save()

        vol_num = ch.volume or ''
        vol = volume_map.get(vol_num)
        if vol is None:
            vol = Volume.objects.create(manga=manga, volume_number=vol_num)
            volume_map[vol_num] = vol
        vol.chapters.add(chapter)

    return manga


# ---------------------------------------------------------------------------
# API Views
# ---------------------------------------------------------------------------


class SearchView(APIView):
    throttle_scope = 'search'

    def get(self, request):
        query = request.GET.get('q', '').strip()
        source = request.GET.get('source', 'all')
        if not query:
            return Response({'error': 'Query required'}, status=400)
        if len(query) > 200:
            return Response({'error': 'Query must be 200 characters or fewer'}, status=400)

        try:
            if source == 'all':
                results, source_status = search_all(query)
            else:
                scraper = get_scraper(source)
                if not getattr(scraper, 'supports_search', False):
                    return Response({'error': f'{source} does not support search'}, status=400)
                items = scraper.search(query)
                results = [{
                    'source': scraper.name,
                    'title': item.title,
                    'alt_titles': item.alt_titles,
                    'author': item.author,
                    'cover': item.cover_url,
                    'source_id': item.source_id,
                    'content_type': item.content_type,
                    'chapters_count': len(item.chapters),
                } for item in items]
                source_status = [{
                    'source': scraper.name,
                    'label': getattr(scraper, 'label', scraper.name.title()),
                    'status': 'ok',
                    'count': len(results),
                    'message': '',
                }]
        except Exception as exc:
            logger.error("Search failed: %s", exc)
            return Response({'error': f'Search failed: {exc}'}, status=500)

        return Response({
            'results': [
                {**item, 'cover': _image_proxy_url(item.get('cover'), item.get('source'))}
                for item in results
            ],
            'sources': list_scrapers(),
            'source_status': source_status,
        })


class ImportMangaView(APIView):
    throttle_scope = 'import'

    def post(self, request):
        source = request.data.get('source', 'auto')
        source_id = request.data.get('source_id') or request.data.get('url')
        force_refresh = _as_bool(request.data.get('refresh', False))
        if not source_id:
            return Response({'error': 'source_id or url required'}, status=400)
        if not isinstance(source_id, str) or len(source_id) > 2048:
            return Response({'error': 'source_id must be a URL under 2048 characters'}, status=400)

        try:
            scraper = get_scraper(source, source_id)
            data = scraper.get_manga_details(source_id)
        except Exception as exc:
            logger.error("Import failed for %s: %s", source_id, exc)
            return Response({'error': f'Failed to fetch manga: {exc}'}, status=500)

        canonical_source_id = data.source_id

        existing = Manga.objects.filter(source=scraper.name, source_id=canonical_source_id).first()
        if existing and not force_refresh and existing.chapters.exists():
            return Response({
                'status': 'exists',
                'manga_id': existing.id,
                'chapters': existing.chapters.count()
            })
        if existing:
            manga = _sync_manga(existing, data, scraper.name)
            return Response({
                'status': 'refreshed',
                'manga_id': manga.id,
                'chapters': manga.chapters.count()
            })

        manga = Manga.objects.create(
            title=data.title,
            alt_titles=data.alt_titles,
            author=data.author,
            artist=data.artist,
            description=data.description,
            cover_url=data.cover_url,
            status=data.status,
            source=scraper.name,
            source_id=data.source_id,
            content_type=data.content_type,
        )

        volume_map = {}
        seen_chapters = set()
        for ch in data.chapters:
            if ch.language not in ALLOWED_LANGUAGES:
                continue
            chapter_key = (ch.number, ch.language)
            if chapter_key in seen_chapters:
                continue
            seen_chapters.add(chapter_key)

            chapter = Chapter.objects.create(
                manga=manga,
                chapter_number=ch.number,
                title=ch.title,
                volume=ch.volume or '',
                source_url=ch.source_url,
                language=ch.language,
            )
            vol_num = ch.volume or ''
            if vol_num not in volume_map:
                volume_map[vol_num] = Volume.objects.create(
                    manga=manga,
                    volume_number=vol_num,
                )
            volume_map[vol_num].chapters.add(chapter)

        return Response({
            'status': 'imported',
            'manga_id': manga.id,
            'chapters': len(seen_chapters),
        })


class MangaDetailView(APIView):
    def get(self, request, pk):
        manga = get_object_or_404(Manga, pk=pk)
        manga_path = urlparse(manga.source_id).path
        if manga.source == "mangahere" and re.search(r"/c\d+(?:\.\d+)?/", manga_path):
            try:
                scraper = get_scraper(manga.source, manga.source_id)
                manga = _sync_manga(manga, scraper.get_manga_details(manga.source_id), scraper.name)
            except Exception as exc:
                logger.warning("Could not repair legacy MangaHere import %s: %s", manga.id, exc)
        return Response({
            'id': manga.id,
            'title': manga.title,
            'author': manga.author,
            'description': manga.description,
            'cover': _image_proxy_url(manga.cover_url, manga.source),
            'status': manga.status,
            'content_type': manga.content_type,
            'source': manga.source,
            'source_id': manga.source_id,
            'chapters_downloaded': manga.downloaded_chapters_count,
            'total_chapters': manga.total_chapters_count,
        })


class ChapterListView(APIView):
    def get(self, request, pk):
        manga = get_object_or_404(Manga, pk=pk)
        chapters = sorted(
            manga.chapters.all().only(
                'id', 'chapter_number', 'title', 'downloaded', 'file_size',
                'language', 'volume',
            ),
            key=lambda ch: chapter_sort_key(ch.chapter_number),
        )

        volume_map = {
            volume.volume_number: volume
            for volume in manga.volumes.only('id', 'volume_number', 'downloaded')
        }
        volumes = {}
        for ch in chapters:
            vol = ch.volume or 'No Volume'
            if vol not in volumes:
                volumes[vol] = {
                    'id': None,
                    'volume': vol,
                    'downloaded': False,
                    'chapters': [],
                }
            volume_obj = volume_map.get(ch.volume or '')
            volumes[vol]['id'] = volume_obj.id if volume_obj else None
            volumes[vol]['downloaded'] = bool(volume_obj and volume_obj.downloaded)
            volumes[vol]['chapters'].append({
                'id': ch.id,
                'number': ch.chapter_number,
                'title': ch.title,
                'downloaded': ch.downloaded,
                'file_size': ch.file_size,
                'language': ch.language,
            })

        return Response({
            'volumes': sorted(volumes.values(), key=lambda item: chapter_sort_key(item['volume']))
        })


class ChapterPagesView(APIView):
    """Return proxied image URLs for reading a chapter online."""

    def get(self, request, chapter_id):
        chapter = get_object_or_404(Chapter, id=chapter_id)
        manga = chapter.manga
        cache_key = f'reader-pages:v1:{chapter.pk}:{chapter.source_url}'
        pages = cache.get(cache_key)
        try:
            if pages is None:
                scraper = get_scraper(manga.source, manga.source_id)
                pages = scraper.get_chapter_pages(chapter.source_url)
                if pages:
                    cache.set(cache_key, pages, 30 * 60)
        except Exception as exc:
            logger.error("Failed to get pages for chapter %s: %s", chapter_id, exc)
            return Response({'error': f'Failed to load pages: {exc}'}, status=500)

        # Proxy all image URLs through our server to bypass CORS/hotlink blocks
        proxied_pages = [
            _image_proxy_url(url, manga.source)
            for url in pages
        ]

        all_chapters = sorted(
            manga.chapters.all(),
            key=lambda ch: chapter_sort_key(ch.chapter_number),
        )
        chapter_ids = [c.id for c in all_chapters]
        current_idx = chapter_ids.index(chapter.id) if chapter.id in chapter_ids else -1
        prev_id = chapter_ids[current_idx - 1] if current_idx > 0 else None
        next_id = chapter_ids[current_idx + 1] if current_idx < len(chapter_ids) - 1 else None

        return Response({
            'manga_id': manga.id,
            'manga_title': manga.title,
            'chapter_id': chapter.id,
            'chapter_number': chapter.chapter_number,
            'chapter_title': chapter.title,
            'pages': proxied_pages,
            'prev_chapter_id': prev_id,
            'next_chapter_id': next_id,
        })


class ChapterProgressView(APIView):
    throttle_scope = 'progress'

    def get(self, request, chapter_id):
        chapter = get_object_or_404(Chapter, id=chapter_id)
        if not request.user.is_authenticated:
            return Response({'current_page': 0, 'completed': False})
        progress = ReadingProgress.objects.filter(user=request.user, chapter=chapter).first()
        return Response({
            'current_page': progress.current_page if progress else 0,
            'completed': progress.completed if progress else False,
        })

    def post(self, request, chapter_id):
        if not request.user.is_authenticated:
            return Response({'error': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        chapter = get_object_or_404(Chapter, id=chapter_id)
        current_page = request.data.get('current_page')
        if isinstance(current_page, bool) or not isinstance(current_page, int) or not 0 <= current_page <= 10000:
            return Response({'error': 'current_page must be an integer between 0 and 10000'}, status=400)

        progress, _ = ReadingProgress.objects.update_or_create(
            user=request.user,
            chapter=chapter,
            defaults={
                'current_page': current_page,
                'completed': _as_bool(request.data.get('completed', False)),
            },
        )
        return Response({
            'current_page': progress.current_page,
            'completed': progress.completed,
        })


class DownloadChaptersView(APIView):
    throttle_scope = 'download'

    def post(self, request):
        chapter_ids = request.data.get('chapter_ids', [])
        if not isinstance(chapter_ids, list) or not chapter_ids:
            return Response({'error': 'No chapters specified'}, status=400)
        if len(chapter_ids) > 100:
            return Response({'error': 'A maximum of 100 chapters can be downloaded at once'}, status=400)

        try:
            chapter_ids = [int(chapter_id) for chapter_id in chapter_ids]
        except (TypeError, ValueError):
            return Response({'error': 'chapter_ids must contain integers'}, status=400)

        first_ch = get_object_or_404(Chapter, id=chapter_ids[0])
        manga = first_ch.manga
        chapters = Chapter.objects.filter(id__in=chapter_ids, manga=manga)
        if chapters.count() != len(set(chapter_ids)):
            return Response({'error': 'All chapters must belong to the same manga'}, status=400)

        task = DownloadTask.objects.create(manga=manga, status='pending')
        task.chapters.set(chapters)

        result = _enqueue_or_run(download_chapters_task, run_download_chapters, task.id)

        return Response({
            'task_id': result["task_id"],
            'status': 'queued' if result["queued"] else 'started',
            'chapters': len(chapter_ids),
        })


class DownloadVolumeView(APIView):
    throttle_scope = 'download'

    def post(self, request, volume_id):
        volume = get_object_or_404(Volume, id=volume_id)

        task = DownloadTask.objects.create(manga=volume.manga, status='pending')
        task.volumes.add(volume)

        result = _enqueue_or_run(
            download_volume_task, run_download_volume, task.id, volume_id
        )

        return Response({
            'task_id': result["task_id"],
            'status': 'queued' if result["queued"] else 'started',
        })


class ChapterFileView(View):
    """Serve CBZ file — plain Django View so 404 is HTML, not JSON."""
    def get(self, request, chapter_id):
        chapter = get_object_or_404(Chapter, id=chapter_id)
        if not chapter.file_path or not Path(chapter.file_path).exists():
            return HttpResponse('File not available yet. Download the chapter first.', status=404, content_type='text/plain')
        return _serve_download(chapter.file_path)


class VolumeFileView(View):
    """Serve volume CBZ — plain Django View so 404 is HTML, not JSON."""
    def get(self, request, volume_id):
        volume = get_object_or_404(Volume, id=volume_id)
        if not volume.file_path or not Path(volume.file_path).exists():
            return HttpResponse('File not available yet. Download the volume first.', status=404, content_type='text/plain')
        return _serve_download(volume.file_path)


class DownloadChapterView(APIView):
    throttle_scope = 'download'

    def post(self, request, chapter_id):
        chapter = get_object_or_404(Chapter, id=chapter_id)

        task = DownloadTask.objects.create(manga=chapter.manga, status='pending')
        task.chapters.add(chapter)

        result = _enqueue_or_run(download_chapters_task, run_download_chapters, task.id)

        return Response({
            'task_id': result["task_id"],
            'status': 'queued' if result["queued"] else 'started',
            'chapters': 1,
        })


class TaskStatusView(APIView):
    def get(self, request, task_id):
        task = get_object_or_404(DownloadTask, id=task_id)
        # Include which chapters were actually downloaded so frontend
        # can trigger file downloads only for files that exist.
        downloaded_files = []
        if task.status == 'completed':
            for ch in task.chapters.filter(downloaded=True):
                if ch.file_path and Path(ch.file_path).exists():
                    downloaded_files.append({
                        'chapter_id': ch.id,
                        'filename': Path(ch.file_path).name,
                        'url': f'/api/chapter/{ch.id}/file/',
                    })
        return Response({
            'id': task.id,
            'status': task.status,
            'progress': task.progress,
            'message': task.message,
            'downloaded_files': downloaded_files,
        })


class LibraryView(APIView):
    def get(self, request):
        manga_list = Manga.objects.annotate(
            total_chapters=Count('chapters', distinct=True),
            downloaded_chapters=Count(
                'chapters', filter=Q(chapters__downloaded=True), distinct=True,
            ),
        ).order_by('-created_at')
        reading_by_manga = {}
        if request.user.is_authenticated:
            progress_items = ReadingProgress.objects.filter(
                user=request.user,
                completed=False,
            ).select_related('chapter').order_by('chapter__manga_id', '-updated_at')
            for progress in progress_items:
                reading_by_manga.setdefault(progress.chapter.manga_id, progress)
        return Response({
            'manga': [
                {
                    'id': m.id,
                    'title': m.title,
                    'cover': _image_proxy_url(m.cover_url, m.source),
                    'source': m.source,
                    'chapters': m.total_chapters,
                    'downloaded': m.downloaded_chapters,
                    'content_type': m.content_type,
                    'reading': (
                        {
                            'chapter_id': reading_by_manga[m.id].chapter_id,
                            'chapter_number': reading_by_manga[m.id].chapter.chapter_number,
                            'page': reading_by_manga[m.id].current_page,
                        }
                        if m.id in reading_by_manga else None
                    ),
                }
                for m in manga_list
            ]
        })


class SourcesView(APIView):
    def get(self, request):
        return Response({'sources': list_scrapers()})


class ImageProxyView(APIView):
    """Proxy manga page images through the server to bypass CORS."""

    throttle_scope = 'proxy_image'

    def get(self, request):
        image_url = request.GET.get('url', '')
        if not image_url:
            return Response({'error': 'url parameter required'}, status=400)

        image_url = unquote(image_url)

        try:
            parsed = urlparse(image_url)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
                return Response({'error': 'Only HTTP(S) image URLs are allowed'}, status=400)
            validate_public_http_url(image_url)
            source = request.GET.get('source', '')
            if not source:
                return Response({'error': 'source parameter required'}, status=400)
            try:
                referer = get_scraper(source).image_referer(image_url)
            except ValueError:
                return Response({'error': 'Unknown image source'}, status=400)

            resp = safe_get(requests, image_url, allow_redirects=False, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'Referer': referer,
                'Accept': 'image/avif,image/webp,image/png,image/jpeg,*/*',
            }, timeout=(5, 20), stream=True)
            with resp:
                resp.raise_for_status()
                content_length = resp.headers.get('Content-Length')
                if content_length and int(content_length) > 20 * 1024 * 1024:
                    return Response({'error': 'Image is too large'}, status=413)

                content_type = resp.headers.get('Content-Type', '').split(';', 1)[0].lower()
                if content_type not in {
                    'image/avif', 'image/bmp', 'image/gif', 'image/jpeg', 'image/png', 'image/webp',
                }:
                    return Response({'error': 'Source did not return an image'}, status=502)

                image_data = bytearray()
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    image_data.extend(chunk)
                    if len(image_data) > 20 * 1024 * 1024:
                        return Response({'error': 'Image is too large'}, status=413)

            response = HttpResponse(bytes(image_data), content_type=content_type)
            response['Cache-Control'] = 'public, max-age=86400'
            response['X-Content-Type-Options'] = 'nosniff'
            return response

        except ValueError as exc:
            return Response({'error': str(exc)}, status=400)
        except Exception as exc:
            logger.error("Image proxy failed for %s: %s", image_url, exc)
            return Response({'error': f'Failed to fetch image: {exc}'}, status=502)


class DeleteMangaView(APIView):
    def delete(self, request, pk):
        manga = get_object_or_404(Manga, pk=pk)
        title = manga.title
        manga.delete()
        return Response({'status': 'deleted', 'title': title})
