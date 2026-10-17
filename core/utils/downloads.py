from pathlib import Path

from django.utils import timezone

from core.scrapers import get_scraper

from .packager import ChapterPackager


def download_chapter(chapter):
    scraper = get_scraper(chapter.manga.source, chapter.manga.source_id)
    images = scraper.download_chapter_images(chapter.source_url)
    if not images:
        raise ValueError(f'No pages found for chapter {chapter.chapter_number}')

    file_path = Path(ChapterPackager().create_cbz(
        images,
        chapter.manga.title,
        chapter.chapter_number,
        chapter.volume or None,
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
    chapters = sorted(volume.chapters.all(), key=lambda item: item.chapter_number)
    if not chapters:
        raise ValueError(f'Volume {volume.volume_number} has no chapters')

    chapter_paths = []
    for chapter in chapters:
        if chapter.file_path and Path(chapter.file_path).is_file():
            chapter_paths.append(chapter.file_path)
        else:
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
