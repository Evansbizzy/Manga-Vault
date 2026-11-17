import zipfile
import os
import tempfile
from pathlib import Path
from typing import List
from django.conf import settings


class ChapterPackager:
    """Package chapter images into downloadable formats"""

    def __init__(self):
        self.output_dir = Path(settings.DOWNLOADS_DIR)
        self.output_dir.mkdir(exist_ok=True)

    def create_cbz(self, images: List[bytes], manga_title: str,
                    chapter_num: str, volume: str = None, language: str = 'en') -> str:
        """
        Create CBZ (Comic Book ZIP) — standard manga format.
        Downloads ALL pages at once, then packages.
        """
        if not images:
            raise ValueError('Cannot create a chapter archive without page images')

        filename = self.chapter_filename(manga_title, chapter_num, volume, language)
        output_path = self.output_dir / filename
        temporary_path = self._temporary_path(output_path)
        try:
            with zipfile.ZipFile(temporary_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i, img_data in enumerate(images):
                    ext = self._get_extension(img_data)
                    arcname = f"{i+1:03d}.{ext}"
                    zf.writestr(arcname, img_data)
            os.replace(temporary_path, output_path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

        return str(output_path)

    @classmethod
    def chapter_filename(cls, manga_title: str, chapter_num: str,
                         volume: str = None, language: str = 'en') -> str:
        safe_title = cls._safe_filename(manga_title)
        safe_chapter = cls._safe_filename(str(chapter_num)) or 'unknown'
        safe_language = cls._safe_filename(str(language or 'en')).lower() or 'en'
        if volume:
            safe_volume = cls._safe_filename(str(volume)) or 'complete'
            return f"{safe_title}_Vol{safe_volume}_Ch{safe_chapter}_{safe_language}.cbz"
        return f"{safe_title}_Ch{safe_chapter}_{safe_language}.cbz"

    def create_volume_cbz(self, chapter_files: List[str], manga_title: str,
                           volume_num: str) -> str:
        """
        Combine multiple chapters into a single volume CBZ.
        """
        safe_title = self._safe_filename(manga_title)
        safe_volume = self._safe_filename(str(volume_num)) or 'complete'
        filename = f"{safe_title}_Volume_{safe_volume}.cbz"
        output_path = self.output_dir / filename
        temporary_path = self._temporary_path(output_path)
        page_num = 1
        try:
            with zipfile.ZipFile(temporary_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for chapter_file in chapter_files:
                    if not os.path.exists(chapter_file):
                        continue
                    with zipfile.ZipFile(chapter_file, 'r') as ch_zf:
                        for name in sorted(ch_zf.namelist()):
                            img_data = ch_zf.read(name)
                            ext = self._get_extension(img_data)
                            arcname = f"{page_num:04d}.{ext}"
                            zf.writestr(arcname, img_data)
                            page_num += 1
            if page_num == 1:
                raise ValueError('Cannot create a volume archive without downloaded pages')
            os.replace(temporary_path, output_path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

        return str(output_path)

    @staticmethod
    def _temporary_path(output_path: Path) -> str:
        handle = tempfile.NamedTemporaryFile(
            prefix=f'.{output_path.stem}-', suffix='.tmp',
            dir=output_path.parent, delete=False,
        )
        handle.close()
        return handle.name

    @staticmethod
    def _safe_filename(title: str) -> str:
        safe = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        return safe.replace(' ', '_')[:100]

    @staticmethod
    def _get_extension(image_data: bytes) -> str:
        """Detect image format from magic bytes"""
        if not image_data or len(image_data) < 12:
            return 'jpg'
        if image_data[:2] == b'\xff\xd8':
            return 'jpg'
        if image_data[:4] == b'\x89PNG':
            return 'png'
        if image_data[:3] == b'GIF':
            return 'gif'
        if image_data[:2] == b'BM':
            return 'bmp'
        # WebP: starts with RIFF....WEBP
        if image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
            return 'webp'
        # AVIF: ftyp box containing 'avif'
        if image_data[4:8] == b'ftyp' and b'avif' in image_data[8:32]:
            return 'avif'
        # JXL (JPEG XL)
        if image_data[:2] == b'\xff\x0a':
            return 'jxl'
        return 'jpg'
