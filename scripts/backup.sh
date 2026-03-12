#!/bin/bash

# Berit Shalvah Financial Services - Backup Script
# This script creates backups of databases and media files

set -e

echo "🔄 Creating backup for Berit Shalvah Financial Services..."

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

# Configuration
BACKUP_DIR="/var/backups/berit-shalvah"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="$BACKUP_DIR/$DATE"

# Create backup directory
mkdir -p "$BACKUP_PATH"

print_status "Backup started at: $(date)"

# Backup PostgreSQL databases
print_status "Backing up PostgreSQL databases..."

# Odoo database
print_status "Backing up Odoo database..."
docker-compose exec -T db pg_dump -U berit_user berit_odoo | gzip > "$BACKUP_PATH/berit_odoo_backup.sql.gz"

# Django portal database
print_status "Backing up Django portal database..."
docker-compose exec -T db pg_dump -U berit_user berit_portal | gzip > "$BACKUP_PATH/berit_portal_backup.sql.gz"

# Backup media files
print_status "Backing up media files..."
docker cp berit_django:/app/media "$BACKUP_PATH/media"

# Backup Odoo data directory
print_status "Backing up Odoo data..."
docker cp berit_odoo:/var/lib/odoo "$BACKUP_PATH/odoo_data"

# Backup configuration files
print_status "Backing up configuration files..."
cp .env "$BACKUP_PATH/"
cp docker-compose.yml "$BACKUP_PATH/"
cp nginx/nginx.conf "$BACKUP_PATH/"

# Create backup manifest
cat > "$BACKUP_PATH/backup_manifest.txt" << EOF
Backup created: $(date)
Backup ID: $DATE
Databases:
- berit_odoo (PostgreSQL)
- berit_portal (PostgreSQL)
Files included:
- Media files (Django)
- Odoo data directory
- Configuration files
Size: $(du -sh "$BACKUP_PATH" | cut -f1)
EOF

# Compress entire backup
print_status "Compressing backup..."
cd "$BACKUP_DIR"
tar -czf "berit_shalvah_backup_$DATE.tar.gz" "$DATE"
rm -rf "$DATE"

# Upload to S3 if configured (optional)
if [ -n "$AWS_S3_BUCKET" ] && [ -n "$AWS_ACCESS_KEY_ID" ]; then
    print_status "Uploading backup to S3..."
    aws s3 cp "berit_shalvah_backup_$DATE.tar.gz" "s3://$AWS_S3_BUCKET/backups/"
    
    # Create S3 lifecycle rule for old backups (optional)
    aws s3api put-bucket-lifecycle-configuration \
        --bucket "$AWS_S3_BUCKET" \
        --lifecycle-configuration '{
            "Rules": [
                {
                    "ID": "BackupRetention",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "backups/"},
                    "Transitions": [
                        {
                            "Days": 30,
                            "StorageClass": "STANDARD_IA"
                        },
                        {
                            "Days": 90,
                            "StorageClass": "GLACIER"
                        }
                    ],
                    "Expiration": {"Days": 365}
                }
            ]
        }'
fi

# Clean up old backups
print_status "Cleaning up old backups (keeping last $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "berit_shalvah_backup_*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Verify backup integrity
print_status "Verifying backup integrity..."
BACKUP_FILE="$BACKUP_DIR/berit_shalvah_backup_$DATE.tar.gz"

if [ -f "$BACKUP_FILE" ]; then
    # Test if backup file is not corrupted
    if tar -tzf "$BACKUP_FILE" > /dev/null 2>&1; then
        print_status "✅ Backup file is valid"
        
        # Show backup size
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        print_status "📦 Backup size: $BACKUP_SIZE"
    else
        print_error "❌ Backup file is corrupted"
        exit 1
    fi
else
    print_error "❌ Backup file not found"
    exit 1
fi

# Send notification (optional)
if [ -n "$ADMIN_EMAIL" ]; then
    print_status "Sending backup notification to $ADMIN_EMAIL..."
    
    # Send email using mail command or curl to email service
    {
        echo "Subject: Berit Shalvah Backup Completed - $DATE"
        echo "To: $ADMIN_EMAIL"
        echo ""
        echo "Backup completed successfully!"
        echo ""
        echo "Backup details:"
        echo "- Date: $(date)"
        echo "- Size: $BACKUP_SIZE"
        echo "- Location: $BACKUP_FILE"
        echo ""
        echo "System status:"
        docker-compose ps --format "table {{.Service}}\t{{.Status}}"
    } | sendmail -t "$ADMIN_EMAIL" 2>/dev/null || \
    curl -X POST "https://api.mailgun.net/v3/yourdomain/messages" \
        -u "api:YOUR_MAILGUN_API_KEY" \
        -F from="backup@beritshalvah.co.ke" \
        -F to="$ADMIN_EMAIL" \
        -F subject="Berit Shalvah Backup Completed - $DATE" \
        -F text="Backup completed successfully! Size: $BACKUP_SIZE" \
        2>/dev/null || \
    print_warning "Could not send email notification"
fi

# Log backup completion
echo "$(date): Backup completed successfully - $BACKUP_SIZE" >> "$BACKUP_DIR/backup.log"

# Display summary
echo ""
echo "✅ Backup completed successfully!"
echo ""
echo "📋 Backup Summary:"
echo "=================================="
echo "📁 Location:           $BACKUP_FILE"
echo "📦 Size:               $BACKUP_SIZE"
echo "🗃️  Databases:          berit_odoo, berit_portal"
echo "📁 Files:              media, odoo_data, configs"
echo "🔄 Retention:          $RETENTION_DAYS days"
echo "📊 Log file:           $BACKUP_DIR/backup.log"
echo ""

# Show recent backups
print_status "Recent backups:"
ls -lh "$BACKUP_DIR"/berit_shalvah_backup_*.tar.gz | tail -5

echo ""
print_status "Backup process completed! 🎉"
