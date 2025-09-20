#!/bin/bash
# Smoke test script for Svoi server
# This script performs basic health checks and functionality tests

set -e

# Configuration
SERVER_URL="http://localhost:8080"
TCP_PORT="5221"
TIMEOUT="30"
VERBOSE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Logging function
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check server health
check_server_health() {
    log "Checking server health..."
    
    # Check if server is running
    if ! docker-compose ps | grep -q "server.*Up"; then
        error "Server container is not running"
        return 1
    fi
    
    # Check server status script
    if [ -f "check_server_status.py" ]; then
        if ! python check_server_status.py; then
            error "Server status check failed"
            return 1
        fi
    fi
    
    log "Server health check passed"
    return 0
}

# Check API endpoints
check_api_endpoints() {
    log "Checking API endpoints..."
    
    # Check if API is accessible
    if command_exists curl; then
        if ! curl -f -s --max-time $TIMEOUT "$SERVER_URL/health" >/dev/null; then
            warning "API health endpoint not accessible"
        else
            log "API health endpoint accessible"
        fi
    fi
    
    log "API endpoints check completed"
    return 0
}

# Check TCP server
check_tcp_server() {
    log "Checking TCP server..."
    
    # Check if port is listening
    if ! ss -tnlp | grep -q ":$TCP_PORT "; then
        error "TCP server not listening on port $TCP_PORT"
        return 1
    fi
    
    log "TCP server check passed"
    return 0
}

# Check database connectivity
check_database() {
    log "Checking database connectivity..."
    
    # Check if database container is running
    if ! docker-compose ps | grep -q "database.*Up"; then
        error "Database container is not running"
        return 1
    fi
    
    # Check database setup script
    if [ -f "scripts/setup_database.py" ]; then
        if ! python scripts/setup_database.py --test; then
            error "Database connectivity check failed"
            return 1
        fi
    fi
    
    log "Database connectivity check passed"
    return 0
}

# Check configuration
check_configuration() {
    log "Checking configuration..."
    
    # Check config file exists
    if [ ! -f "config.yaml" ]; then
        error "Configuration file config.yaml not found"
        return 1
    fi
    
    # Validate YAML syntax
    if command_exists python; then
        if ! python -c "import yaml; yaml.safe_load(open('config.yaml'))" 2>/dev/null; then
            error "Configuration file has invalid YAML syntax"
            return 1
        fi
    fi
    
    log "Configuration check passed"
    return 0
}

# Check Docker services
check_docker_services() {
    log "Checking Docker services..."
    
    # Check if docker-compose is available
    if ! command_exists docker-compose; then
        error "docker-compose not found"
        return 1
    fi
    
    # Check if all services are running
    if ! docker-compose ps | grep -q "Up"; then
        error "No Docker services are running"
        return 1
    fi
    
    log "Docker services check passed"
    return 0
}

# Check system resources
check_system_resources() {
    log "Checking system resources..."
    
    # Check CPU usage
    if command_exists top; then
        cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
        if (( $(echo "$cpu_usage > 90" | bc -l) )); then
            warning "High CPU usage: ${cpu_usage}%"
        fi
    fi
    
    # Check memory usage
    if command_exists free; then
        memory_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
        if (( memory_usage > 90 )); then
            warning "High memory usage: ${memory_usage}%"
        fi
    fi
    
    # Check disk space
    if command_exists df; then
        disk_usage=$(df / | tail -1 | awk '{print $5}' | cut -d'%' -f1)
        if (( disk_usage > 90 )); then
            warning "High disk usage: ${disk_usage}%"
        fi
    fi
    
    log "System resources check passed"
    return 0
}

# Check logs for errors
check_logs() {
    log "Checking logs for errors..."
    
    # Check for recent errors in Docker logs
    if command_exists docker-compose; then
        error_count=$(docker-compose logs --tail=100 | grep -i error | wc -l)
        if (( error_count > 5 )); then
            warning "High number of errors in recent logs: $error_count"
        fi
    fi
    
    # Check for recent errors in system logs
    if command_exists journalctl; then
        error_count=$(journalctl -p err --since "1 hour ago" | wc -l)
        if (( error_count > 10 )); then
            warning "High number of system errors in last hour: $error_count"
        fi
    fi
    
    log "Logs check passed"
    return 0
}

# Run smoke test
run_smoke_test() {
    log "Starting smoke test for Svoi server..."
    
    local failed_checks=0
    
    # Run all checks
    check_docker_services || ((failed_checks++))
    check_configuration || ((failed_checks++))
    check_server_health || ((failed_checks++))
    check_api_endpoints || ((failed_checks++))
    check_tcp_server || ((failed_checks++))
    check_database || ((failed_checks++))
    check_system_resources || ((failed_checks++))
    check_logs || ((failed_checks++))
    
    # Report results
    if (( failed_checks == 0 )); then
        log "All smoke tests passed!"
        return 0
    else
        error "$failed_checks smoke test(s) failed"
        return 1
    fi
}

# Main function
main() {
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -u|--url)
                SERVER_URL="$2"
                shift 2
                ;;
            -p|--port)
                TCP_PORT="$2"
                shift 2
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  -v, --verbose    Enable verbose output"
                echo "  -u, --url        Server URL (default: http://localhost:8080)"
                echo "  -p, --port       TCP port (default: 5221)"
                echo "  -t, --timeout    Timeout in seconds (default: 30)"
                echo "  -h, --help       Show this help message"
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Run smoke test
    run_smoke_test
}

# Run main function
main "$@"

