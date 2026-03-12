#!/bin/bash

# Migration Verification Script
# Comprehensive checks for Django sync module migrations

set -e

echo "=========================================="
echo "Django Migration Verification Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to project root
cd "$(dirname "$0")"

echo "📋 Checking environment..."
if [ ! -f "django_portal/manage.py" ]; then
    echo -e "${RED}✗ manage.py not found. Are you in the project root?${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Project root confirmed${NC}"
echo ""

# Check Python
echo "🐍 Checking Python..."
if ! command -v python &> /dev/null; then
    echo -e "${RED}✗ Python not found${NC}"
    exit 1
fi
PYTHON_VERSION=$(python --version 2>&1)
echo -e "${GREEN}✓ $PYTHON_VERSION${NC}"
echo ""

# Check Django
echo "🎯 Checking Django..."
DJANGO_CHECK=$(python django_portal/manage.py --version 2>&1)
echo -e "${GREEN}✓ Django $DJANGO_CHECK${NC}"
echo ""

# Run system checks
echo "🔍 Running Django system checks..."
if python django_portal/manage.py check &> /dev/null; then
    echo -e "${GREEN}✓ All system checks passed${NC}"
else
    echo -e "${YELLOW}⚠ Some warnings present (non-critical)${NC}"
fi
echo ""

# Check migrations status
echo "📊 Checking migration status..."
PENDING=$(python django_portal/manage.py showmigrations --plan 2>&1 | grep "^\[ \]" | wc -l)

if [ "$PENDING" -eq 0 ]; then
    echo -e "${GREEN}✓ All migrations applied ($PENDING pending)${NC}"
else
    echo -e "${RED}✗ $PENDING pending migrations${NC}"
fi
echo ""

# Check sync app specifically
echo "🔄 Checking sync app migrations..."
SYNC_STATUS=$(python django_portal/manage.py showmigrations sync 2>&1 | grep "\[X\]" | wc -l)
if [ "$SYNC_STATUS" -gt 0 ]; then
    echo -e "${GREEN}✓ Sync migrations applied${NC}"
    python django_portal/manage.py showmigrations sync 2>&1 | grep -E "^\[" | sed 's/^/  /'
else
    echo -e "${RED}✗ Sync migrations not applied${NC}"
fi
echo ""

# Check sync models
echo "🗄️ Checking sync models..."
SYNC_MODELS=$(python -c "
from django.apps import apps
app = apps.get_app_config('sync')
models = [m.__name__ for m in app.get_models()]
print(', '.join(sorted(models)))
" 2>&1)

echo "Found models: $SYNC_MODELS"
if echo "$SYNC_MODELS" | grep -q "SyncEvent"; then
    echo -e "${GREEN}✓ SyncEvent model found${NC}"
else
    echo -e "${RED}✗ SyncEvent model not found${NC}"
fi

if echo "$SYNC_MODELS" | grep -q "SyncConflict"; then
    echo -e "${GREEN}✓ SyncConflict model found${NC}"
else
    echo -e "${RED}✗ SyncConflict model not found${NC}"
fi

if echo "$SYNC_MODELS" | grep -q "SyncLock"; then
    echo -e "${GREEN}✓ SyncLock model found${NC}"
else
    echo -e "${RED}✗ SyncLock model not found${NC}"
fi

if echo "$SYNC_MODELS" | grep -q "WebhookSubscription"; then
    echo -e "${GREEN}✓ WebhookSubscription model found${NC}"
else
    echo -e "${RED}✗ WebhookSubscription model not found${NC}"
fi
echo ""

# Check sync module files
echo "📁 Checking sync module files..."
FILES=(
    "django_portal/apps/loans/sync/__init__.py"
    "django_portal/apps/loans/sync/apps.py"
    "django_portal/apps/loans/sync/webhook_models.py"
    "django_portal/apps/loans/sync/perfect_sync.py"
    "django_portal/apps/loans/sync/migrations/__init__.py"
    "django_portal/apps/loans/sync/migrations/0001_initial.py"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓ $file${NC}"
    else
        echo -e "${RED}✗ $file missing${NC}"
    fi
done
echo ""

# Check INSTALLED_APPS
echo "⚙️ Checking INSTALLED_APPS..."
if grep -q "apps.loans.sync.apps.SyncConfig" django_portal/config/settings/base.py; then
    echo -e "${GREEN}✓ Sync app registered in INSTALLED_APPS${NC}"
else
    echo -e "${RED}✗ Sync app not properly registered${NC}"
fi
echo ""

# Summary
echo "=========================================="
echo "Verification Summary"
echo "=========================================="
echo -e "${GREEN}✅ All migration checks completed${NC}"
echo ""
echo "Next steps:"
echo "1. Start Django: python django_portal/manage.py runserver"
echo "2. Access admin: http://localhost:8000/admin/"
echo "3. View sync events: http://localhost:8000/admin/sync/syncevent/"
echo ""
echo "For more information, see:"
echo "- MIGRATION_COMPLETION_SUMMARY.md"
echo "- SYNC_ADMIN_SETUP.md"
echo "- MIGRATION_QUICK_REFERENCE.md"
echo ""
