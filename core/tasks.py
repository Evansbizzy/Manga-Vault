import logging
import threading
import traceback

from celery import shared_task
from django.utils import timezone

from .models import Chapter, DownloadTask, Volume, chapter_sort_key
from .utils.downloads import download_chapter, download_volume

logger = logging.getLogger(__name__)


def _download_chapters(task_id: int):
    """Download and package every chapter attached to a task."""
    task = DownloadTask.objects.get(id=task_id)
    task.status = 'downloading'
    task.save()

    try:
        chapters = sorted(
            task.chapters.all(),
            key=lambda ch: chapter_sort_key(ch.chapter_number),
        )
        total = len(chapters)
        success_count = 0
        failures = []

        for idx, chapter in enumerate(chapters):
            slice_start = int((idx / max(total, 1)) * 90)
            slice_end = int(((idx + 1) / max(total, 1)) * 90)

            task.progress = max(slice_start, 5)
            task.status = 'downloading'
            task.message = f"Preparing Ch. {chapter.chapter_number} ({idx+1}/{total})…"
            task.save()

            try:
                file_path = download_chapter(chapter)
                if file_path:
                    success_count += 1
                    task.progress = slice_end
                    task.message = f"Ch. {chapter.chapter_number} downloaded"
                    task.save()
                else:
                    logger.warning("No pages for chapter %s", chapter.chapter_number)
                    failures.append(chapter.chapter_number)
            except Exception as exc:
                logger.warning("Failed to prepare ch %s: %s", chapter.chapter_number, exc)
                failures.append(chapter.chapter_number)

            task.progress = slice_end
            task.save()

        task.status = 'failed' if not success_count else 'completed'
        task.progress = 100
        task.message = f"{success_count}/{total} chapters ready for download"
        if failures:
            task.message += f"; failed chapters: {', '.join(failures[:20])}"
            if len(failures) > 20:
                task.message += f" and {len(failures) - 20} more"
        task.completed_at = timezone.now()
        task.save()

    except Exception as e:
        logger.error("Task %s failed: %s", task_id, traceback.format_exc())
        task.status = 'failed'
        task.message = str(e)
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'message', 'completed_at'])


def _download_volume(task_id: int, volume_id: int):
    """Download and package all chapters in a volume."""
    task = DownloadTask.objects.get(id=task_id)
    volume = Volume.objects.get(id=volume_id)
    task.status = 'downloading'
    task.save()

    try:
        chapters = sorted(
            volume.chapters.all(),
            key=lambda ch: chapter_sort_key(ch.chapter_number),
        )
        total = len(chapters)

        task.progress = 5
        task.message = f"Preparing volume {volume.volume_number} ({total} chapters)"
        task.save(update_fields=['progress', 'message'])
        download_volume(volume)

        task.status = 'completed'
        task.progress = 100
        task.message = f"Volume {volume.volume_number} ready ({total} chapters)"
        task.completed_at = timezone.now()
        task.save()

    except Exception as e:
        logger.error("Volume task %s failed: %s", task_id, traceback.format_exc())
        task.status = 'failed'
        task.message = str(e)
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'message', 'completed_at'])


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------

@shared_task
def download_chapters_task(task_id: int):
    return _download_chapters(task_id)


@shared_task
def download_volume_task(task_id: int, volume_id: int):
    return _download_volume(task_id, volume_id)


# ---------------------------------------------------------------------------
# Synchronous fallback (runs in a background thread so Django doesn't block)
# ---------------------------------------------------------------------------

def run_download_chapters(task_id: int):
    t = threading.Thread(target=_download_chapters, args=(task_id,), daemon=True)
    t.start()


def run_download_volume(task_id: int, volume_id: int):
    t = threading.Thread(target=_download_volume, args=(task_id, volume_id), daemon=True)
    t.start()
