#!/bin/bash

# Berit Shalvah Financial Services - Local Development Setup Script
# This script sets up the system for local development without Docker

set -e

echo "🚀 Setting up Berit Shalvah Financial Services (Local Development)..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_header() {
    echo -e "${BLUE}$1${NC}"
}

# Check if we're in the right directory
if [ ! -f "README_LOCAL.md" ]; then
    print_error "Please run this script from the berit-shalvah directory"
    exit 1
fi

# Check prerequisites
print_header "📋 Checking Prerequisites..."

# Check Python
if command -v python3.12 &> /dev/null; then
    PYTHON_VERSION=$(python3.12 --version)
    print_status "✅ Python 3.12 found: $PYTHON_VERSION"
else
    print_error "❌ Python 3.12 not found. Please install Python 3.12"
    exit 1
fi

# Check PostgreSQL
if command -v psql &> /dev/null; then
    POSTGRES_VERSION=$(psql --version | head -n1)
    print_status "✅ PostgreSQL found: $POSTGRES_VERSION"
else
    print_error "❌ PostgreSQL not found. Please install PostgreSQL 16+"
    exit 1
fi

# Check Redis
if command -v redis-cli &> /dev/null; then
    REDIS_VERSION=$(redis-cli --version)
    print_status "✅ Redis found: $REDIS_VERSION"
else
    print_error "❌ Redis not found. Please install Redis 7+"
    exit 1
fi

# Setup PostgreSQL
print_header "🗄️  Setting up PostgreSQL..."

# Start PostgreSQL if not running
if ! sudo systemctl is-active --quiet postgresql-16; then
    print_status "Starting PostgreSQL..."
    sudo systemctl start postgresql-16
    sleep 3
fi

# Enable PostgreSQL
sudo systemctl enable postgresql-16

# Check if databases exist
if sudo -u postgres psql -lqt | grep -q berit_odoo; then
    print_status "✅ Database 'berit_odoo' exists"
else
    print_status "Creating database 'berit_odoo'..."
    sudo -u postgres createdb berit_odoo
fi

if sudo -u postgres psql -lqt | grep -q berit_portal; then
    print_status "✅ Database 'berit_portal' exists"
else
    print_status "Creating database 'berit_portal'..."
    sudo -u postgres createdb berit_portal
fi

# Check if user exists
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='berit_user';" | grep -q 1; then
    print_status "✅ Database user 'berit_user' exists"
else
    print_status "Creating database user 'berit_user'..."
    sudo -u postgres createuser -s berit_user
fi

# Setup Redis
print_header "🔴 Setting up Redis..."

if ! sudo systemctl is-active --quiet redis; then
    print_status "Starting Redis..."
    sudo systemctl start redis
    sleep 2
fi

sudo systemctl enable redis

# Setup Python environments
print_header "🐍 Setting up Python environments..."

# Create virtual environments
if [ ! -d "odoo_env" ]; then
    print_status "Creating Odoo virtual environment..."
    python3.12 -m venv odoo_env
fi

if [ ! -d "django_env" ]; then
    print_status "Creating Django virtual environment..."
    python3.12 -m venv django_env
fi

# Install Python dependencies
print_header "📦 Installing Python dependencies..."

# Odoo dependencies
print_status "Installing Odoo dependencies..."
source odoo_env/bin/activate
cd odoo
pip install --upgrade pip
pip install -r requirements.txt
cd ..

# Django dependencies
print_status "Installing Django dependencies..."
source django_env/bin/activate
cd django_portal
pip install --upgrade pip
pip install -r requirements.txt
cd ..

# Setup environment file
print_header "⚙️  Setting up environment..."

if [ ! -f ".env" ]; then
    print_status "Creating .env file from template..."
    cp .env.example .env
    
    # Generate a random secret key
    SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
    
    # Update .env with generated secret
    sed -i "s/your-secret-key-here/$SECRET_KEY/" .env
    
    print_warning "⚠️  Please edit .env file with your database passwords and email settings"
    print_warning "⚠️  Current SECRET_KEY: $SECRET_KEY"
else
    print_status "✅ .env file already exists"
fi

# Django setup
print_header "🌐 Setting up Django..."

source django_env/bin/activate
cd django_portal

# Run migrations
print_status "Running Django migrations..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput

# Collect static files
print_status "Collecting static files..."
python manage.py collectstatic --noinput

# Create Django superuser if not exists
print_status "Creating Django superuser..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@beritshalvah.co.ke').exists():
    User.objects.create_superuser(
        email='admin@beritshalvah.co.ke',
        username='admin',
        first_name='Admin',
        last_name='User',
        password='admin123'
    )
    print('Django superuser created: admin@beritshalvah.co.ke / admin123')
else:
    print('Django superuser already exists')
EOF

cd ..

# Create startup scripts
print_header "🚀 Creating startup scripts..."

# Django startup script
cat > start_django.sh << 'EOF'
#!/bin/bash
echo "Starting Django Portal..."
cd $(dirname "$0")/django_portal
source ../django_env/bin/activate
export DJANGO_SETTINGS_MODULE=config.settings.development
python manage.py runserver 0.0.0.0:8000
EOF

chmod +x start_django.sh

# Odoo startup script
cat > start_odoo.sh << 'EOF'
#!/bin/bash
echo "Starting Odoo Backend..."
cd $(dirname "$0")/odoo
source ../odoo_env/bin/activate
export ODOO_RCFILE=odoo.conf
python odoo-bin --addons-path=/opt/odoo/addons,/mnt/extra-addons --db-filter=berit_odoo --dev=all
EOF

chmod +x start_odoo.sh

# Celery startup script
cat > start_celery.sh << 'EOF'
#!/bin/bash
echo "Starting Celery..."
cd $(dirname "$0")/django_portal
source ../django_env/bin/activate
export DJANGO_SETTINGS_MODULE=config.settings.development

# Start Celery worker
celery -A config worker -l info &

# Start Celery beat
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler &
EOF

chmod +x start_celery.sh

# Display final information
print_header "🎉 Setup Complete!"

echo ""
echo "📋 Access Information:"
echo "=================================="
echo "🌐 Django Portal:      http://localhost:8000/portal"
echo "👤 Django Admin:       http://localhost:8000/admin"
echo "🏢 Odoo Backend:       http://localhost:8069"
echo ""
echo "🔑 Default Credentials:"
echo "=================================="
echo "Django Admin:         admin@beritshalvah.co.ke / admin123"
echo "Odoo Admin:           admin / admin"
echo ""
echo "🚀 To start services:"
echo "=================================="
echo "./start_django.sh     # Start Django portal"
echo "./start_odoo.sh       # Start Odoo backend"
echo "./start_celery.sh      # Start Celery workers"
echo ""
echo "📝 Development Commands:"
echo "=================================="
echo "cd django_portal && source ../django_env/bin/activate"
echo "python manage.py runserver 0.0.0.0:8000"
echo "python manage.py test"
echo "python manage.py makemigrations"
echo "python manage.py migrate"
echo ""
echo "📚 Documentation:"
echo "=================================="
echo "• README_LOCAL.md - Detailed setup guide"
echo "• Individual app docs in django_portal/apps/*/README.md"
echo "• Odoo module docs in odoo/addons/berit_loan/README.md"
echo ""

print_status "✅ Local development environment is ready!"
print_warning "💡 Don't forget to update .env with your actual database passwords and email settings"
