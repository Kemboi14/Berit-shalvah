# -*- coding: utf-8 -*-
"""
Views for user authentication and profile management
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, UpdateView

from .forms import (
    ClientProfileForm,
    CustomUserCreationForm,
    UserDocumentForm,
    UserProfileUpdateForm,
)
from .models import ClientProfile, User, UserDocument, VerificationRequest


def signup_view(request):
    """User registration view"""
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()

            # Create client profile
            ClientProfile.objects.create(user=user)

            # Send verification email
            # TODO: Implement email verification

            messages.success(
                request,
                "Account created successfully! Please check your email to verify your account.",
            )
            return redirect("accounts:login")
    else:
        form = CustomUserCreationForm()

    return render(request, "accounts/signup.html", {"form": form})


@login_required
def profile_view(request):
    """User profile view"""
    user = request.user
    profile = user.get_client_profile()

    # Get completion percentage
    completion_percentage = 0
    if profile:
        completion_percentage = profile.get_completion_percentage()

    # Get recent documents
    recent_documents = user.documents.order_by("-uploaded_at")[:5]

    # Get verification requests
    verification_requests = user.verification_requests.order_by("-submitted_at")[:5]

    context = {
        "profile": profile,
        "completion_percentage": completion_percentage,
        "recent_documents": recent_documents,
        "verification_requests": verification_requests,
    }

    return render(request, "accounts/profile.html", context)


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Update user profile"""

    model = User
    form_class = UserProfileUpdateForm
    template_name = "accounts/profile_edit.html"
    success_url = reverse_lazy("accounts:profile")

    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.user_type == User.UserType.CLIENT:
            try:
                context["profile_form"] = ClientProfileForm(
                    instance=self.request.user.client_profile
                )
            except ClientProfile.DoesNotExist:
                context["profile_form"] = ClientProfileForm()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        # Handle client profile form
        if self.request.user.user_type == User.UserType.CLIENT:
            profile_form = ClientProfileForm(
                self.request.POST, instance=self.request.user.get_client_profile()
            )
            if profile_form.is_valid():
                profile_form.save()

        messages.success(self.request, "Profile updated successfully!")
        return response


@login_required
def documents_view(request):
    """View uploaded documents"""
    documents = request.user.documents.order_by("-uploaded_at")

    return render(
        request,
        "accounts/documents.html",
        {
            "documents": documents,
        },
    )


@login_required
@require_POST
def upload_document_view(request):
    """Upload document view"""
    form = UserDocumentForm(request.POST, request.FILES)

    if form.is_valid():
        document = form.save(commit=False)
        document.user = request.user
        document.filename = request.FILES["file"].name
        document.file_size = request.FILES["file"].size
        document.mime_type = request.FILES["file"].content_type

        # Validate file size
        if document.file_size > settings.MAX_UPLOAD_SIZE:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"File size exceeds maximum limit of {settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB",
                }
            )

        # Validate file type
        allowed_types = getattr(settings, "ALLOWED_DOCUMENT_TYPES", [])
        file_extension = document.filename.split(".")[-1].lower()
        if file_extension not in allowed_types:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"File type not allowed. Allowed types: {', '.join(allowed_types)}",
                }
            )

        document.save()

        return JsonResponse(
            {
                "success": True,
                "document": {
                    "id": document.id,
                    "document_type": document.get_document_type_display(),
                    "filename": document.filename,
                    "uploaded_at": document.uploaded_at.strftime("%Y-%m-%d %H:%M"),
                    "is_verified": document.is_verified,
                    "file_size_mb": document.get_file_size_mb(),
                },
            }
        )

    return JsonResponse({"success": False, "error": "Invalid form data"})


@login_required
@require_POST
def delete_document_view(request, document_id):
    """Delete document view"""
    document = get_object_or_404(UserDocument, id=document_id, user=request.user)

    # Delete file from storage
    if document.file and default_storage.exists(document.file.name):
        default_storage.delete(document.file.name)

    document.delete()

    return JsonResponse({"success": True})


@login_required
def verification_requests_view(request):
    """View verification requests"""
    requests = request.user.verification_requests.order_by("-submitted_at")

    return render(
        request,
        "accounts/verification_requests.html",
        {
            "verification_requests": requests,
        },
    )


@login_required
@require_POST
def submit_verification_request(request):
    """Submit verification request"""
    request_type = request.POST.get("request_type")
    notes = request.POST.get("notes", "")

    # Check if there's already a pending request of this type
    existing_request = VerificationRequest.objects.filter(
        user=request.user,
        request_type=request_type,
        status=VerificationRequest.Status.PENDING,
    ).first()

    if existing_request:
        return JsonResponse(
            {
                "success": False,
                "error": "You already have a pending verification request of this type.",
            }
        )

    # Create new verification request
    verification_request = VerificationRequest.objects.create(
        user=request.user, request_type=request_type, notes=notes
    )

    # TODO: Send notification to admin

    return JsonResponse(
        {
            "success": True,
            "request_id": verification_request.id,
            "message": "Verification request submitted successfully!",
        }
    )


