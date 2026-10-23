import os
import re

from django.db import models
from django.conf import settings


def chapter_sort_key(value: str):
    """Sort chapter labels naturally instead of lexicographically."""
    if value is None:
        return (1, "")

    text = str(value).strip()
    match = re.match(r"^(\d+(?:\.\d+)?)", text)
    if match:
        return (0, float(match.group(1)))
    return (1, text.lower())

class Manga(models.Model):
    title = models.CharField(max_length=500)
    alt_titles = models.JSONField(default=list, blank=True)
    author = models.CharField(max_length=200, blank=True)
    artist = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    cover_url = models.URLField(blank=True)
    cover_image = models.ImageField(upload_to='covers/', blank=True, null=True)
    status = models.CharField(max_length=50, blank=True)  # ongoing, completed, etc.
    source = models.CharField(max_length=100)  # mangadex, etc.
    source_id = models.CharField(max_length=1000)
    content_type = models.CharField(max_length=50, default='manga')  # manga, manhwa, webtoon
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Manga"
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['source', 'source_id'], name='unique_manga_source_id')
        ]
    
    def __str__(self):
        return self.title
    
    @property
    def downloaded_chapters_count(self):
        return self.chapters.filter(downloaded=True).count()
    
    @property
    def total_chapters_count(self):
        return self.chapters.count()

class Chapter(models.Model):
    manga = models.ForeignKey(Manga, on_delete=models.CASCADE, related_name='chapters')
    chapter_number = models.CharField(max_length=50)
    title = models.CharField(max_length=500, blank=True)
    volume = models.CharField(max_length=50, blank=True)
    source_url = models.CharField(max_length=1000)
    language = models.CharField(max_length=10, default='en')
    page_count = models.IntegerField(default=0)
    downloaded = models.BooleanField(default=False)
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.BigIntegerField(default=0)  # in bytes
    downloaded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['manga_id', 'chapter_number']
        unique_together = ['manga', 'chapter_number', 'language']
    
    def __str__(self):
        return f"{self.manga.title} - Ch.{self.chapter_number}"
    
    @property
    def filename(self):
        if self.file_path:
            return os.path.basename(self.file_path)
        return None

class Volume(models.Model):
    manga = models.ForeignKey(Manga, on_delete=models.CASCADE, related_name='volumes')
    volume_number = models.CharField(max_length=50)
    chapters = models.ManyToManyField(Chapter, related_name='volumes')
    downloaded = models.BooleanField(default=False)
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['volume_number']
        unique_together = ['manga', 'volume_number']
    
    def __str__(self):
        return f"{self.manga.title} - Vol.{self.volume_number}"

class DownloadTask(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('downloading', 'Downloading'),
        ('packaging', 'Packaging'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    manga = models.ForeignKey(Manga, on_delete=models.CASCADE, related_name='tasks')
    chapters = models.ManyToManyField(Chapter, blank=True)
    volumes = models.ManyToManyField(Volume, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)  # 0-100
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Task {self.id} - {self.status}"


class ReadingProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='manga_reading_progress')
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='reading_progress')
    current_page = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'chapter'], name='unique_user_chapter_progress'),
        ]
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user} - {self.chapter}"
