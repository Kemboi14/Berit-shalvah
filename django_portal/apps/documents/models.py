# -*- coding: utf-8 -*-
"""
Document management models
"""
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class DocumentCategory(models.Model):
    """Document categories for organization"""
    name = models.CharField(_('Category Name'), max_length=100, unique=True)
    description = models.TextField(_('Description'), blank=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('Document Category')
        verbose_name_plural = _('Document Categories')
        ordering = ['name']
    
    def __str__(self):
        return self.name


class UploadedDocument(models.Model):
    """Generic uploaded document model"""
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='uploaded_documents',
        verbose_name=_('User')
    )
    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Category')
    )
    title = models.CharField(_('Title'), max_length=200)
    description = models.TextField(_('Description'), blank=True)
    file = models.FileField(_('File'), upload_to='documents/%Y/%m/')
    filename = models.CharField(_('Original Filename'), max_length=255)
    file_size = models.PositiveIntegerField(_('File Size'), help_text=_('File size in bytes'))
    mime_type = models.CharField(_('MIME Type'), max_length=100, blank=True)
    uploaded_at = models.DateTimeField(_('Uploaded At'), auto_now_add=True)
    
    # Sharing and permissions
    is_public = models.BooleanField(_('Public'), default=False, help_text=_('Make document accessible to staff'))
    shared_with = models.ManyToManyField(
        User,
        blank=True,
        related_name='shared_documents',
        verbose_name=_('Shared With')
    )
    
    # Tags for better organization
    tags = models.CharField(_('Tags'), max_length=500, blank=True, help_text=_('Comma-separated tags'))
    
    class Meta:
        verbose_name = _('Uploaded Document')
        verbose_name_plural = _('Uploaded Documents')
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.title}"
    
    def get_file_size_mb(self):
        """Get file size in MB"""
        return round(self.file_size / (1024 * 1024), 2)
    
    def get_tags_list(self):
        """Get tags as a list"""
        if self.tags:
            return [tag.strip() for tag in self.tags.split(',')]
        return []
    
    def set_tags_list(self, tags_list):
        """Set tags from a list"""
        self.tags = ', '.join(tags_list)
