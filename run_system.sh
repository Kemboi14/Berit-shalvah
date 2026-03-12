#!/bin/bash

###############################################################################
# Berit Shalvah System Startup Script
#
# This script manages the complete lifecycle of the Berit Shalvah Portal:
# - System health checks
# - Database initialization
# - Cache setup
# - Django migrations
# - Background workers
# - Service monitoring
#
# Usage: ./run_system.sh [command]
# Commands: start, stop, restart, status, migrate, logs, test-sync, help
###############################################################################

set -e

# Configuration
PROJECT_ROOT="/home/nick/berit-shalvah"
DJANGO_DIR="$PROJECT_ROOT/django_portal"
ENV_FILE="$PROJECT_ROOT/.env"
VENV_PATH="$PROJECT_ROOT/django_env"
LOGS_DIR="$PROJECT_ROOT/logs"
PID_DIR="/tmp/berit_pids"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Ensure logs and pid directories exist
mkdir -p "$LOGS_DIR" "$PID_DIR"

###############################################################################
# Utility Functions
###############################################################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

check_env() {
    if [ ! -f "$ENV_FILE" ]; then
        log_error "Environment file not found: $ENV_FILE"
        log_info "Creating from template..."
        cp "$PROJECT_ROOT/.env.example" "$ENV_FILE" 2>/dev/null || {
            log_error "Could not create .env file"
            exit 1
        }
        log_warning "Please configure $ENV_FILE with your settings"
        return 1
    fi
    return 0
}

activate_venv() {
    if [ ! -d "$VENV_PATH" ]; then
        log_error "Virtual environment not found: $VENV_PATH"
        exit 1
    fi
    source "$VENV_PATH/bin/activate"
    log_success "Virtual environment activated"
}

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "Required command not found: $1"
        return 1
    fi
    return 0
}

###############################################################################
# Health Check Functions
###############################################################################

check_postgresql() {
    print_header "Checking PostgreSQL"

    if ! check_command "psql"; then
        log_error "PostgreSQL client not installed"
        return 1
    fi

    if ! psql -U "${POSTGRES_USER:-berit_user}" -d "${PORTAL_DB:-berit_portal}" -c "SELECT 1" &>/dev/null; then
        log_error "PostgreSQL connection failed"
        log_info "Starting PostgreSQL..."
        sudo systemctl start postgresql || {
            log_error "Failed to start PostgreSQL"
            return 1
        }
        sleep 2
    fi

    log_success "PostgreSQL is running"
    return 0
}

check_redis() {
    print_header "Checking Redis"

    if ! check_command "redis-cli"; then
        log_error "Redis CLI not installed"
        return 1
    fi

    if ! redis-cli ping &>/dev/null; then
        log_error "Redis connection failed"
        log_info "Starting Redis..."
        sudo systemctl start redis || {
            log_error "Failed to start Redis"
            return 1
        }
        sleep 2
    fi

    log_success "Redis is running"
    return 0
}

check_python() {
    print_header "Checking Python & Dependencies"

    if ! check_command "python"; then
        log_error "Python not found"
        return 1
    fi

    python_version=$(python --version | awk '{print $2}')
    log_info "Python version: $python_version"

    activate_venv

    # Check required packages
    python -c "import django; import celery; import psycopg2; import redis" 2>/dev/null || {
        log_error "Missing required packages"
        log_info "Installing requirements..."
        pip install -q -r "$DJANGO_DIR/requirements.txt" || {
            log_error "Failed to install requirements"
            return 1
        }
    }

    log_success "Python dependencies are installed"
    return 0
}

check_django() {
    print_header "Checking Django"

    cd "$DJANGO_DIR"

    # Run system checks
    if ! python manage.py check &>/dev/null; then
        log_error "Django system check failed"
        python manage.py check
        return 1
    fi

    log_success "Django system checks passed"
    return 0
}

run_health_checks() {
    print_header "System Health Checks"

    local failed=0

    check_postgresql || failed=$((failed + 1))
    check_redis || failed=$((failed + 1))
    check_python || failed=$((failed + 1))
    check_django || failed=$((failed + 1))

    if [ $failed -eq 0 ]; then
        log_success "All health checks passed"
        return 0
    else
        log_error "$failed health check(s) failed"
        return 1
    fi
}

###############################################################################
# Database Functions
###############################################################################

run_migrations() {
    print_header "Running Database Migrations"

    check_env || return 1
    activate_venv

    cd "$DJANGO_DIR"

    log_info "Checking migration status..."
    python manage.py showmigrations --plan 2>&1 | head -20

    log_info "Applying pending migrations..."
    python manage.py migrate --noinput || {
        log_error "Migration failed"
        return 1
    }

    log_success "Migrations completed successfully"
}

show_migration_status() {
    print_header "Migration Status"

    activate_venv
    cd "$DJANGO_DIR"

    python manage.py showmigrations
}

create_superuser() {
    print_header "Create Superuser"

    activate_venv
    cd "$DJANGO_DIR"

    log_info "Creating superuser..."
    python manage.py createsuperuser
}

