from pathlib import Path
import zipfile

from django.utils import timezone
from core.models import chapter_sort_key

from .chapter_pages import get_chapter_page_urls

from .packager import ChapterPackager


def is_current_chapter_archive(chapter):
    if not chapter.downloaded or not chapter.file_path or chapter.page_count < 1:
        return False
    path = Path(chapter.file_path)
    packager = ChapterPackager()
    expected = packager.output_dir / packager.chapter_filename(
        chapter.manga.title, chapter.chapter_number, chapter.volume or None, chapter.language
    )
    if path.resolve() != expected.resolve() or not path.is_file() or not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as archive:
            entries = [
                item for item in archive.infolist()
                if not item.is_dir() and Path(item.filename).suffix.lower() in {
                    '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.avif'
                }
            ]
            return len(entries) == chapter.page_count and path.stat().st_size == chapter.file_size
    except (OSError, zipfile.BadZipFile):
        return False


def download_chapter(chapter):
    from core.scrapers import get_scraper

    scraper = get_scraper(chapter.manga.source, chapter.manga.source_id)
    page_urls = get_chapter_page_urls(chapter)
    if chapter.page_count == len(page_urls) and is_current_chapter_archive(chapter):
        return Path(chapter.file_path)
    if chapter.downloaded:
        # Older versions marked partial downloads as complete. Hide that status
        # before retrying so a failed repair cannot expose the stale archive.
        chapter.downloaded = False
        chapter.save(update_fields=['downloaded'])

    images = scraper.download_chapter_images_from_urls(page_urls)
    if not images:
        raise ValueError(
            f'No image data was received for Chapter {chapter.chapter_number}. '
            'The source may have blocked the page requests or changed its reader.'
        )

    file_path = Path(ChapterPackager().create_cbz(
        images,
        chapter.manga.title,
        chapter.chapter_number,
        chapter.volume or None,
        chapter.language,
    ))
    chapter.downloaded = True
    chapter.file_path = str(file_path)
    chapter.page_count = len(images)
    chapter.file_size = file_path.stat().st_size
    chapter.downloaded_at = timezone.now()
    chapter.save(update_fields=[
        'downloaded', 'file_path', 'page_count', 'file_size', 'downloaded_at',
    ])
    return file_path


def download_volume(volume):
    chapters = sorted(volume.chapters.all(), key=lambda item: chapter_sort_key(item.chapter_number))
    if not chapters:
        raise ValueError(f'Volume {volume.volume_number} has no chapters')

    if volume.downloaded:
        volume.downloaded = False
        volume.save(update_fields=['downloaded'])

    chapter_paths = []
    for chapter in chapters:
        chapter_paths.append(str(download_chapter(chapter)))

    file_path = Path(ChapterPackager().create_volume_cbz(
        chapter_paths,
        volume.manga.title,
        volume.volume_number or 'complete',
    ))
    volume.downloaded = True
    volume.file_path = str(file_path)
    volume.file_size = file_path.stat().st_size
    volume.save(update_fields=['downloaded', 'file_path', 'file_size'])
    return file_path
