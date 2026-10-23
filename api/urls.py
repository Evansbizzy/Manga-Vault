from django.urls import path
from . import views

urlpatterns = [
    path('sources/', views.SourcesView.as_view()),
    path('search/', views.SearchView.as_view()),
    path('import/', views.ImportMangaView.as_view()),
    path('manga/<int:pk>/', views.MangaDetailView.as_view()),
    path('manga/<int:pk>/chapters/', views.ChapterListView.as_view()),
    path('manga/<int:pk>/delete/', views.DeleteMangaView.as_view()),
    path('chapter/<int:chapter_id>/download/', views.DownloadChapterView.as_view()),
    path('chapter/<int:chapter_id>/file/', views.ChapterFileView.as_view()),
    path('chapter/<int:chapter_id>/pages/', views.ChapterPagesView.as_view()),
    path('chapter/<int:chapter_id>/progress/', views.ChapterProgressView.as_view()),
    path('download/chapters/', views.DownloadChaptersView.as_view()),
    path('download/volume/<int:volume_id>/', views.DownloadVolumeView.as_view()),
    path('volume/<int:volume_id>/file/', views.VolumeFileView.as_view()),
    path('task/<int:task_id>/', views.TaskStatusView.as_view()),
    path('library/', views.LibraryView.as_view()),
    path('proxy-image/', views.ImageProxyView.as_view()),
]