collect_static() {
    print_header "Collecting Static Files"

    activate_venv
    cd "$DJANGO_DIR"

    python manage.py collectstatic --noinput || {
        log_error "Failed to collect static files"
        return 1
    }

    log_success "Static files collected"
}

###############################################################################
# Service Start/Stop Functions
###############################################################################

start_django() {
    print_header "Starting Django Development Server"

    activate_venv
    cd "$DJANGO_DIR"

    local port="${DJANGO_PORT:-8000}"
    local logfile="$LOGS_DIR/django.log"

    log_info "Starting Django on port $port..."
    nohup python manage.py runserver 0.0.0.0:$port > "$logfile" 2>&1 &

    local pid=$!
    echo $pid > "$PID_DIR/django.pid"

    sleep 2
    if kill -0 $pid 2>/dev/null; then
        log_success "Django started (PID: $pid)"
        log_info "Access portal at: http://localhost:$port"
    else
        log_error "Failed to start Django"
        return 1
    fi
}

start_celery_worker() {
    print_header "Starting Celery Worker"

    activate_venv
    cd "$DJANGO_DIR"

    local logfile="$LOGS_DIR/celery_worker.log"

    log_info "Starting Celery worker..."
    nohup celery -A config worker -l info --concurrency=4 > "$logfile" 2>&1 &

    local pid=$!
    echo $pid > "$PID_DIR/celery_worker.pid"

    sleep 2
    if kill -0 $pid 2>/dev/null; then
        log_success "Celery worker started (PID: $pid)"
    else
        log_error "Failed to start Celery worker"
        return 1
    fi
}

start_celery_beat() {
    print_header "Starting Celery Beat Scheduler"

    activate_venv
    cd "$DJANGO_DIR"

    local logfile="$LOGS_DIR/celery_beat.log"

    log_info "Starting Celery beat..."
    nohup celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler > "$logfile" 2>&1 &

    local pid=$!
    echo $pid > "$PID_DIR/celery_beat.pid"

    sleep 2
    if kill -0 $pid 2>/dev/null; then
        log_success "Celery beat started (PID: $pid)"
    else
        log_error "Failed to start Celery beat"
        return 1
    fi
}

start_flower() {
    print_header "Starting Flower (Celery Monitor)"

    activate_venv
    cd "$DJANGO_DIR"

    local logfile="$LOGS_DIR/flower.log"
    local port="${FLOWER_PORT:-5555}"

    log_info "Starting Flower on port $port..."
    nohup celery -A config flower --port=$port > "$logfile" 2>&1 &

    local pid=$!
    echo $pid > "$PID_DIR/flower.pid"

    sleep 2
    if kill -0 $pid 2>/dev/null; then
        log_success "Flower started (PID: $pid)"
        log_info "Monitor at: http://localhost:$port"
    else
        log_warning "Flower failed to start (optional service)"
    fi
}

stop_service() {
    local service=$1
    local pidfile="$PID_DIR/${service}.pid"

    if [ -f "$pidfile" ]; then
        local pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping $service (PID: $pid)..."
            kill "$pid"
            sleep 1
            if ! kill -0 "$pid" 2>/dev/null; then
                log_success "$service stopped"
                rm -f "$pidfile"
            else
                log_warning "Forcing kill on $service..."
                kill -9 "$pid"
                rm -f "$pidfile"
                log_success "$service force stopped"
            fi
        else
            log_warning "$service is not running"
            rm -f "$pidfile"
        fi
    else
        log_warning "$service PID file not found"
    fi
}

###############################################################################
# Start/Stop All Functions
###############################################################################

start_all() {
    print_header "Starting All Services"

    run_health_checks || {
        log_error "Health checks failed. Fix issues and try again."
        return 1
    }

    run_migrations || return 1

    start_django || return 1
    start_celery_worker || return 1
    start_celery_beat || return 1

    # Flower is optional
    if command -v flower &> /dev/null; then
        start_flower
    fi

    print_header "System Started Successfully"
    log_success "All services are running"
    echo ""
    log_info "Portal:  http://localhost:8000"
    log_info "Admin:   http://localhost:8000/admin"
    log_info "Flower:  http://localhost:5555"
    echo ""
}

stop_all() {
    print_header "Stopping All Services"

    stop_service "django"
    stop_service "celery_worker"
    stop_service "celery_beat"
    stop_service "flower"

    log_success "All services stopped"
}

restart_all() {
    stop_all
    sleep 2
    start_all
}

show_status() {
    print_header "System Status"

    local services=("django" "celery_worker" "celery_beat" "flower")
    local running=0
    local stopped=0

    for service in "${services[@]}"; do
        local pidfile="$PID_DIR/${service}.pid"
        if [ -f "$pidfile" ]; then
            local pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                log_success "$service is running (PID: $pid)"
                running=$((running + 1))
            else
                log_error "$service is not running (stale PID)"
                stopped=$((stopped + 1))
            fi
        else
            log_error "$service is not running"
            stopped=$((stopped + 1))
        fi
    done

    echo ""
    log_info "Summary: $running running, $stopped stopped"
}

