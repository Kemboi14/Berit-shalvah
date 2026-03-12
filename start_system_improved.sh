#!/bin/bash

################################################################################
# Berit Shalvah Financial Services - Improved System Startup Script
#
# This script starts all system services with enhanced error handling, logging,
# and recovery mechanisms.
#
# Usage: ./start_system_improved.sh [OPTIONS]
# Options:
#   --debug       Enable debug mode with verbose output
#   --no-odoo     Skip Odoo startup
#   --no-celery   Skip Celery worker and beat
#   --help        Show this help message
################################################################################

set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/startup_$(date +%Y%m%d_%H%M%S).log"
DJANGO_PORT=8000
ODOO_PORT=8069
ODOO_GEVENT_PORT=8072
ODOO_BIN_PATH="/home/nick/odoo-19/odoo-bin"
DJANGO_ENV_BIN="${PROJECT_DIR}/django_env/bin/activate"
ODOO_ENV_BIN="${PROJECT_DIR}/odoo_env/bin/activate"

# Flags
DEBUG=false
START_ODOO=true
START_CELERY=true
VERBOSE=false

# Arrays to store PIDs
declare -a PIDS
declare -a SERVICES

################################################################################
# Functions
################################################################################

# Print with timestamp
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" | tee -a "$LOG_FILE"
}

# Print colored output
print_status() {
    local color=$1
    local symbol=$2
    local message=$3
    echo -e "${color}${symbol} ${message}${NC}" | tee -a "$LOG_FILE"
}

# Initialize logging
init_logging() {
    mkdir -p "$LOG_DIR"
    touch "$LOG_FILE"
    log "INFO" "=========================================="
    log "INFO" "Berit Shalvah System Startup"
    log "INFO" "Started: $(date)"
    log "INFO" "Project Directory: $PROJECT_DIR"
    log "INFO" "=========================================="
}

# Parse command line arguments
parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --debug)
                DEBUG=true
                VERBOSE=true
                log "INFO" "Debug mode enabled"
                shift
                ;;
            --verbose)
                VERBOSE=true
                shift
                ;;
            --no-odoo)
                START_ODOO=false
                log "INFO" "Odoo startup disabled"
                shift
                ;;
            --no-celery)
                START_CELERY=false
                log "INFO" "Celery startup disabled"
                shift
                ;;
            --help)
                print_help
                exit 0
                ;;
            *)
                log "WARN" "Unknown option: $1"
                shift
                ;;
        esac
    done
}

