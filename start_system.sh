#!/bin/bash
echo "🚀 Starting Berit Shalvah Financial Services System..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}📁 Project Directory: $PROJECT_DIR${NC}"

# Function to check if service is running
check_service() {
    local service=$1
    if systemctl is-active --quiet $service; then
        echo -e "${GREEN}✓ $service is running${NC}"
        return 0
    else
        echo -e "${RED}✗ $service is not running${NC}"
        return 1
    fi
}

# Function to start service
start_service() {
    local service=$1
    local description=$2
    echo -e "${YELLOW}🔄 Starting $description...${NC}"
    sudo systemctl start $service
    sleep 2
    if check_service $service; then
        echo -e "${GREEN}✓ $description started successfully${NC}"
    else
        echo -e "${RED}✗ Failed to start $description${NC}"
    fi
}

echo -e "${BLUE}🔍 Checking system services...${NC}"

# Check and start PostgreSQL
if ! check_service postgresql; then
    start_service postgresql "PostgreSQL Database"
fi

# Check and start Redis
if ! check_service redis; then
    start_service redis "Redis Cache Server"
fi

# Check and start Nginx
if ! check_service nginx; then
    start_service nginx "Nginx Reverse Proxy"
fi

# Copy our nginx config and reload so WebSocket/gevent rules are active
echo -e "${YELLOW}🔄 Applying Nginx configuration...${NC}"
sudo cp "$PROJECT_DIR/nginx/nginx.conf" /etc/nginx/nginx.conf
if sudo nginx -t 2>/dev/null; then
    sudo systemctl reload nginx
    echo -e "${GREEN}✓ Nginx configuration applied${NC}"
else
    echo -e "${RED}✗ Nginx config test failed – reload skipped. Check /etc/nginx/nginx.conf${NC}"
fi

echo -e "${BLUE}🌐 Starting Application Services...${NC}"

# Start Odoo
echo -e "${YELLOW}🔄 Starting Odoo Backend...${NC}"
cd $PROJECT_DIR
source odoo_env/bin/activate
python /home/nick/odoo-19/odoo-bin \
    --config=$PROJECT_DIR/odoo/odoo.conf \
    --db-filter='^berit_odoo$' \
    --gevent-port=8072 &
ODOO_PID=$!
echo -e "${GREEN}✓ Odoo started (PID: $ODOO_PID)${NC}"

# Wait a moment for Odoo to initialize
sleep 5

# Start Django Portal
echo -e "${YELLOW}🔄 Starting Django Portal...${NC}"
cd $PROJECT_DIR/django_portal
source ../django_env/bin/activate
export DJANGO_SETTINGS_MODULE=config.settings.development
python manage.py runserver 0.0.0.0:8000 &
DJANGO_PID=$!
echo -e "${GREEN}✓ Django Portal started (PID: $DJANGO_PID)${NC}"

# Start Celery Worker
echo -e "${YELLOW}🔄 Starting Celery Worker...${NC}"
cd $PROJECT_DIR/django_portal
celery -A config worker --loglevel=info &
CELERY_PID=$!
echo -e "${GREEN}✓ Celery Worker started (PID: $CELERY_PID)${NC}"

# Start Celery Beat (scheduler)
echo -e "${YELLOW}🔄 Starting Celery Beat...${NC}"
cd $PROJECT_DIR/django_portal
celery -A config beat --loglevel=info &
CELERY_BEAT_PID=$!
echo -e "${GREEN}✓ Celery Beat started (PID: $CELERY_BEAT_PID)${NC}"

echo -e "${GREEN}🎉 All services started successfully!${NC}"
echo -e "${BLUE}📊 Service Status:${NC}"
echo -e "  • PostgreSQL: Running"
echo -e "  • Redis: Running"
echo -e "  • Nginx: Running"
echo -e "  • Odoo Backend:   http://localhost:8069 (PID: $ODOO_PID)"
echo -e "  • Odoo WebSocket: http://localhost:8072"
echo -e "  • Django Portal: http://localhost:8000 (PID: $DJANGO_PID)"
echo -e "  • Celery Worker: Running (PID: $CELERY_PID)"
echo -e "  • Celery Beat: Running (PID: $CELERY_BEAT_PID)"

echo -e "${YELLOW}💡 Access URLs:${NC}"
echo -e "  • Odoo Admin: http://localhost:8069/web/login"
echo -e "  • Django Portal: http://localhost:8000"
echo -e "  • Nginx Proxy: http://localhost"

echo -e "${RED}⚠️  Press Ctrl+C to stop all services${NC}"

# Wait for user to stop
trap 'echo -e "${YELLOW}🛑 Stopping all services...${NC}"; kill $ODOO_PID $DJANGO_PID $CELERY_PID $CELERY_BEAT_PID 2>/dev/null; echo -e "${GREEN}✓ All services stopped${NC}"; exit 0' INT

# Keep running
while true; do
    sleep 1
done
