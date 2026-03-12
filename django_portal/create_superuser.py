#!/usr/bin/env python
import sys
import os
sys.path.append('/home/nick/berit-shalvah/django_portal')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import django
django.setup()

from apps.accounts.models import User

try:
    user = User.objects.create_superuser('admin', 'admin@beritshalvah.com', 'admin123')
    print('Superuser created successfully!')
    print('Username: admin')
    print('Password: admin123')
    print('Email: admin@beritshalvah.com')
except Exception as e:
    print(f'Error: {e}')
    # Try to reset password
    try:
        user = User.objects.get(username='admin')
        user.set_password('admin123')
        user.save()
        print('Password reset successfully!')
        print('Username: admin')
        print('Password: admin123')
    except Exception as e2:
        print(f'User not found: {e2}')
        # List existing users
        try:
            users = User.objects.all()
            print(f'Found {users.count()} existing users:')
            for u in users[:5]:  # Show first 5 users
                print(f'  - {u.username} ({u.email})')
        except Exception as e3:
            print(f'Cannot list users: {e3}')