show_logs() {
    local service="${1:-django}"
    local logfile="$LOGS_DIR/${service}.log"

    if [ ! -f "$logfile" ]; then
        log_error "Log file not found: $logfile"
        return 1
    fi

    log_info "Showing last 50 lines of $service log..."
    echo ""
    tail -50 "$logfile"
}

follow_logs() {
    local service="${1:-django}"
    local logfile="$LOGS_DIR/${service}.log"

    if [ ! -f "$logfile" ]; then
        log_error "Log file not found: $logfile"
        return 1
    fi

    log_info "Following $service log (Ctrl+C to stop)..."
    tail -f "$logfile"
}

###############################################################################
# Testing Functions
###############################################################################

test_odoo_sync() {
    print_header "Testing Odoo Sync"

    activate_venv
    cd "$DJANGO_DIR"

    python manage.py shell << 'EOF'
import sys
from apps.loans.sync.perfect_sync import PerfectOdooSync

try:
    sync = PerfectOdooSync()
    print("[✓] PerfectOdooSync initialized")

    # Test connection
    sync.test_connection()
    print("[✓] Odoo connection successful")

    # List models
    from apps.loans.sync.webhook_models import SyncEvent
    events = SyncEvent.objects.all()
    print(f"[✓] Database connected. Found {events.count()} sync events")

except Exception as e:
    print(f"[✗] Error: {e}", file=sys.stderr)
    sys.exit(1)

print("\n[✓] Odoo sync system operational")
EOF
}

run_tests() {
    print_header "Running Django Tests"

    activate_venv
    cd "$DJANGO_DIR"

    python manage.py test apps.loans.sync -v 2
}

###############################################################################
# Info Functions
###############################################################################

show_help() {
    cat << 'EOF'

╔════════════════════════════════════════════════════════════════════════════╗
║           Berit Shalvah System Control Script - Help                       ║
╚════════════════════════════════════════════════════════════════════════════╝

USAGE:
    ./run_system.sh [COMMAND]

COMMANDS:

  start              Start all services (Django, Celery, Beat)
  stop               Stop all services gracefully
  restart            Restart all services
  status             Show status of all services

  migrate            Run database migrations
  migrations         Show migration status
  superuser          Create a Django superuser
  static             Collect static files

  health             Run system health checks
  check              Run Django system checks

  logs [SERVICE]     Show logs for a service (default: django)
  follow [SERVICE]   Follow logs in real-time

  test-sync          Test Odoo synchronization
  test               Run Django tests

  shell              Open Django shell
  help               Show this help message

SERVICES:
  - django           Django development server
  - celery_worker    Celery task worker
  - celery_beat      Celery beat scheduler
  - flower           Celery monitoring UI (optional)

EXAMPLES:
    # Start everything
    ./run_system.sh start

    # Run migrations and start
    ./run_system.sh migrate
    ./run_system.sh start

    # View status
    ./run_system.sh status

    # Follow Django logs
    ./run_system.sh follow django

    # Test Odoo connectivity
    ./run_system.sh test-sync

    # Stop all services
    ./run_system.sh stop

ENVIRONMENT VARIABLES:
    DJANGO_PORT        Django server port (default: 8000)
    FLOWER_PORT        Flower monitoring port (default: 5555)
    POSTGRES_HOST      PostgreSQL host
    POSTGRES_PORT      PostgreSQL port
    REDIS_URL          Redis connection URL
    DEBUG              Django debug mode

For more information, see SYSTEM_OPERATIONAL_GUIDE.md

EOF
}

show_config() {
    print_header "System Configuration"

    log_info "Project Root: $PROJECT_ROOT"
    log_info "Django Dir:   $DJANGO_DIR"
    log_info "Logs Dir:     $LOGS_DIR"
    log_info "Venv Path:    $VENV_PATH"
    log_info "Environment:  $ENV_FILE"
    echo ""

    if check_env; then
        log_info "Loading environment from $ENV_FILE..."
        source "$ENV_FILE"

        log_info "Key Settings:"
        log_info "  - DEBUG:        ${DEBUG:-not set}"
        log_info "  - POSTGRES_HOST: ${POSTGRES_HOST:-not set}"
        log_info "  - ODOO_URL:     ${ODOO_URL:-not set}"
        log_info "  - REDIS_URL:    ${REDIS_URL:-not set}"
    fi
}

###############################################################################
# Main Command Handler
###############################################################################

main() {
    local command="${1:-help}"

    case "$command" in
        start)
            start_all
            ;;
        stop)
            stop_all
            ;;
        restart)
            restart_all
            ;;
        status)
            show_status
            ;;

        migrate)
            run_migrations
            ;;
        migrations)
            show_migration_status
            ;;
        superuser)
            create_superuser
            ;;
        static)
            collect_static
            ;;

        health|check)
            run_health_checks
            ;;

        logs)
            show_logs "${2:-django}"
            ;;
        follow)
            follow_logs "${2:-django}"
            ;;

        test-sync)
            test_odoo_sync
            ;;
        test)
            run_tests
            ;;

        shell)
            activate_venv
            cd "$DJANGO_DIR"
            python manage.py shell
            ;;

        config|info)
            show_config
            ;;

        help|-h|--help)
            show_help
            ;;

        *)
            log_error "Unknown command: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
