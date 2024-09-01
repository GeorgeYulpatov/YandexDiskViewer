from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('download/', views.download, name='download'),  # Ensure this line is present
    path('download_multiple/', views.download_multiple, name='download_multiple'),  # New URL for multiple downloads
]