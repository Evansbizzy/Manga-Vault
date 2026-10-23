from django.urls import path
from . import views

urlpatterns = [
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('', views.IndexView.as_view(), name='index'),
    path('search/', views.SearchPageView.as_view(), name='search'),
    path('library/', views.LibraryPageView.as_view(), name='library'),
    path('manga/<int:pk>/', views.MangaDetailPageView.as_view(), name='manga_detail'),
    path('reader/<int:chapter_id>/', views.ReaderPageView.as_view(), name='reader'),
    # File downloads — plain Django views, NO DRF
    path('download/chapter/<int:chapter_id>/', views.DownloadChapterFileView.as_view(), name='download_chapter'),
    path('download/volume/<int:volume_id>/', views.DownloadVolumeFileView.as_view(), name='download_volume'),
]
