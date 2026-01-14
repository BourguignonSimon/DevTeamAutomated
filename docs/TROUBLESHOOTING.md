# Troubleshooting Guide

This guide helps you diagnose and resolve common issues with DevTeamAutomated.

---

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Installation Issues](#installation-issues)
- [Docker Issues](#docker-issues)
- [Redis Issues](#redis-issues)
- [LLM Gateway Issues](#llm-gateway-issues)
- [API Issues](#api-issues)
- [Worker Issues](#worker-issues)
- [Performance Issues](#performance-issues)
- [Logging and Debugging](#logging-and-debugging)
- [Getting Help](#getting-help)

---

## Quick Diagnostics

Run these commands to quickly diagnose common issues:

```bash
# Check all services are running
docker compose ps

# Check service logs for errors
docker compose logs --tail=50 | grep -i error

# Test Redis connectivity
redis-cli -p 6380 ping

# Test API health
curl http://localhost:3000/api/projects
curl http://localhost:8000/health

# Check for DLQ entries (failed events)
redis-cli -p 6380 XLEN audit:dlq

# View recent events
redis-cli -p 6380 XRANGE audit:events - + COUNT 10
```

---

## Installation Issues

### Python Version Mismatch

**Symptom:**
```
ERROR: Python 3.12 or higher is required
```

**Solution:**
```bash
# Check Python version
python --version

# Install Python 3.12+
# macOS
brew install python@3.12

# Ubuntu
sudo apt install python3.12

# Use pyenv
pyenv install 3.12.0
pyenv local 3.12.0
```

---

### Missing Dependencies

**Symptom:**
```
ModuleNotFoundError: No module named 'redis'
```

**Solution:**
```bash
# Install dependencies
pip install -r requirements.txt

# If in virtual environment, ensure it's activated
source .venv/bin/activate
pip install -r requirements.txt
```

---

### Docker Compose Version

**Symptom:**
```
ERROR: Version in "./docker-compose.yml" is unsupported
```

**Solution:**
```bash
# Check Docker Compose version
docker compose version

# Update Docker Desktop (recommended)
# Or install standalone Docker Compose v2
```

---

## Docker Issues

### Containers Not Starting

**Symptom:**
```
Container devteamautomated-orchestrator exited with code 1
```

**Solution:**
```bash
# Check container logs
docker compose logs orchestrator

# Common causes:
# 1. Redis not ready - containers start before Redis
docker compose down
docker compose up redis -d
sleep 5
docker compose up -d

# 2. Port conflicts
docker compose ps
lsof -i :3000  # Check if port is in use

# 3. Rebuild images
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

### Port Already in Use

**Symptom:**
```
Error: port 3000 already in use
```

**Solution:**
```bash
# Find what's using the port
lsof -i :3000

# Kill the process
kill -9 <PID>

# Or change the port in docker-compose.yml
ports:
  - "3001:3000"  # Use 3001 instead
```

---

### Volume Permission Issues

**Symptom:**
```
Permission denied: '/storage'
```

**Solution:**
```bash
# Fix permissions
sudo chown -R $USER:$USER ./storage

# Or run with correct user
docker compose down
DOCKER_USER=$(id -u):$(id -g) docker compose up -d
```

---

### Out of Disk Space

**Symptom:**
```
no space left on device
```

**Solution:**
```bash
# Clean up Docker
docker system prune -a
docker volume prune

# Check disk usage
df -h
docker system df
```

---

## Redis Issues

### Connection Refused

**Symptom:**
```
redis.exceptions.ConnectionError: Error connecting to redis:6379
```

**Solution:**
```bash
# Check if Redis is running
docker compose ps redis

# Verify Redis is accessible
redis-cli -p 6380 ping

# Check Redis logs
docker compose logs redis

# Restart Redis
docker compose restart redis
```

---

### Authentication Failed

**Symptom:**
```
NOAUTH Authentication required
```

**Solution:**
```bash
# If REDIS_PASSWORD is set, use it
redis-cli -p 6380 -a your_password ping

# Check .env file
grep REDIS_PASSWORD .env

# Ensure services have the password
docker compose down
docker compose up -d
```

---

### Consumer Group Issues

**Symptom:**
```
NOGROUP No such consumer group
```

**Solution:**
```bash
# Create the consumer group
redis-cli -p 6380 XGROUP CREATE audit:events my_group 0-0 MKSTREAM

# List existing groups
redis-cli -p 6380 XINFO GROUPS audit:events

# Destroy and recreate if needed
redis-cli -p 6380 XGROUP DESTROY audit:events my_group
redis-cli -p 6380 XGROUP CREATE audit:events my_group 0-0 MKSTREAM
```

---

### Stream Too Large

**Symptom:**
```
OOM command not allowed when used memory > 'maxmemory'
```

**Solution:**
```bash
# Check stream length
redis-cli -p 6380 XLEN audit:events

# Trim old entries
redis-cli -p 6380 XTRIM audit:events MAXLEN ~ 10000

# Increase Redis memory (docker-compose.yml)
redis:
  command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

---

## LLM Gateway Issues

### All Providers Failed

**Symptom:**
```
503 Service Unavailable: All LLM providers failed
```

**Solution:**
```bash
# Check provider status
curl http://localhost:8000/health

# Verify API keys are set
grep -E "API_KEY" .env

# Test mode should work without keys
# Ensure LLM_TEST_MODE=true for development

# Check rate limits
curl http://localhost:8000/v1/usage
```

---

### Invalid API Key

**Symptom:**
```
401 Unauthorized: Invalid API key
```

**Solution:**
```bash
# Verify key is correct
echo $ANTHROPIC_API_KEY

# Check key format
# Anthropic: sk-ant-api03-...
# OpenAI: sk-...
# Gemini: AIza...

# Regenerate key if needed at provider console
```

---

### Rate Limited

**Symptom:**
```
429 Too Many Requests
```

**Solution:**
```bash
# Wait and retry (automatic with backoff)

# Check current usage
curl http://localhost:8000/v1/usage

# Reduce request rate in config
# config/llm_config.yaml
rate_limiting:
  providers:
    anthropic:
      requests_per_minute: 30  # Reduce from 60
```

---

### Timeout Errors

**Symptom:**
```
Request timed out after 120 seconds
```

**Solution:**
```bash
# Increase timeout
# .env
LLM_TIMEOUT_S=300

# Or in config/llm_config.yaml
global:
  timeout_seconds: 300

# Restart services
docker compose restart llm_gateway
```

---

## API Issues

### 404 Not Found

**Symptom:**
```
{"error": {"code": "NOT_FOUND", "message": "Project not found"}}
```

**Solution:**
```bash
# Verify resource exists
curl http://localhost:3000/api/projects

# Check if project ID is correct
curl http://localhost:3000/api/projects/YOUR_PROJECT_ID/status

# Projects are stored in Redis
redis-cli -p 6380 SMEMBERS audit:backlog:projects
```

---

### 400 Bad Request

**Symptom:**
```
{"error": {"code": "VALIDATION_ERROR", "message": "Invalid input"}}
```

**Solution:**
```bash
# Check request body format
# Ensure Content-Type is set
curl -X POST http://localhost:3000/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name": "Test", "description": "Test project"}'

# Validate JSON
echo '{"name": "Test"}' | jq .
```

---

### CORS Errors

**Symptom:**
```
Access to fetch has been blocked by CORS policy
```

**Solution:**
```python
# In services/frontend_api/main.py, CORS is already configured
# If accessing from different origin, update:

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://yourdomain.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Worker Issues

### Worker Not Processing Events

**Symptom:**
Events are published but workers don't process them.

**Solution:**
```bash
# Check worker logs
docker compose logs time_waste_worker

# Verify consumer group membership
redis-cli -p 6380 XINFO CONSUMERS audit:events time_waste_workers

# Check pending messages
redis-cli -p 6380 XPENDING audit:events time_waste_workers

# Restart workers
docker compose restart time_waste_worker
```

---

### Events Going to DLQ

**Symptom:**
```
Events appear in audit:dlq instead of being processed
```

**Solution:**
```bash
# Check DLQ entries
redis-cli -p 6380 XRANGE audit:dlq - + COUNT 5

# Common causes:
# 1. Schema validation failure
# 2. Missing required fields
# 3. Worker crash during processing

# View DLQ entry details
redis-cli -p 6380 XRANGE audit:dlq - + COUNT 1

# Retry failed events (manual)
# Read from DLQ and republish to main stream
```

---

### Duplicate Processing

**Symptom:**
Same event processed multiple times.

**Solution:**
```bash
# Check idempotence TTL
grep DEDUPE_TTL .env

# Increase TTL if needed
DEDUPE_TTL_SECONDS=172800  # 48 hours

# Verify idempotence keys exist
redis-cli -p 6380 KEYS "audit:processed:*"

# Clear idempotence for testing
redis-cli -p 6380 DEL "audit:processed:event:YOUR_EVENT_ID"
```

---

## Performance Issues

### Slow Event Processing

**Symptom:**
Events take too long to process.

**Solution:**
```bash
# Check processing metrics
docker compose logs orchestrator | grep "processed in"

# Increase worker replicas
# docker-compose.yml
time_waste_worker:
  deploy:
    replicas: 3

# Check Redis performance
redis-cli -p 6380 INFO stats

# Check LLM latency
curl http://localhost:8000/v1/usage
```

---

### High Memory Usage

**Symptom:**
Services consuming excessive memory.

**Solution:**
```bash
# Check container memory
docker stats

# Set memory limits
# docker-compose.yml
services:
  orchestrator:
    deploy:
      resources:
        limits:
          memory: 1G

# Clear Redis caches
redis-cli -p 6380 FLUSHDB  # WARNING: Deletes all data
```

---

### High CPU Usage

**Symptom:**
CPU constantly at 100%.

**Solution:**
```bash
# Identify the service
docker stats

# Check for tight polling loops
# Increase BLOCK_MS
BLOCK_MS=5000  # 5 seconds

# Check for retry storms
docker compose logs --tail=100 | grep -i "retry"
```

---

## Logging and Debugging

### Enable Debug Logging

```bash
# Set in .env
LOG_LEVEL=DEBUG

# Restart services
docker compose restart

# View debug logs
docker compose logs -f | grep -i debug
```

---

### View Specific Service Logs

```bash
# Single service
docker compose logs -f orchestrator

# Multiple services
docker compose logs -f orchestrator worker

# With timestamps
docker compose logs -f --timestamps orchestrator

# Last N lines
docker compose logs --tail=100 orchestrator
```

---

### Inspect Redis Data

```bash
# Connect to Redis CLI
redis-cli -p 6380

# List all keys
KEYS *

# View stream info
XINFO STREAM audit:events

# View consumer groups
XINFO GROUPS audit:events

# View pending messages
XPENDING audit:events orchestrator_group

# View backlog items
KEYS "audit:backlog:*"
GET "audit:backlog:PROJECT_ID:ITEM_ID"
```

---

### Enable LLM Request Logging

```yaml
# config/llm_config.yaml
global:
  logging_enabled: true
  log_level: DEBUG
```

---

### Trace Event Flow

```bash
# Find events by correlation ID
CORRELATION_ID="your-correlation-id"

# Search in events stream
redis-cli -p 6380 XRANGE audit:events - + | grep $CORRELATION_ID

# Check DLQ
redis-cli -p 6380 XRANGE audit:dlq - + | grep $CORRELATION_ID
```

---

## Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Service not running | Start Docker Compose |
| `NOAUTH` | Missing Redis password | Set `REDIS_PASSWORD` |
| `Invalid API key` | Wrong or expired key | Check provider console |
| `Rate limited` | Too many requests | Wait or reduce rate |
| `Schema validation failed` | Invalid event format | Check event structure |
| `No such consumer group` | Group not created | Create with `XGROUP CREATE` |
| `Timeout` | Slow LLM response | Increase `LLM_TIMEOUT_S` |
| `Out of memory` | Memory limit reached | Increase limits or scale |

---

## Getting Help

### Before Asking for Help

1. Check this troubleshooting guide
2. Search existing GitHub issues
3. Review service logs
4. Try restarting services
5. Test with `LLM_TEST_MODE=true`

### Information to Include

When reporting issues, include:

```
1. DevTeamAutomated version (git commit)
2. Operating system
3. Docker/Docker Compose version
4. Relevant error messages
5. Steps to reproduce
6. Configuration (sanitized - no API keys)
7. Service logs
```

### Resources

- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: [docs/](.)
- **Changelog**: [CHANGELOG.md](../CHANGELOG.md)

---

## See Also

- [Installation Guide](INSTALLATION.md)
- [Configuration Reference](CONFIGURATION.md)
- [Architecture Overview](ARCHITECTURE.md)
