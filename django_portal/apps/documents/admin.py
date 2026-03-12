# -*- coding: utf-8 -*-
"""
Admin configuration for documents app
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import UploadedDocument, DocumentCategory


@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    """Document category admin"""
    list_display = ('name', 'description', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('name',)


@admin.register(UploadedDocument)
class UploadedDocumentAdmin(admin.ModelAdmin):
    """Uploaded document admin"""
    list_display = ('title', 'user', 'category', 'file_size', 'is_public', 'uploaded_at')
    list_filter = ('category', 'is_public', 'uploaded_at')
    search_fields = ('title', 'description', 'user__email', 'tags')
    readonly_fields = ('uploaded_at', 'file_size', 'mime_type')
    date_hierarchy = 'uploaded_at'
    
    fieldsets = (
        (_('Document Info'), {
            'fields': ('user', 'title', 'description', 'category')
        }),
        (_('File'), {
            'fields': ('file', 'filename', 'file_size', 'mime_type')
        }),
        (_('Sharing'), {
            'fields': ('is_public', 'shared_with')
        }),
        (_('Tags'), {
            'fields': ('tags',)
        }),
        (_('Timestamps'), {
            'fields': ('uploaded_at',)
        }),
    )
    
    filter_horizontal = ('shared_with',)
    
    def get_file_size_mb(self, obj):
        """Get file size in MB"""
        return f"{obj.file_size / (1024*1024):.2f} MB"
    get_file_size_mb.short_description = 'File Size'
    
    actions = ['make_public', 'make_private']
    
    def make_public(self, request, queryset):
        """Make selected documents public"""
        count = queryset.update(is_public=True)
        self.message_user(request, f'{count} documents made public.')
    make_public.short_description = 'Make selected documents public'
    
    def make_private(self, request, queryset):
        """Make selected documents private"""
        count = queryset.update(is_public=False)
        self.message_user(request, f'{count} documents made private.')
    make_private.short_description = 'Make selected documents private'
