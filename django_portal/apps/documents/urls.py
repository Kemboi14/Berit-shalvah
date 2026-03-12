# -*- coding: utf-8 -*-
"""
URL configuration for documents app
"""
from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    # Document management
    path('', views.document_list_view, name='list'),
    path('upload/', views.DocumentUploadView.as_view(), name='upload'),
    path('<int:pk>/edit/', views.DocumentUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', views.DocumentDeleteView.as_view(), name='delete'),
    path('<int:pk>/download/', views.document_download_view, name='download'),
    path('<int:pk>/share/', views.document_share_view, name='share'),
    
    # Category management (admin/staff only)
    path('categories/', views.category_management_view, name='categories'),
    path('categories/<int:category_id>/delete/', views.delete_category_view, name='delete_category'),
]
