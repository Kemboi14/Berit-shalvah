# -*- coding: utf-8 -*-
"""
Authentication views for Berit Shalvah
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import LoginView, LogoutView
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView

from .forms import CustomUserCreationForm
from .models import User


class CustomLogoutView(LogoutView):
    """Custom logout view with success message — accepts both GET and POST."""

    next_page = reverse_lazy("home")

    def get(self, request, *args, **kwargs):
        """Allow GET requests so plain <a href> logout links work."""
        logout(request)
        messages.success(request, _("You have been successfully logged out."))
        return redirect(self.next_page)

    def post(self, request, *args, **kwargs):
        messages.success(request, _("You have been successfully logged out."))
        return super().post(request, *args, **kwargs)


class UnifiedLoginView(LoginView):
    """
    Unified login view that handles email, phone, and username.
    The template has separate forms that all POST to this view.
    """

    template_name = "accounts/login.html"

    def post(self, request, *args, **kwargs):
        login_type = request.POST.get("login_type", "email")
        login_field = request.POST.get("login_field", "").strip()
        password = request.POST.get("password", "")

        user = None

        # Try authentication based on login type
        if login_type == "email":
            try:
                user_obj = User.objects.get(email__iexact=login_field)
                # Ensure username is synced to email (fix legacy blank usernames)
                if not user_obj.username:
                    user_obj.username = user_obj.email
                    user_obj.save(update_fields=["username"])
                user = authenticate(
                    request, username=user_obj.username, password=password
                )
            except User.DoesNotExist:
                pass

        elif login_type == "phone":
            try:
                user_obj = User.objects.get(phone=login_field)
                if not user_obj.username:
                    user_obj.username = user_obj.email
                    user_obj.save(update_fields=["username"])
                user = authenticate(
                    request, username=user_obj.username, password=password
                )
            except User.DoesNotExist:
                pass

        else:  # username
            user = authenticate(request, username=login_field, password=password)

        if user is not None:
            if not user.is_active:
                messages.error(
                    request,
                    _("Your account has been deactivated. Please contact support."),
                )
                return render(
                    request,
                    self.template_name,
                    {"login_field": login_field, "login_type": login_type},
                )
            login(request, user)
            messages.success(
                request,
                _("Login successful! Welcome back, {}.").format(
                    user.first_name or user.email
                ),
            )
            next_url = request.GET.get("next") or reverse_lazy("dashboard:home")
            return redirect(next_url)
        else:
            messages.error(request, _("Invalid email or password. Please try again."))
            return render(
                request,
                self.template_name,
                {"login_field": login_field, "login_type": login_type},
            )


class SignupView(CreateView):
    """Signup view - consolidated from duplicate implementations"""

    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        response = super().form_valid(form)

        # ClientProfile is created automatically by the post_save signal.
        # Use get_or_create as a safety net in case the signal didn't fire.
        from .models import ClientProfile

        ClientProfile.objects.get_or_create(user=self.object)

        messages.success(
            self.request,
            _("Account created successfully! You can now log in."),
        )
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)


def ajax_login(request):
    """AJAX login endpoint"""
    if request.method == "POST":
        login_field = request.POST.get("login_field")
        password = request.POST.get("password")
        login_type = request.POST.get("login_type", "email")

        user = None

        if login_type == "email":
            try:
                user_obj = User.objects.get(email=login_field)
                user = authenticate(
                    request, username=user_obj.username, password=password
                )
            except User.DoesNotExist:
                pass
        elif login_type == "phone":
            try:
                user_obj = User.objects.get(phone=login_field)
                user = authenticate(
                    request, username=user_obj.username, password=password
                )
            except User.DoesNotExist:
                pass
        else:
            user = authenticate(request, username=login_field, password=password)

        if user:
            if not user.is_active:
                return JsonResponse(
                    {
                        "success": False,
                        "message": _("Your account has been deactivated."),
                    }
                )
            login(request, user)
            return JsonResponse(
                {
                    "success": True,
                    "message": _("Login successful!"),
                    "redirect_url": str(
                        request.GET.get("next") or reverse_lazy("dashboard:home")
                    ),
                }
            )
        else:
            return JsonResponse(
                {"success": False, "message": _("Invalid email or password.")}
            )

    return JsonResponse({"success": False, "message": _("Invalid request method.")})


def check_user_exists(request):
    """Check if user exists by email or phone"""
    from django.db.models import Q

    if request.method == "GET":
        identifier = request.GET.get("identifier")
        user_type = request.GET.get("type", "email")

        if user_type == "email":
            exists = User.objects.filter(email=identifier).exists()
        elif user_type == "phone":
            exists = User.objects.filter(phone=identifier).exists()
        else:
            exists = User.objects.filter(
                Q(email=identifier) | Q(phone=identifier) | Q(username=identifier)
            ).exists()

        return JsonResponse({"exists": exists})

    return JsonResponse({"exists": False})
