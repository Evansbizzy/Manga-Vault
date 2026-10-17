from django.contrib import admin
from .models import Manga, Chapter, Volume, DownloadTask

@admin.register(Manga)
class MangaAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'source', 'content_type', 'created_at']
    list_filter = ['source', 'content_type', 'status']
    search_fields = ['title', 'author']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ['manga', 'chapter_number', 'volume', 'downloaded', 'downloaded_at']
    list_filter = ['downloaded', 'manga__source']
    search_fields = ['manga__title', 'chapter_number']

@admin.register(Volume)
class VolumeAdmin(admin.ModelAdmin):
    list_display = ['manga', 'volume_number', 'downloaded']
    filter_horizontal = ['chapters']

@admin.register(DownloadTask)
class DownloadTaskAdmin(admin.ModelAdmin):
    list_display = ['id', 'manga', 'status', 'progress', 'created_at']
    list_filter = ['status']
