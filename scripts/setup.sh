#!/bin/bash

# Berit Shalvah Financial Services - Setup Script
# This script sets up the complete loan management system

set -e

echo "🚀 Setting up Berit Shalvah Financial Services Loan Management System..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p nginx/ssl
mkdir -p logs/odoo
mkdir -p logs/django
mkdir -p logs/nginx
mkdir -p backups

# Set proper permissions
chmod 755 nginx/ssl
chmod 755 logs
chmod 755 backups

# Copy environment file if it doesn't exist
if [ ! -f .env ]; then
    print_status "Creating environment file..."
    cp .env.example .env
    print_warning "Please edit .env file with your configuration before continuing."
    print_warning "Important: Update database passwords, email settings, and domain names."
    read -p "Press Enter to continue after editing .env file..."
fi

# Build and start services
print_status "Building and starting Docker containers..."
docker-compose down
docker-compose build
docker-compose up -d

# Wait for database to be ready
print_status "Waiting for database to be ready..."
sleep 30

# Check if database is ready
until docker-compose exec -T db pg_isready -U berit_user -d berit_odoo; do
    print_status "Waiting for PostgreSQL to be ready..."
    sleep 5
done

until docker-compose exec -T db pg_isready -U berit_user -d berit_portal; do
    print_status "Waiting for PostgreSQL to be ready..."
    sleep 5
done

# Create Odoo database and install module
print_status "Setting up Odoo database..."
docker-compose exec -T odoo odoo --addons-path=/opt/odoo/addons,/mnt/extra-addons -d berit_odoo --stop-after-init

# Install custom module
print_status "Installing Berit Loan module..."
docker-compose exec -T odoo odoo --addons-path=/opt/odoo/addons,/mnt/extra-addons -d berit_odoo -i berit_loan --stop-after-init

# Run Django migrations
print_status "Running Django migrations..."
docker-compose exec -T django python manage.py migrate

# Create Django superuser
print_status "Creating Django superuser..."
docker-compose exec -T django python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@beritshalvah.co.ke').exists():
    User.objects.create_superuser('admin@beritshalvah.co.ke', 'admin123', 'Admin', 'User', user_type='admin')
    print('Django superuser created: admin@beritshalvah.co.ke / admin123')
else:
    print('Django superuser already exists')
EOF

# Collect static files
print_status "Collecting Django static files..."
docker-compose exec -T django python manage.py collectstatic --noinput

# Load initial data
print_status "Loading initial data..."
docker-compose exec -T django python manage.py loaddata apps/loans/fixtures/initial_data.json 2>/dev/null || echo "No initial data fixtures found"

# Check service health
print_status "Checking service health..."

# Check Odoo
if curl -f http://localhost:8069/web &> /dev/null; then
    print_status "✅ Odoo is running on http://localhost:8069"
else
    print_error "❌ Odoo is not responding"
fi

# Check Django
if curl -f http://localhost:8000/portal/health &> /dev/null; then
    print_status "✅ Django portal is running on http://localhost:8000/portal"
else
    print_error "❌ Django portal is not responding"
fi

# Check Nginx
if curl -f http://localhost/health &> /dev/null; then
    print_status "✅ Nginx is running on http://localhost"
else
    print_error "❌ Nginx is not responding"
fi

# Display access information
echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📋 Access Information:"
echo "=================================="
echo "🏠 Main Site:           http://localhost"
echo "👤 Django Portal:      http://localhost:8000/portal"
echo "🏢 Odoo Backend:       http://localhost:8069"
echo "📊 Django Admin:       http://localhost:8000/admin"
echo ""
echo "🔑 Default Credentials:"
echo "=================================="
echo "Django Admin:         admin@beritshalvah.co.ke / admin123"
echo "Odoo Admin:           admin / admin (change in .env)"
echo ""
echo "📝 Next Steps:"
echo "=================================="
echo "1. Change default passwords"
echo "2. Configure email settings in .env"
echo "3. Set up SSL certificate for production"
echo "4. Configure domain names"
echo "5. Test the complete loan application flow"
echo ""
echo "📚 Documentation:"
echo "=================================="
echo "Check README.md for detailed documentation"
echo ""

# Show running containers
print_status "Running containers:"
docker-compose ps

echo ""
print_status "Setup script completed! 🚀"
