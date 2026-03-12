# -*- coding: utf-8 -*-
"""
Simple redirect view for profile
"""
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

@login_required
def profile_redirect(request):
    """Redirect to portal dashboard"""
    return redirect('dashboard:home')
