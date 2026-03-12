# -*- coding: utf-8 -*-
"""
Enhanced authentication views with phone number support
"""

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView

from .auth_forms import CustomAuthenticationForm, EmailLoginForm, PhoneLoginForm
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


class CustomLoginView(LoginView):
    """Custom login view that accepts email/username and phone"""

    form_class = CustomAuthenticationForm
    template_name = "accounts/login.html"

    def form_valid(self, form):
        # Try to authenticate with email/username first
        login_field = form.cleaned_data.get("login_field")
        password = form.cleaned_data.get("password")

        # Try authentication with different fields
        user = None

        # Try with email
        try:
            user_obj = User.objects.get(email=login_field)
            user = authenticate(
                self.request, username=user_obj.username, password=password
            )
        except User.DoesNotExist:
            pass

        # Try with phone if email didn't work
        if not user:
            try:
                user_obj = User.objects.get(phone=login_field)
                user = authenticate(
                    self.request, username=user_obj.username, password=password
                )
            except User.DoesNotExist:
                pass

        # Try with username if neither email nor phone worked
        if not user:
            user = authenticate(self.request, username=login_field, password=password)

        if user:
            login(self.request, user)
            messages.success(self.request, _("Login successful!"))
            return redirect(self.get_success_url())
        else:
            form.add_error(None, _("Invalid login credentials."))
            return self.form_invalid(form)


class PhoneLoginView(LoginView):
    """Phone number based login view"""

    form_class = PhoneLoginForm
    template_name = "accounts/phone_login.html"

    def form_valid(self, form):
        phone = form.cleaned_data.get("phone")
        password = form.cleaned_data.get("password")

        try:
            user_obj = User.objects.get(phone=phone)
            user = authenticate(
                self.request, username=user_obj.username, password=password
            )
            if user:
                login(self.request, user)
                messages.success(self.request, _("Login successful!"))
                return redirect(self.get_success_url())
            else:
                form.add_error("password", _("Invalid password."))
        except User.DoesNotExist:
            form.add_error("phone", _("No account found with this phone number."))

        return self.form_invalid(form)


class EmailLoginView(LoginView):
    """Email based login view"""

    form_class = EmailLoginForm
    template_name = "accounts/email_login.html"

    def form_valid(self, form):
        email = form.cleaned_data.get("email")
        password = form.cleaned_data.get("password")

        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(
                self.request, username=user_obj.username, password=password
            )
            if user:
                login(self.request, user)
                messages.success(self.request, _("Login successful!"))
                return redirect(self.get_success_url())
            else:
                form.add_error("password", _("Invalid password."))
        except User.DoesNotExist:
            form.add_error("email", _("No account found with this email address."))

        return self.form_invalid(form)


class CustomSignupView(CreateView):
    """Custom signup view with phone number requirement"""

    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("accounts:login")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request, _("Account created successfully! Please log in.")
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

        user = None

        # Try authentication with different fields
        # Try with email
        try:
            user_obj = User.objects.get(email=login_field)
            user = authenticate(request, username=user_obj.username, password=password)
        except User.DoesNotExist:
            pass

        # Try with phone if email didn't work
        if not user:
            try:
                user_obj = User.objects.get(phone=login_field)
                user = authenticate(
                    request, username=user_obj.username, password=password
                )
            except User.DoesNotExist:
                pass

        # Try with username if neither email nor phone worked
        if not user:
            user = authenticate(request, username=login_field, password=password)

        if user:
            login(request, user)
            return JsonResponse(
                {
                    "success": True,
                    "message": _("Login successful!"),
                    "redirect_url": request.GET.get("next", reverse_lazy("dashboard")),
                }
            )
        else:
            return JsonResponse(
                {"success": False, "message": _("Invalid login credentials.")}
            )

    return JsonResponse({"success": False, "message": _("Invalid request method.")})


def check_user_exists(request):
    """Check if user exists by email or phone"""
    if request.method == "GET":
        identifier = request.GET.get("identifier")
        user_type = request.GET.get("type", "email")  # email or phone

        if user_type == "email":
            exists = User.objects.filter(email=identifier).exists()
        elif user_type == "phone":
            exists = User.objects.filter(phone=identifier).exists()
        else:
            exists = User.objects.filter(
                models.Q(email=identifier)
                | models.Q(phone=identifier)
                | models.Q(username=identifier)
            ).exists()

        return JsonResponse({"exists": exists})

    return JsonResponse({"exists": False})
