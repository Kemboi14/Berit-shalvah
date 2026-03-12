#!/usr/bin/env python
import sys
import os
sys.path.append('/home/nick/berit-shalvah/django_portal')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import django
django.setup()

from apps.accounts.models import User

# Check existing users
users = User.objects.all()
print(f'Found {users.count()} users:')

for u in users:
    print(f'  - Username: {u.username}')
    print(f'    Email: {u.email}')
    print(f'    Superuser: {u.is_superuser}')
    print(f'    Staff: {u.is_staff}')
    print('---')

# Try to find or create admin user
try:
    admin_user = User.objects.get(username='admin')
    print('Found existing admin user')
    # Reset password
    admin_user.set_password('admin123')
    admin_user.is_superuser = True
    admin_user.is_staff = True
    admin_user.save()
    print('Password reset successfully!')
    print('Username: admin')
    print('Password: admin123')
except User.DoesNotExist:
    print('Admin user not found, creating new one...')
    admin_user = User.objects.create_superuser('admin', 'admin@beritshalvah.com', 'admin123')
    print('Superuser created successfully!')
    print('Username: admin')
    print('Password: admin123')
except Exception as e:
    print(f'Error: {e}')

# Also try to create a test user with email login
try:
    test_user = User.objects.get(email='nick@beritshalvah.com')
    print('Found existing test user')
    test_user.set_password('test123')
    test_user.save()
    print('Test user password reset!')
    print('Email: nick@beritshalvah.com')
    print('Password: test123')
except User.DoesNotExist:
    print('Creating test user...')
    test_user = User.objects.create_user('nick', 'nick@beritshalvah.com', 'test123')
    test_user.is_staff = True
    test_user.save()
    print('Test user created!')
    print('Email: nick@beritshalvah.com')
    print('Password: test123')
except Exception as e:
    print(f'Error creating test user: {e}')

print('\nLogin Options:')
print('1. Username: admin, Password: admin123')
print('2. Email: nick@beritshalvah.com, Password: test123')