# Print help message
print_help() {
    cat << EOF
Berit Shalvah Financial Services - System Startup Script

Usage: $0 [OPTIONS]

Options:
  --debug       Enable debug mode with verbose output
  --verbose     Show verbose output
  --no-odoo     Skip Odoo startup
  --no-celery   Skip Celery worker and beat
  --help        Show this help message

Examples:
  # Start all services (default)
  $0

  # Start with debug output
  $0 --debug

  # Start without Odoo
  $0 --no-odoo

  # Start only Django (no Odoo, no Celery)
  $0 --no-odoo --no-celery

Access URLs after startup:
  - Django Portal: http://localhost:${DJANGO_PORT}
  - Django Admin: http://localhost:${DJANGO_PORT}/admin
  - Odoo Admin: http://localhost:${ODOO_PORT}/web/login
  - Nginx Proxy: http://localhost

Press Ctrl+C to stop all services

EOF
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check system dependencies
check_dependencies() {
    print_status "$BLUE" "🔍" "Checking system dependencies..."

    local missing_deps=()

    for cmd in python python3 postgres redis-server systemctl; do
        if ! command_exists "$cmd"; then
            missing_deps+=("$cmd")
            log "ERROR" "Missing dependency: $cmd"
        else
            log "DEBUG" "✓ $cmd found"
        fi
    done

    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_status "$RED" "✗" "Missing dependencies: ${missing_deps[*]}"
        log "ERROR" "Please install missing dependencies and try again"
        return 1
    fi

    print_status "$GREEN" "✓" "All dependencies satisfied"
    return 0
}

# Check if service is running
check_service() {
    local service=$1
    if systemctl is-active --quiet "$service" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Start a system service
start_service() {
    local service=$1
    local description=$2

    print_status "$YELLOW" "🔄" "Starting ${description}..."
    log "INFO" "Attempting to start service: $service"

    if check_service "$service"; then
        print_status "$GREEN" "✓" "${description} already running"
        log "INFO" "Service $service already running"
        return 0
    fi

    if ! sudo systemctl start "$service" 2>/dev/null; then
        print_status "$RED" "✗" "Failed to start ${description}"
        log "ERROR" "Failed to start service: $service"
        return 1
    fi

    sleep 2

    if check_service "$service"; then
        print_status "$GREEN" "✓" "${description} started successfully"
        log "INFO" "Service $service started successfully"
        return 0
    else
        print_status "$RED" "✗" "Failed to start ${description}"
        log "ERROR" "Service $service failed to start"
        return 1
    fi
}

# Apply our nginx config and reload so WebSocket/gevent rules are active
apply_nginx_config() {
    print_status "$YELLOW" "🔄" "Applying Nginx configuration (WebSocket/gevent rules)..."
    log "INFO" "Copying nginx config and reloading"

    if ! sudo cp "$PROJECT_DIR/nginx/nginx.conf" /etc/nginx/nginx.conf 2>/dev/null; then
        print_status "$RED" "✗" "Failed to copy nginx config"
        log "ERROR" "Could not copy nginx/nginx.conf to /etc/nginx/nginx.conf"
        return 1
    fi

    if sudo nginx -t >> "$LOG_FILE" 2>&1; then
        sudo systemctl reload nginx
        print_status "$GREEN" "✓" "Nginx configuration applied and reloaded"
        log "INFO" "Nginx reloaded successfully"
    else
        print_status "$RED" "✗" "Nginx config test failed – reload skipped"
        log "ERROR" "nginx -t failed; check $LOG_FILE for details"
        return 1
    fi
}

# Check virtual environment
check_venv() {
    local venv_path=$1
    local venv_name=$2

    if [ ! -f "$venv_path" ]; then
        print_status "$RED" "✗" "Virtual environment not found: $venv_name"
        log "ERROR" "Virtual environment missing: $venv_path"
        log "INFO" "Creating virtual environment..."

        local venv_dir=$(dirname "$venv_path")
        if ! python3.12 -m venv "$venv_dir" 2>&1 | tee -a "$LOG_FILE"; then
            print_status "$RED" "✗" "Failed to create virtual environment"
            log "ERROR" "Failed to create venv: $venv_dir"
            return 1
        fi

        print_status "$GREEN" "✓" "Virtual environment created"
        log "INFO" "Virtual environment created successfully"
    fi

    return 0
}

# Start Odoo
start_odoo() {
    if [ "$START_ODOO" = false ]; then
        log "INFO" "Odoo startup disabled, skipping..."
        return 0
    fi

    print_status "$YELLOW" "🔄" "Starting Odoo Backend..."
    log "INFO" "Starting Odoo service"

    # Check if Odoo binary exists
    if [ ! -f "$ODOO_BIN_PATH" ]; then
        print_status "$RED" "✗" "Odoo binary not found: $ODOO_BIN_PATH"
        log "ERROR" "Odoo binary missing: $ODOO_BIN_PATH"
        return 1
    fi

    # Check virtual environment
    if ! check_venv "$ODOO_ENV_BIN" "Odoo"; then
        return 1
    fi

    # Start Odoo
    (
        cd "$PROJECT_DIR"
        source "$ODOO_ENV_BIN"

        if [ "$DEBUG" = true ]; then
            "$ODOO_BIN_PATH" \
                --config="$PROJECT_DIR/odoo/odoo.conf" \
                --db-filter='^berit_odoo$' \
                --gevent-port=$ODOO_GEVENT_PORT \
                --dev=all \
                2>&1 | tee -a "$LOG_FILE"
        else
            "$ODOO_BIN_PATH" \
                --config="$PROJECT_DIR/odoo/odoo.conf" \
                --db-filter='^berit_odoo$' \
                --gevent-port=$ODOO_GEVENT_PORT \
                >> "$LOG_FILE" 2>&1
        fi
    ) &

    local odoo_pid=$!
    PIDS+=($odoo_pid)
    SERVICES+=("Odoo Backend ($odoo_pid)")

    sleep 3

    if kill -0 $odoo_pid 2>/dev/null; then
        print_status "$GREEN" "✓" "Odoo started successfully (PID: $odoo_pid)"
        log "INFO" "Odoo started with PID: $odoo_pid"
        return 0
    else
        print_status "$RED" "✗" "Failed to start Odoo"
        log "ERROR" "Odoo failed to start (PID: $odoo_pid)"
        return 1
    fi
}

# Start Django
start_django() {
    print_status "$YELLOW" "🔄" "Starting Django Portal..."
    log "INFO" "Starting Django service"

    # Check virtual environment
    if ! check_venv "$DJANGO_ENV_BIN" "Django"; then
        return 1
    fi

    # Run migrations first
    log "INFO" "Running Django migrations..."
    (
        cd "$PROJECT_DIR/django_portal"
        source "$DJANGO_ENV_BIN"

        if ! python manage.py migrate >> "$LOG_FILE" 2>&1; then
            log "WARN" "Django migrations had issues, continuing anyway..."
        else
            log "INFO" "Django migrations completed successfully"
        fi
    )

    # Start Django
    (
        cd "$PROJECT_DIR/django_portal"
        source "$DJANGO_ENV_BIN"
        export DJANGO_SETTINGS_MODULE=config.settings.development
        export DEBUG=True

        if [ "$DEBUG" = true ]; then
            python manage.py runserver 0.0.0.0:$DJANGO_PORT
        else
            python manage.py runserver 0.0.0.0:$DJANGO_PORT 2>&1 | tee -a "$LOG_FILE"
        fi
    ) &

    local django_pid=$!
    PIDS+=($django_pid)
    SERVICES+=("Django Portal ($django_pid)")

    sleep 2

    if kill -0 $django_pid 2>/dev/null; then
        print_status "$GREEN" "✓" "Django started successfully (PID: $django_pid)"
        log "INFO" "Django started with PID: $django_pid"
        return 0
    else
        print_status "$RED" "✗" "Failed to start Django"
        log "ERROR" "Django failed to start (PID: $django_pid)"
        return 1
    fi
}

# Start Celery Worker
start_celery_worker() {
    if [ "$START_CELERY" = false ]; then
        log "INFO" "Celery startup disabled, skipping..."
        return 0
    fi

    print_status "$YELLOW" "🔄" "Starting Celery Worker..."
    log "INFO" "Starting Celery Worker"

    # Check virtual environment
    if ! check_venv "$DJANGO_ENV_BIN" "Django"; then
        return 1
    fi

    # Start Celery Worker
    (
        cd "$PROJECT_DIR/django_portal"
        source "$DJANGO_ENV_BIN"

        if [ "$DEBUG" = true ]; then
            celery -A config worker --loglevel=debug --logfile="$LOG_DIR/celery_worker.log"
        else
            celery -A config worker --loglevel=info --logfile="$LOG_DIR/celery_worker.log" 2>&1 | tee -a "$LOG_FILE"
        fi
    ) &

    local celery_pid=$!
    PIDS+=($celery_pid)
    SERVICES+=("Celery Worker ($celery_pid)")

    sleep 2

    if kill -0 $celery_pid 2>/dev/null; then
        print_status "$GREEN" "✓" "Celery Worker started successfully (PID: $celery_pid)"
        log "INFO" "Celery Worker started with PID: $celery_pid"
        return 0
    else
        print_status "$RED" "✗" "Failed to start Celery Worker"
        log "ERROR" "Celery Worker failed to start (PID: $celery_pid)"
        return 1
    fi
}

# Start Celery Beat
start_celery_beat() {
    if [ "$START_CELERY" = false ]; then
        return 0
    fi

    print_status "$YELLOW" "🔄" "Starting Celery Beat Scheduler..."
    log "INFO" "Starting Celery Beat"

    # Check virtual environment
    if ! check_venv "$DJANGO_ENV_BIN" "Django"; then
        return 1
    fi

    # Start Celery Beat
    (
        cd "$PROJECT_DIR/django_portal"
        source "$DJANGO_ENV_BIN"

        if [ "$DEBUG" = true ]; then
            celery -A config beat --loglevel=debug --logfile="$LOG_DIR/celery_beat.log" --scheduler django_celery_beat.schedulers:DatabaseScheduler
        else
            celery -A config beat --loglevel=info --logfile="$LOG_DIR/celery_beat.log" --scheduler django_celery_beat.schedulers:DatabaseScheduler 2>&1 | tee -a "$LOG_FILE"
        fi
    ) &

    local beat_pid=$!
    PIDS+=($beat_pid)
    SERVICES+=("Celery Beat ($beat_pid)")

    sleep 2

    if kill -0 $beat_pid 2>/dev/null; then
        print_status "$GREEN" "✓" "Celery Beat started successfully (PID: $beat_pid)"
        log "INFO" "Celery Beat started with PID: $beat_pid"
        return 0
    else
        print_status "$RED" "✗" "Failed to start Celery Beat"
        log "ERROR" "Celery Beat failed to start (PID: $beat_pid)"
        return 1
    fi
}

# Display system status
display_status() {
    echo ""
    print_status "$GREEN" "🎉" "System startup completed!"
    log "INFO" "System startup completed successfully"

    echo ""
    echo -e "${BLUE}📊 Service Status:${NC}"
    echo -e "  ${GREEN}✓${NC} PostgreSQL: Running"
    echo -e "  ${GREEN}✓${NC} Redis: Running"
    echo -e "  ${GREEN}✓${NC} Nginx: Running"

    if [ "$START_ODOO" = true ]; then
        echo -e "  ${GREEN}✓${NC} Odoo Backend:   http://localhost:${ODOO_PORT} (PID: ${PIDS[0]})"
        echo -e "  ${GREEN}✓${NC} Odoo WebSocket: http://localhost:${ODOO_GEVENT_PORT}"
    fi

    echo ""
    echo -e "${CYAN}🌐 Access URLs:${NC}"
    echo -e "  • Django Portal: http://localhost:${DJANGO_PORT}"
    echo -e "  • Django Admin: http://localhost:${DJANGO_PORT}/admin"

    if [ "$START_ODOO" = true ]; then
        echo -e "  • Odoo Admin: http://localhost:${ODOO_PORT}/web/login"
    fi

    echo -e "  • Nginx Proxy: http://localhost"

    echo ""
    echo -e "${YELLOW}💡 Useful Commands:${NC}"
    echo -e "  • View logs: tail -f $LOG_FILE"
    echo -e "  • Celery logs: tail -f $LOG_DIR/celery_worker.log"
    echo -e "  • Check processes: ps aux | grep -E '(python|celery)'"
    echo -e "  • Stop services: Press Ctrl+C"

    echo ""
    echo -e "${RED}⚠️  Press Ctrl+C to stop all services${NC}"
    echo ""

    log "INFO" "System is ready for use"
}

# Cleanup and stop all services
cleanup() {
    echo ""
    print_status "$YELLOW" "🛑" "Stopping all services..."
    log "INFO" "Stopping all services..."

    # Kill all PIDs
    for pid in "${PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            log "INFO" "Stopping process: $pid"
            kill "$pid" 2>/dev/null || true

            # Wait a bit for graceful shutdown
            sleep 1

            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
    done

    echo ""
    print_status "$GREEN" "✓" "All services stopped"
    log "INFO" "All services stopped successfully"
    log "INFO" "Shutdown completed at $(date)"
    log "INFO" "=========================================="

    echo ""
    echo -e "${BLUE}📋 Summary:${NC}"
    echo -e "  • Log file: $LOG_FILE"
    echo -e "  • View logs: cat $LOG_FILE"
    echo ""

    exit 0
}

################################################################################
# Main Execution
################################################################################

main() {
    # Parse arguments
    parse_arguments "$@"

    # Initialize logging
    init_logging

    # Set up trap for Ctrl+C
    trap cleanup INT TERM

    print_status "$BLUE" "🚀" "Starting Berit Shalvah Financial Services System..."
    log "INFO" "Project Directory: $PROJECT_DIR"

    # Check dependencies
    if ! check_dependencies; then
        print_status "$RED" "✗" "Dependency check failed"
        log "ERROR" "System startup aborted due to missing dependencies"
        exit 1
    fi

    echo ""

    # Check and start system services
    print_status "$BLUE" "🔍" "Checking system services..."

    start_service postgresql "PostgreSQL Database"
    start_service redis "Redis Cache Server"
    start_service nginx "Nginx Reverse Proxy"
    apply_nginx_config

    echo ""
    print_status "$BLUE" "🌐" "Starting Application Services..."

    # Start application services
    if ! start_odoo; then
        log "WARN" "Odoo failed to start, continuing with other services..."
    fi

    if ! start_django; then
        print_status "$RED" "✗" "Django failed to start - cannot continue"
        log "ERROR" "Django startup failed - aborting"
        cleanup
        exit 1
    fi

    if ! start_celery_worker; then
        log "WARN" "Celery Worker failed to start"
    fi

    if ! start_celery_beat; then
        log "WARN" "Celery Beat failed to start"
    fi

    # Display status
    display_status

    # Keep running
    while true; do
        sleep 1

        # Check if any critical service has died
        for pid in "${PIDS[@]}"; do
            if ! kill -0 "$pid" 2>/dev/null; then
                log "WARN" "Process $pid has died"
            fi
        done
    done
}

# Run main function
main "$@"