@login_required
def dashboard_view(request):
    """User dashboard"""
    user = request.user

    if user.user_type == User.UserType.CLIENT:
        # Get client-specific data
        profile = user.get_client_profile()
        recent_applications = user.loan_applications.order_by("-created_at")[:5]

        context = {
            "profile": profile,
            "recent_applications": recent_applications,
        }
        return render(request, "dashboard.html", context)
    else:
        # Staff dashboard
        context = {
            "user": user,
        }
        return render(request, "dashboard.html", context)


class HomeView(TemplateView):
    """Home page view"""

    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.user.is_authenticated:
            # Redirect authenticated users to their dashboard
            context["show_dashboard_link"] = True
        else:
            context["show_login_signup"] = True

        return context


@csrf_exempt
def check_email_view(request):
    """Check if email is available (AJAX)"""
    if request.method == "POST":
        email = request.POST.get("email", "")

        if User.objects.filter(email=email).exists():
            return JsonResponse({"available": False})
        else:
            return JsonResponse({"available": True})

    return JsonResponse({"error": "Invalid request method"})


@csrf_exempt
def check_national_id_view(request):
    """Check if national ID is available (AJAX)"""
    if request.method == "POST":
        national_id = request.POST.get("national_id", "")

        if User.objects.filter(national_id=national_id).exists():
            return JsonResponse({"available": False})
        else:
            return JsonResponse({"available": True})

    return JsonResponse({"error": "Invalid request method"})


@login_required
def settings_view(request):
    """User settings view"""
    return render(request, "accounts/settings.html")


@login_required
@require_POST
def change_password_view(request):
    """Change password view"""
    current_password = request.POST.get("current_password")
    new_password = request.POST.get("new_password")
    confirm_password = request.POST.get("confirm_password")

    # Validate inputs
    if not current_password or not new_password or not confirm_password:
        return JsonResponse(
            {"success": False, "error": "All password fields are required."}
        )

    if new_password != confirm_password:
        return JsonResponse({"success": False, "error": "New passwords do not match."})

    if len(new_password) < 8:
        return JsonResponse(
            {"success": False, "error": "Password must be at least 8 characters long."}
        )

    # Check current password
    if not request.user.check_password(current_password):
        return JsonResponse(
            {"success": False, "error": "Current password is incorrect."}
        )

    # Change password
    request.user.set_password(new_password)
    request.user.save()

    # Update session to prevent logout
    update_session_auth_hash(request, request.user)

    return JsonResponse({"success": True, "message": "Password changed successfully!"})


@login_required
def export_data_view(request):
    """Export user data view"""
    import json

    from django.http import HttpResponse

    # Collect user data
    user_data = {
        "personal_info": {
            "full_name": request.user.full_name,
            "email": request.user.email,
            "phone": str(request.user.phone) if request.user.phone else None,
            "national_id": request.user.national_id,
            "date_joined": request.user.date_joined.strftime("%Y-%m-%d"),
        },
        "documents": [
            {
                "type": doc.document_type,
                "filename": doc.filename,
                "uploaded_at": doc.uploaded_at.strftime("%Y-%m-%d"),
                "is_verified": doc.is_verified,
            }
            for doc in request.user.documents.all()
        ],
        "loan_applications": [
            {
                "reference": app.reference_number,
                "amount": float(app.loan_amount),
                "duration": app.loan_duration,
                "status": app.status,
                "created_at": app.created_at.strftime("%Y-%m-%d"),
            }
            for app in request.user.loan_applications.all()
        ],
    }

    # Create JSON response
    data = json.dumps(user_data, indent=2)
    response = HttpResponse(data, content_type="application/json")
    response["Content-Disposition"] = (
        f'attachment; filename="{request.user.email}_data.json"'
    )

    return response


@login_required
@require_POST
def deactivate_account_view(request):
    """Deactivate account view"""
    # Mark user as inactive (soft delete)
    request.user.is_active = False
    request.user.save()

    # Log out the user
    from django.contrib.auth import logout

    logout(request)

    return JsonResponse(
        {
            "success": True,
            "message": "Your account has been deactivated. You can reactivate it by contacting support.",
        }
    )


@login_required
@require_POST
def delete_account_view(request):
    """Delete account view (permanent deletion)"""
    from django.contrib.auth import logout

    # Store user info for logging before deletion
    user_email = request.user.email

    # Delete all associated data
    request.user.documents.all().delete()  # Delete documents
    request.user.verification_requests.all().delete()  # Delete verification requests
    request.user.loan_applications.all().delete()  # Delete loan applications

    # Delete the user (this will cascade delete related models due to ForeignKey relationships)
    request.user.delete()

    # Log out (though user is deleted, this ensures session cleanup)
    logout(request)

    return JsonResponse(
        {
            "success": True,
            "message": f"Account {user_email} has been permanently deleted. All data has been removed.",
        }
    )
