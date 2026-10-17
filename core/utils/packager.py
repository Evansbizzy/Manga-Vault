import zipfile
import os
from pathlib import Path
from typing import List
from django.conf import settings


class ChapterPackager:
    """Package chapter images into downloadable formats"""

    def __init__(self):
        self.output_dir = Path(settings.DOWNLOADS_DIR)
        self.output_dir.mkdir(exist_ok=True)

    def create_cbz(self, images: List[bytes], manga_title: str,
                    chapter_num: str, volume: str = None) -> str:
        """
        Create CBZ (Comic Book ZIP) — standard manga format.
        Downloads ALL pages at once, then packages.
        """
        safe_title = self._safe_filename(manga_title)

        safe_chapter = self._safe_filename(str(chapter_num)) or 'unknown'
        if volume:
            safe_volume = self._safe_filename(str(volume)) or 'complete'
            filename = f"{safe_title}_Vol{safe_volume}_Ch{safe_chapter}.cbz"
        else:
            filename = f"{safe_title}_Ch{safe_chapter}.cbz"

        output_path = self.output_dir / filename

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, img_data in enumerate(images):
                ext = self._get_extension(img_data)
                arcname = f"{i+1:03d}.{ext}"
                zf.writestr(arcname, img_data)

        return str(output_path)

    def create_volume_cbz(self, chapter_files: List[str], manga_title: str,
                           volume_num: str) -> str:
        """
        Combine multiple chapters into a single volume CBZ.
        """
        safe_title = self._safe_filename(manga_title)
        safe_volume = self._safe_filename(str(volume_num)) or 'complete'
        filename = f"{safe_title}_Volume_{safe_volume}.cbz"
        output_path = self.output_dir / filename

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            page_num = 1
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

        return str(output_path)

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
