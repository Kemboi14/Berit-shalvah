#!/usr/bin/env python
import sys
import os
sys.path.append('/home/nick/berit-shalvah/django_portal')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

import django
django.setup()

from apps.accounts.models import User

print("=== Creating Django Superuser ===")

# Create admin user without deleting existing users first
try:
    admin = User.objects.create_superuser(
        username='admin',
        email='admin@beritshalvah.com',
        password='admin123'
    )
    admin.phone = '+254712345678'
    admin.first_name = 'Admin'
    admin.last_name = 'User'
    admin.save()
    print('✓ Admin user created successfully!')
    print('  Username: admin')
    print('  Password: admin123')
    print('  Email: admin@beritshalvah.com')
    print('  Phone: +254712345678')
except Exception as e:
    print(f'✗ Admin user may already exist: {e}')
    # Try to get existing admin user
    try:
        admin = User.objects.get(username='admin')
        admin.set_password('admin123')
        admin.save()
        print('✓ Admin password reset successfully!')
    except:
        print('✗ Could not reset admin password')

# Create test user
try:
    test = User.objects.create_user(
        username='nick',
        email='nick@beritshalvah.com',
        password='test123'
    )
    test.phone = '+254723456789'
    test.first_name = 'Nick'
    test.last_name = 'Test'
    test.is_staff = True
    test.save()
    print('✓ Test user created successfully!')
    print('  Username: nick')
    print('  Password: test123')
    print('  Email: nick@beritshalvah.com')
    print('  Phone: +254723456789')
except Exception as e:
    print(f'✗ Test user may already exist: {e}')
    # Try to get existing test user
    try:
        test = User.objects.get(username='nick')
        test.set_password('test123')
        test.save()
        print('✓ Test user password reset successfully!')
    except:
        print('✗ Could not reset test password')

print("\n=== Login Credentials ===")
print("1. Username: admin, Password: admin123")
print("2. Username: nick, Password: test123")
print("3. Email: nick@beritshalvah.com, Password: test123")
print("4. Phone: +254723456789, Password: test123")

# Verify users were created
print("\n=== Verification ===")
users = User.objects.all()
print(f'Found {users.count()} users:')
for u in users:
    print(f'  - {u.username} ({u.email}) - Superuser: {u.is_superuser}')
