# Runbook 02: Queue Spike and Overload

## Symptoms
- Queue length > 10,000 items
- High memory usage
- Database insert latency > 1000ms
- Alerts: `QueueHigh`, `MemoryHigh`
- System performance degradation

## Immediate Actions (5-10 minutes)

### 1. Check Current Status
```bash
# Check server status
python check_server_status.py

# Check memory usage
docker stats --no-stream

# Check database performance
python scripts/monitor.py --database
```

### 2. Check System Resources
```bash
# Check CPU usage
docker stats --no-stream

# Check memory usage
free -h

# Check disk I/O
iostat -x 1 5

# Check disk space
df -h
```

### 3. Check Processing Metrics
```bash
# Check queue status
python -c "from src.server import Server; s = Server(); print(s.get_queue_status())"

# Check processing rate
python scripts/monitor.py --queue

# Check error rates
grep -c "ERROR" logs/server.log | tail -10
```

## Diagnostics

### 1. Database Performance Analysis
```sql
-- Check active queries
SELECT pid, state, query_start, query 
FROM pg_stat_activity 
WHERE state = 'active' 
ORDER BY query_start;

-- Check slow queries
SELECT query, mean_time, calls, total_time
FROM pg_stat_statements 
ORDER BY mean_time DESC 
LIMIT 10;

-- Check table sizes
SELECT schemaname, tablename, 
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### 2. Queue Analysis
```bash
# Check queue composition
python -c "from src.server import Server; s = Server(); print(s.get_queue_stats())"

# Check processing rates
python scripts/monitor.py --processing

# Check memory usage by component
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### 3. System Load Analysis
```bash
# Check load average
uptime

# Check process list
ps aux --sort=-%cpu | head -20

# Check network connections
ss -tuln | wc -l

# Check file descriptors
lsof | wc -l
```

## Mitigations

### 1. Immediate Load Reduction
```bash
# Restart server to clear queues
docker-compose restart server

# Scale up server instances
docker-compose up -d --scale server=2

# Clear old data
python scripts/cleanup.py --old-data
```

### 2. Database Optimization
```sql
-- Analyze tables for better query planning
ANALYZE frames;
ANALYZE processing_errors;

-- Check and kill long-running queries
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE state = 'active' 
AND query_start < NOW() - INTERVAL '5 minutes';
```

### 3. Scale Resources
```bash
# Increase memory limits
docker-compose up -d --scale server=3

# Optimize Docker resources
docker-compose down
docker-compose up -d --scale server=2
```

### 4. Configuration Tuning
```bash
# Update config for better performance
python -c "
import yaml
config = yaml.safe_load(open('config.yaml'))
config['server']['max_workers'] = 4
config['server']['batch_size'] = 100
yaml.dump(config, open('config.yaml', 'w'))
"

# Restart with new config
docker-compose restart
```

## Root Cause Checklist

- [ ] **Database Issues**
  - [ ] Slow queries blocking inserts
  - [ ] Index bloat affecting performance
  - [ ] Connection pool exhaustion
  - [ ] Disk I/O bottlenecks

- [ ] **Processing Issues**
  - [ ] Worker processes stuck
  - [ ] Batch processing failures
  - [ ] Memory leaks in workers
  - [ ] Network timeouts

- [ ] **Load Issues**
  - [ ] Sudden traffic spike
  - [ ] Malicious traffic
  - [ ] Resource exhaustion
  - [ ] Configuration issues

- [ ] **Infrastructure Issues**
  - [ ] CPU/memory limits reached
  - [ ] Network bandwidth saturation
  - [ ] Disk space issues
  - [ ] External service degradation

## Follow-up

### 1. Performance Tuning
- [ ] Optimize database queries
- [ ] Add missing indexes
- [ ] Tune connection pool settings
- [ ] Implement query caching

### 2. Monitoring Improvements
- [ ] Add queue depth alerts
- [ ] Monitor processing patterns
- [ ] Set up capacity planning
- [ ] Implement auto-scaling

### 3. Architecture Improvements
- [ ] Implement horizontal scaling
- [ ] Add load balancing
- [ ] Optimize data processing pipeline
- [ ] Implement circuit breakers

## Related Resources

- **Dashboard**: [Server Monitor](http://localhost:3000/monitor)
- **Database**: [DB Performance](http://localhost:3000/database)
- **Monitoring**: [System Metrics](http://localhost:3000/metrics)
- **Documentation**: [Performance Guide](docs/performance.md)

## Escalation

If queue continues to grow after 15 minutes:
1. Escalate to database team
2. Consider emergency scaling
3. Implement aggressive cleanup
4. Notify management of potential service degradation

