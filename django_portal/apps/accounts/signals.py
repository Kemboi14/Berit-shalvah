# -*- coding: utf-8 -*-
"""
Signals for accounts app
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import ClientProfile, VerificationRequest

User = get_user_model()


@receiver(post_save, sender=User)
def create_client_profile(sender, instance, created, **kwargs):
    """Create client profile when user is created"""
    if created and instance.user_type == User.UserType.CLIENT:
        ClientProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_client_profile(sender, instance, **kwargs):
    """Save client profile when user is saved"""
    if instance.user_type == User.UserType.CLIENT:
        try:
            instance.client_profile.save()
        except ClientProfile.DoesNotExist:
            ClientProfile.objects.create(user=instance)
