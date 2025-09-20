# Svoi Server Runbooks

This directory contains operational runbooks (SOP) for the Svoi server system.

## Structure

- `01-no-frames.md` - No frames received for N minutes
- `02-queue-spike.md` - Queue growth and overload
- `03-decode-errors-spike.md` - Decode errors spike
- `04-db-slow.md` - Database performance issues
- `05-api-5xx-spike.md` - API 5xx errors spike
- `06-release-expand-contract.md` - Release with expand/contract migrations
- `07-api-bluegreen-rollback.md` - Blue/Green rollback procedures
- `08-backup-restore-pitr.md` - PITR backup and restore
- `09-security-incident.md` - Security incident response
- `10-tenant-quota-breach.md` - Tenant quota breach handling

## Usage

Each runbook follows the format:
1. **Symptoms** - How the issue manifests
2. **Immediate Actions** - What to do in first 5-10 minutes
3. **Diagnostics** - Commands and checks to run
4. **Mitigations** - How to resolve the issue
5. **Root Cause Checklist** - Things to investigate
6. **Follow-up** - Post-incident actions

## Quick Reference

### Emergency Contacts
- **On-call Engineer**: [Contact Info]
- **Database Admin**: [Contact Info]
- **Security Team**: [Contact Info]
- **Management**: [Contact Info]

### Key Dashboards
- **SLO Overview**: [Dashboard URL]
- **CAN Pipeline**: [Dashboard URL]
- **Database Latency**: [Dashboard URL]
- **API Canary**: [Dashboard URL]
- **Security Events**: [Dashboard URL]

### Key Commands
```bash
# Check system health
python check_server_status.py

# Check deployment status
docker-compose ps

# Emergency restart
docker-compose restart

# Check logs
docker-compose logs -f
```

