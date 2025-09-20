# Makefile for Svoi Server
# Operational commands and automation

.PHONY: help build start stop restart status logs clean test

# Default target
help:
	@echo "Svoi Server - Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  build          - Build Docker containers"
	@echo "  start          - Start all services"
	@echo "  stop           - Stop all services"
	@echo "  restart        - Restart all services"
	@echo "  status         - Show service status"
	@echo "  logs           - Show logs"
	@echo ""
	@echo "Testing:"
	@echo "  test           - Run all tests"
	@echo "  test-client    - Run client tests"
	@echo "  test-api       - Run API tests"
	@echo "  smoke-test     - Run smoke tests"
	@echo ""
	@echo "Operations:"
	@echo "  health-check   - Check system health"
	@echo "  daily-ops      - Run daily operations"
	@echo "  backup         - Create backup"
	@echo "  restore        - Restore from backup"
	@echo ""
	@echo "Database:"
	@echo "  db-setup       - Setup database"
	@echo "  db-migrate     - Run database migrations"
	@echo "  db-reset       - Reset database"
	@echo ""
	@echo "Monitoring:"
	@echo "  monitor        - Start monitoring"
	@echo "  metrics        - Show metrics"
	@echo "  alerts         - Check alerts"
	@echo ""
	@echo "Runbooks:"
	@echo "  runbook-*      - Show specific runbook"
	@echo ""

# Development commands
build:
	docker-compose build

start:
	docker-compose up -d

stop:
	docker-compose down

restart:
	docker-compose restart

status:
	docker-compose ps

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	docker system prune -f

# Testing commands
test:
	python -m pytest tests/ -v

test-client:
	python scripts/test_client.py

test-api:
	python scripts/test_api.py

smoke-test:
	./playbooks/smoke.sh

# Health and monitoring
health-check:
	python check_server_status.py

monitor:
	python scripts/monitor.py

metrics:
	curl -s http://localhost:8080/metrics | head -20

alerts:
	@echo "Checking for active alerts..."
	@if [ -f "alerts/prometheus-rules.yml" ]; then \
		echo "Prometheus rules configured"; \
	else \
		echo "No Prometheus rules found"; \
	fi

# Database operations
db-setup:
	python scripts/setup_database.py

db-migrate:
	@echo "Database migrations not implemented yet"

db-reset:
	@echo "Resetting database..."
	docker-compose down
	docker volume rm svoi-server_postgres_data || true
	docker-compose up -d database
	sleep 10
	python scripts/setup_database.py

# Backup and restore
backup:
	@echo "Creating backup..."
	docker-compose exec database pg_dump -U postgres navtelecom_server > backup_$(shell date +%Y%m%d_%H%M%S).sql

restore:
	@echo "Restore from backup..."
	@read -p "Enter backup file name: " backup_file; \
	docker-compose exec -T database psql -U postgres navtelecom_server < $$backup_file

# Daily operations
daily-ops:
	@echo "Running daily operations..."
	@echo "1. Health check"
	python check_server_status.py
	@echo "2. Check logs for errors"
	docker-compose logs --tail=100 | grep -i error | wc -l
	@echo "3. Check disk space"
	df -h
	@echo "4. Check memory usage"
	free -h

# Runbook commands
.PHONY: runbook-no-frames runbook-queue-spike runbook-decode-errors runbook-db-slow runbook-api-5xx

runbook-no-frames:
	@echo "Opening runbook: No frames received"
	@cat runbooks/01-no-frames.md

runbook-queue-spike:
	@echo "Opening runbook: Queue spike and overload"
	@cat runbooks/02-queue-spike.md

runbook-decode-errors:
	@echo "Opening runbook: Decode errors spike"
	@cat runbooks/03-decode-errors-spike.md

runbook-db-slow:
	@echo "Opening runbook: Database slow"
	@cat runbooks/04-db-slow.md

runbook-api-5xx:
	@echo "Opening runbook: API 5xx spike"
	@cat runbooks/05-api-5xx-spike.md

# Emergency commands
emergency-restart:
	@echo "Emergency restart of all services..."
	docker-compose down
	docker-compose up -d

emergency-logs:
	@echo "Emergency log collection..."
	docker-compose logs --tail=1000 > emergency_logs_$(shell date +%Y%m%d_%H%M%S).log

emergency-status:
	@echo "Emergency status check..."
	@echo "=== Docker Status ==="
	docker-compose ps
	@echo "=== System Resources ==="
	free -h
	df -h
	@echo "=== Network ==="
	ss -tlnp | grep -E "(5221|8080|5432)"

# Configuration management
config-validate:
	@echo "Validating configuration..."
	python -c "import yaml; yaml.safe_load(open('config.yaml')); print('Config is valid')"

config-backup:
	@echo "Backing up configuration..."
	cp config.yaml config.yaml.backup.$(shell date +%Y%m%d_%H%M%S)

# Development helpers
dev-setup:
	@echo "Setting up development environment..."
	pip install -r requirements.txt
	python scripts/setup_database.py
	@echo "Development setup complete"

dev-reset:
	@echo "Resetting development environment..."
	docker-compose down -v
	docker system prune -f
	make dev-setup

# Documentation
docs:
	@echo "Available documentation:"
	@echo "- README.md - Main documentation"
	@echo "- CONSOLE_GUIDE.md - Console usage guide"
	@echo "- QUICKSTART.md - Quick start guide"
	@echo "- UNIVERSAL_SERVER_GUIDE.md - Universal server guide"
	@echo "- runbooks/ - Operational runbooks"
	@echo "- templates/ - Incident templates"

# Security
security-check:
	@echo "Running security checks..."
	@echo "1. Checking for exposed ports"
	ss -tlnp | grep -E "(5221|8080|5432)"
	@echo "2. Checking firewall status"
	ufw status || echo "UFW not available"
	@echo "3. Checking for suspicious processes"
	ps aux | grep -E "(python|postgres)" | head -10

# Performance
perf-check:
	@echo "Running performance checks..."
	@echo "1. CPU usage"
	top -bn1 | grep "Cpu(s)"
	@echo "2. Memory usage"
	free -h
	@echo "3. Disk I/O"
	iostat -x 1 1 || echo "iostat not available"
	@echo "4. Network connections"
	ss -s

# Maintenance
maintenance:
	@echo "Running maintenance tasks..."
	@echo "1. Cleaning old logs"
	find logs/ -name "*.log" -mtime +7 -delete 2>/dev/null || true
	@echo "2. Cleaning Docker"
	docker system prune -f
	@echo "3. Updating package lists"
	apt update 2>/dev/null || echo "apt not available"

# Quick actions
quick-start:
	@echo "Quick start sequence..."
	make build
	make start
	sleep 10
	make health-check

quick-stop:
	@echo "Quick stop sequence..."
	make stop
	make clean

quick-restart:
	@echo "Quick restart sequence..."
	make stop
	make start
	sleep 5
	make health-check

