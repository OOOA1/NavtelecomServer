# Runbook 01: No Frames Received

## Symptoms
- No CAN frames received for > 10 minutes
- Dashboard shows `frames/sec = 0`
- Alerts: `NoFrames` triggered
- Users report missing telemetry data

## Immediate Actions (5-10 minutes)

### 1. Check System Health
```bash
# Check server status
python check_server_status.py

# Check Docker containers
docker-compose ps

# Check server logs
docker-compose logs server
```

### 2. Check Network Connectivity
```bash
# Check if server is listening
netstat -tlnp | grep :5221

# Check firewall rules
ufw status
iptables -L

# Check network interfaces
ip addr show
```

### 3. Check Logs
```bash
# Check server logs
docker-compose logs -f server

# Check system logs for errors
journalctl -p err -n 50 --no-pager

# Check for connection errors
grep -i "connection" logs/server.log | tail -20
```

## Diagnostics

### 1. Check Frame Processing
```sql
-- Check recent frames in database
SELECT COUNT(*), MAX(timestamp) 
FROM frames 
WHERE timestamp > NOW() - INTERVAL '1 hour';

-- Check for processing errors
SELECT COUNT(*), error_type 
FROM processing_errors 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY error_type;
```

### 2. Check Network Configuration
```bash
# Check DNS resolution
nslookup your-server-domain.com

# Check routing
ip route show

# Check network statistics
netstat -i
ss -s
```

### 3. Check Device Connectivity
```bash
# Check active connections
ss -tnp | grep 5221

# Check connection attempts
grep "connection" logs/server.log | tail -20

# Check server configuration
cat config.yaml
```

## Mitigations

### 1. Restart Services
```bash
# Restart server container
docker-compose restart server

# Restart all services
docker-compose restart

# Check service status
docker-compose ps
```

### 2. Check Configuration
```bash
# Verify config file
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Check environment variables
docker-compose config

# Validate server settings
python -c "from src.config import Config; print(Config())"
```

### 3. Network Troubleshooting
```bash
# Temporarily disable firewall for testing
ufw disable

# Check port binding
docker-compose logs server | grep -i "listening"

# Test local connectivity
telnet localhost 5221
```

### 4. Database Connectivity
```bash
# Check database connection
python scripts/setup_database.py --test

# Check database logs
docker-compose logs database

# Verify database schema
python -c "from src.database import Database; db = Database(); print(db.test_connection())"
```

## Root Cause Checklist

- [ ] **Network Issues**
  - [ ] DNS resolution working
  - [ ] Firewall rules correct
  - [ ] Port 5221 accessible
  - [ ] Network interfaces up

- [ ] **Service Issues**
  - [ ] Server container running
  - [ ] Database accessible
  - [ ] Configuration valid
  - [ ] Logs show no errors

- [ ] **Device Issues**
  - [ ] Devices connected to network
  - [ ] Devices sending data
  - [ ] Device configuration correct
  - [ ] Device authentication working

- [ ] **Infrastructure Issues**
  - [ ] Server resources (CPU, memory, disk)
  - [ ] Network bandwidth
  - [ ] Database performance
  - [ ] External dependencies

## Follow-up

### 1. Post-Incident Actions
- [ ] Update monitoring thresholds if needed
- [ ] Review server configuration
- [ ] Check device configurations
- [ ] Update documentation

### 2. Prevention Measures
- [ ] Set up additional monitoring
- [ ] Implement health checks
- [ ] Create backup infrastructure
- [ ] Regular connectivity tests

### 3. Documentation Updates
- [ ] Update runbook based on lessons learned
- [ ] Document new troubleshooting steps
- [ ] Update contact information
- [ ] Share knowledge with team

## Related Resources

- **Dashboard**: [Server Status](http://localhost:3000/dashboard)
- **Logs**: [Server Logs](logs/server.log)
- **Configuration**: [config.yaml](config.yaml)
- **Documentation**: [README.md](README.md)

## Escalation

If issue persists after 30 minutes:
1. Escalate to senior engineer
2. Contact network team
3. Consider switching to backup infrastructure
4. Notify management if customer impact is high

