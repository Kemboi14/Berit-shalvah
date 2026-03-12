# -*- coding: utf-8 -*-
"""
Views for document management
"""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q

from .models import UploadedDocument, DocumentCategory
from .forms import UploadedDocumentForm, DocumentCategoryForm


@login_required
def document_list_view(request):
    """List user's documents"""
    documents = UploadedDocument.objects.filter(
        Q(user=request.user) | Q(shared_with=request.user) | Q(is_public=True)
    ).distinct().order_by('-uploaded_at')
    
    # Filter by category
    category_id = request.GET.get('category')
    if category_id:
        documents = documents.filter(category_id=category_id)
    
    # Search
    search_query = request.GET.get('search')
    if search_query:
        documents = documents.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(tags__icontains=search_query)
        )
    
    categories = DocumentCategory.objects.all()
    
    context = {
        'documents': documents,
        'categories': categories,
        'selected_category': category_id,
        'search_query': search_query,
    }
    
    return render(request, 'berit/documents/list.html', context)


class DocumentUploadView(LoginRequiredMixin, CreateView):
    """Upload new document"""
    model = UploadedDocument
    form_class = UploadedDocumentForm
    template_name = 'berit/documents/upload.html'
    success_url = reverse_lazy('documents:list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.filename = self.request.FILES['file'].name
        form.instance.file_size = self.request.FILES['file'].size
        form.instance.mime_type = self.request.FILES['file'].content_type
        
        # Validate file size
        if form.instance.file_size > settings.MAX_UPLOAD_SIZE:
            messages.error(
                self.request, 
                f'File size exceeds maximum limit of {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB'
            )
            return self.form_invalid(form)
        
        messages.success(self.request, 'Document uploaded successfully!')
        return super().form_valid(form)


class DocumentUpdateView(LoginRequiredMixin, UpdateView):
    """Update document details"""
    model = UploadedDocument
    form_class = UploadedDocumentForm
    template_name = 'berit/documents/edit.html'
    success_url = reverse_lazy('documents:list')
    
    def get_queryset(self):
        return UploadedDocument.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, 'Document updated successfully!')
        return super().form_valid(form)


class DocumentDeleteView(LoginRequiredMixin, DeleteView):
    """Delete document"""
    model = UploadedDocument
    template_name = 'berit/documents/delete.html'
    success_url = reverse_lazy('documents:list')
    
    def get_queryset(self):
        return UploadedDocument.objects.filter(user=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        document = self.get_object()
        
        # Delete file from storage
        if document.file and default_storage.exists(document.file.name):
            default_storage.delete(document.file.name)
        
        messages.success(request, 'Document deleted successfully!')
        return super().delete(request, *args, **kwargs)


@login_required
def document_download_view(request, document_id):
    """Download document"""
    document = get_object_or_404(
        UploadedDocument, 
        id=document_id,
        user=request.user
    )
    
    if document.file and default_storage.exists(document.file.name):
        response = HttpResponse(
            default_storage.open(document.file.name, 'rb').read(),
            content_type=document.mime_type or 'application/octet-stream'
        )
        response['Content-Disposition'] = f'attachment; filename="{document.filename}"'
        response['Content-Length'] = document.file_size
        return response
    
    messages.error(request, 'File not found')
    return redirect('documents:list')


@login_required
def document_share_view(request, document_id):
    """Share document with other users"""
    document = get_object_or_404(
        UploadedDocument, 
        id=document_id,
        user=request.user
    )
    
    if request.method == 'POST':
        emails = request.POST.get('emails', '').split(',')
        make_public = request.POST.get('make_public') == 'on'
        
        # Share with users
        shared_count = 0
        for email in emails:
            email = email.strip()
            if email:
                try:
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    user = User.objects.get(email=email)
                    document.shared_with.add(user)
                    shared_count += 1
                except User.DoesNotExist:
                    messages.warning(request, f'User with email {email} not found')
        
        # Make public
        if make_public:
            document.is_public = True
            messages.success(request, 'Document is now public')
        else:
            document.is_public = False
        
        document.save()
        
        if shared_count > 0:
            messages.success(request, f'Document shared with {shared_count} users')
        
        return redirect('documents:list')
    
    return render(request, 'berit/documents/share.html', {'document': document})


@login_required
def category_management_view(request):
    """Manage document categories (admin/staff only)"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'You do not have permission to manage categories')
        return redirect('documents:list')
    
    if request.method == 'POST':
        form = DocumentCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category created successfully!')
            return redirect('documents:categories')
    else:
        form = DocumentCategoryForm()
    
    categories = DocumentCategory.objects.all()
    
    context = {
        'form': form,
        'categories': categories,
    }
    
    return render(request, 'berit/documents/categories.html', context)


@login_required
def delete_category_view(request, category_id):
    """Delete document category"""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'You do not have permission to delete categories')
        return redirect('documents:categories')
    
    category = get_object_or_404(DocumentCategory, id=category_id)
    
    # Check if category is in use
    if category.uploadeddocument_set.exists():
        messages.error(request, 'Cannot delete category that is in use')
        return redirect('documents:categories')
    
    category.delete()
    messages.success(request, 'Category deleted successfully!')
    
    return redirect('documents:categories')
