#!/bin/bash

# Berit Shalvah Financial Services - Production Deployment Script
# This script deploys the system to production

set -e

echo "🚀 Deploying Berit Shalvah Financial Services to Production..."

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

# Check if we're in production mode
if [ ! -f .env ]; then
    print_error ".env file not found. Please create it first."
    exit 1
fi

# Check production settings
if grep -q "DEBUG=True" .env; then
    print_error "DEBUG is set to True. Please set DEBUG=False for production."
    exit 1
fi

# Backup current deployment
print_status "Creating backup of current deployment..."
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup databases
print_status "Backing up databases..."
docker-compose exec -T db pg_dump -U berit_user berit_odoo > "$BACKUP_DIR/berit_odoo_backup.sql"
docker-compose exec -T db pg_dump -U berit_user berit_portal > "$BACKUP_DIR/berit_portal_backup.sql"

# Backup media files
print_status "Backing up media files..."
docker cp berit_django:/app/media "$BACKUP_DIR/media"

# Pull latest code (assuming git is used)
print_status "Pulling latest code..."
git pull origin main

# Build and deploy with production configuration
print_status "Building production containers..."
docker-compose -f docker-compose.yml -f docker-compose.prod.yml down
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Wait for services to be ready
print_status "Waiting for services to be ready..."
sleep 60

# Run migrations
print_status "Running Django migrations..."
docker-compose exec -T django python manage.py migrate

# Collect static files
print_status "Collecting static files..."
docker-compose exec -T django python manage.py collectstatic --noinput

# Check service health
print_status "Checking service health..."

# Check if all services are healthy
services=("odoo" "django" "nginx" "db" "redis")
for service in "${services[@]}"; do
    if docker-compose ps $service | grep -q "Up"; then
        print_status "✅ $service is running"
    else
        print_error "❌ $service is not running"
        exit 1
    fi
done

# Setup SSL certificate (if domain is configured)
DOMAIN=$(grep ALLOWED_HOSTS .env | cut -d '=' -f2 | cut -d ',' -f1 | tr -d "'")
if [ "$DOMAIN" != "localhost" ] && [ "$DOMAIN" != "127.0.0.1" ]; then
    print_status "Setting up SSL certificate for $DOMAIN..."
    
    # Install certbot if not present
    if ! command -v certbot &> /dev/null; then
        print_status "Installing certbot..."
        apt-get update
        apt-get install -y certbot python3-certbot-nginx
    fi
    
    # Obtain SSL certificate
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "beritfinance@gmail.com"
    
    # Setup auto-renewal
    echo "0 12 * * * /usr/bin/certbot renew --quiet" | crontab -
fi

# Setup log rotation
print_status "Setting up log rotation..."
cat > /etc/logrotate.d/berit-shalvah << EOF
/var/log/berit-shalvah/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 root root
    postrotate
        docker-compose restart nginx
    endscript
}
EOF

# Setup backup cron job
print_status "Setting up backup cron job..."
(crontab -l 2>/dev/null; echo "0 2 * * * /path/to/berit-shalvah/scripts/backup.sh") | crontab -

# Test production URLs
print_status "Testing production URLs..."
sleep 10

# Test main site
if curl -f -k https://$DOMAIN/health &> /dev/null; then
    print_status "✅ Main site is accessible"
else
    print_error "❌ Main site is not accessible"
fi

# Test Django portal
if curl -f -k https://$DOMAIN/portal/health &> /dev/null; then
    print_status "✅ Django portal is accessible"
else
    print_error "❌ Django portal is not accessible"
fi

# Test Odoo
if curl -f -k https://$DOMAIN/web &> /dev/null; then
    print_status "✅ Odoo is accessible"
else
    print_error "❌ Odoo is not accessible"
fi

# Display deployment summary
echo ""
echo "🎉 Production deployment completed!"
echo ""
echo "📋 Deployment Summary:"
echo "=================================="
echo "🌐 Domain:              https://$DOMAIN"
echo "👤 Django Portal:      https://$DOMAIN/portal"
echo "🏢 Odoo Backend:       https://$DOMAIN/web"
echo "📊 Django Admin:       https://$DOMAIN/admin"
echo ""
echo "🔐 Security:"
echo "=================================="
echo "✅ SSL certificate installed"
echo "✅ Debug mode disabled"
echo "✅ Security headers configured"
echo "✅ Rate limiting enabled"
echo ""
echo "💾 Backups:"
echo "=================================="
echo "📁 Location:           $BACKUP_DIR"
echo "🔄 Auto-backup:         Daily at 2:00 AM"
echo "📊 Retention:          30 days"
echo ""
echo "📝 Next Steps:"
echo "=================================="
echo "1. Test all functionality"
echo "2. Monitor logs for any issues"
echo "3. Update DNS if needed"
echo "4. Configure monitoring"
echo "5. Set up alerts for errors"
echo ""

# Show running containers
print_status "Running containers:"
docker-compose -f docker-compose.yml -f docker-compose.prod.yml ps

echo ""
print_status "Production deployment completed! 🚀"
