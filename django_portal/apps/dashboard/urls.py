# -*- coding: utf-8 -*-
"""
URL configuration for dashboard app
"""
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Main dashboard (routes based on user type)
    path('', views.DashboardView.as_view(), name='home'),
    
    # Specific dashboard views
    path('client/', views.client_dashboard_view, name='client'),
    path('staff/', views.staff_dashboard_view, name='staff'),
    path('admin/', views.admin_dashboard_view, name='admin'),
    
    # AJAX endpoints
    path('stats/', views.dashboard_stats_view, name='stats'),
]
