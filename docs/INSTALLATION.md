# Installation Guide

This guide provides detailed instructions for installing and setting up DevTeamAutomated in various environments.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Installation (Docker)](#quick-installation-docker)
- [Manual Installation (Python)](#manual-installation-python)
- [Production Deployment](#production-deployment)
- [Cloud Deployment](#cloud-deployment)
- [Upgrading](#upgrading)
- [Uninstallation](#uninstallation)

---

## Prerequisites

### Required Software

| Software | Minimum Version | Purpose |
|----------|----------------|---------|
| Docker | 20.10+ | Container runtime |
| Docker Compose | 2.0+ | Multi-container orchestration |
| Git | 2.30+ | Version control |
| Python | 3.12+ | Runtime (manual install only) |

### Optional Software

| Software | Purpose |
|----------|---------|
| Redis CLI | Direct Redis access for debugging |
| Make | Build automation |
| curl | API testing |

### Hardware Requirements

| Environment | CPU | Memory | Storage |
|-------------|-----|--------|---------|
| Development | 2 cores | 4 GB | 10 GB |
| Production | 4+ cores | 8+ GB | 50+ GB |

---

## Quick Installation (Docker)

The fastest way to get started is using Docker Compose.

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-org/DevTeamAutomated.git
cd DevTeamAutomated
```

### Step 2: Create Environment File

```bash
cp .env.example .env
```

### Step 3: Configure Environment (Optional)

Edit `.env` to customize settings. For testing, the defaults work out of the box:

```bash
# .env - Minimal configuration for development
REDIS_HOST=redis
REDIS_PORT=6379
NAMESPACE=audit
LLM_TEST_MODE=true
LOG_LEVEL=INFO
```

### Step 4: Start All Services

```bash
# Using Docker Compose directly
docker compose up --build

# Or using Make
make up
```

### Step 5: Verify Installation

Check that all services are running:

```bash
# List containers
docker compose ps

# Expected output:
# NAME                    STATUS
# devteamautomated-redis  Up
# devteamautomated-frontend  Up
# devteamautomated-orchestrator  Up
# devteamautomated-validator  Up
# ... (additional services)
```

Verify service health:

```bash
# Frontend API
curl http://localhost:3000/api/projects

# LLM Gateway
curl http://localhost:8000/health

# Order Intake
curl http://localhost:8080/orders/pending-validation
```

### Step 6: Access the Dashboard

Open http://localhost:3000 in your browser.

---

## Manual Installation (Python)

For development without Docker or for debugging purposes.

### Step 1: Clone and Setup Virtual Environment

```bash
git clone https://github.com/your-org/DevTeamAutomated.git
cd DevTeamAutomated

# Create virtual environment
python -m venv .venv

# Activate (Linux/macOS)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate
```

### Step 2: Install Dependencies

```bash
# Runtime dependencies
pip install -r requirements.txt

# Development dependencies (optional)
pip install -r requirements-dev.txt
```

### Step 3: Install and Start Redis

**Option A: Using Docker (Recommended)**

```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

**Option B: Native Installation**

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis

# Verify
redis-cli ping  # Should return PONG
```

### Step 4: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` for local development:

```bash
REDIS_HOST=localhost
REDIS_PORT=6379
NAMESPACE=audit
LLM_TEST_MODE=true
LOG_LEVEL=DEBUG
```

### Step 5: Run Services

Open multiple terminal windows and run each service:

**Terminal 1 - Orchestrator:**
```bash
source .venv/bin/activate
python -m services.orchestrator.main
```

**Terminal 2 - Validator:**
```bash
source .venv/bin/activate
python -m services.stream_consumer.main
```

**Terminal 3 - Worker:**
```bash
source .venv/bin/activate
python -m services.worker.main
```

**Terminal 4 - Frontend API:**
```bash
source .venv/bin/activate
uvicorn services.frontend_api.main:app --reload --port 3000
```

**Terminal 5 - LLM Gateway:**
```bash
source .venv/bin/activate
uvicorn services.llm_gateway.main:app --reload --port 8000
```

### Step 6: Verify Installation

```bash
# Test the frontend API
curl http://localhost:3000/api/projects

# Run unit tests
pytest tests/ -v
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] Set strong `REDIS_PASSWORD`
- [ ] Configure LLM API keys
- [ ] Set `LLM_TEST_MODE=false`
- [ ] Set `LOG_LEVEL=WARNING` or `INFO`
- [ ] Configure resource limits
- [ ] Set up monitoring
- [ ] Configure Redis persistence
- [ ] Set up backups

### Step 1: Create Production Environment File

```bash
cp .env.example .env.prod
```

Edit `.env.prod`:

```bash
# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your_secure_password_here

# Namespace
NAMESPACE=audit

# Consumer Configuration
CONSUMER_NAME=prod-consumer-1
BLOCK_MS=2000
IDLE_RECLAIM_MS=60000
PENDING_RECLAIM_COUNT=50

# Reliability Settings
MAX_ATTEMPTS=5
DEDUPE_TTL_SECONDS=86400
LOCK_TTL_S=120

# Logging
LOG_LEVEL=INFO

# LLM Configuration
LLM_PROVIDER_ORDER=anthropic,openai,google
LLM_TEST_MODE=false
LLM_GATEWAY_URL=http://llm_gateway:8000
LLM_TIMEOUT_S=120
LLM_MAX_RETRIES=3
LLM_CACHE_ENABLED=true
LLM_CACHE_TTL_S=3600

# API Keys (use secrets management in production)
ANTHROPIC_API_KEY=sk-ant-your-key
OPENAI_API_KEY=sk-your-key
GEMINI_API_KEY=your-key
```

### Step 2: Deploy with Production Compose

```bash
# Load production environment
export $(cat .env.prod | xargs)

# Deploy
docker compose -f docker-compose.prod.yml up -d --build
```

### Step 3: Verify Deployment

```bash
# Check service health
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Test endpoints
curl http://localhost:3000/api/projects
curl http://localhost:8000/health
```

### Step 4: Configure Monitoring

Set up health check endpoints for your monitoring system:

| Endpoint | Expected Response |
|----------|-------------------|
| `http://localhost:3000/api/projects` | 200 OK |
| `http://localhost:8000/health` | `{"status": "healthy"}` |
| `http://localhost:8080/orders/pending-validation` | 200 OK |

### Step 5: Configure Redis Persistence

The production compose file includes Redis persistence. Verify:

```bash
# Check Redis persistence
docker exec -it devteamautomated-redis redis-cli CONFIG GET appendonly
# Should return "appendonly" "yes"
```

---

## Cloud Deployment

### AWS Deployment

**Using ECS/Fargate:**

1. Push images to ECR:
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

docker tag devteamautomated-frontend:latest <account>.dkr.ecr.us-east-1.amazonaws.com/devteamautomated-frontend:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/devteamautomated-frontend:latest
```

2. Use ElastiCache for Redis
3. Deploy using ECS Task Definitions
4. Use ALB for load balancing

**Using Elastic Beanstalk:**

1. Create `Dockerrun.aws.json` from `docker-compose.prod.yml`
2. Deploy using EB CLI

### Google Cloud Deployment

**Using Cloud Run:**

```bash
# Build and push
gcloud builds submit --tag gcr.io/PROJECT-ID/devteamautomated-frontend

# Deploy
gcloud run deploy devteamautomated-frontend \
  --image gcr.io/PROJECT-ID/devteamautomated-frontend \
  --platform managed
```

Use Cloud Memorystore for Redis.

### Azure Deployment

**Using Azure Container Instances:**

```bash
az container create \
  --resource-group myResourceGroup \
  --name devteamautomated \
  --image your-registry.azurecr.io/devteamautomated-frontend \
  --ports 3000
```

Use Azure Cache for Redis.

### Kubernetes Deployment

Create Kubernetes manifests from Docker Compose:

```bash
# Install kompose
curl -L https://github.com/kubernetes/kompose/releases/download/v1.28.0/kompose-linux-amd64 -o kompose
chmod +x kompose

# Convert
./kompose convert -f docker-compose.prod.yml

# Deploy
kubectl apply -f .
```

---

## Upgrading

### Docker Upgrade

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker compose down
docker compose up --build -d

# Verify
docker compose ps
```

### Manual Upgrade

```bash
# Pull latest changes
git pull origin main

# Activate virtual environment
source .venv/bin/activate

# Update dependencies
pip install -r requirements.txt --upgrade

# Restart services
# (restart each service manually)
```

### Database Migrations

If schema changes are required:

```bash
# Check for migration scripts
ls migrations/

# Run migrations (if applicable)
python -m migrations.run
```

---

## Uninstallation

### Docker Uninstallation

```bash
# Stop and remove containers, networks, volumes
docker compose down -v --remove-orphans

# Remove images
docker rmi $(docker images 'devteamautomated*' -q)

# Remove the directory
cd ..
rm -rf DevTeamAutomated
```

### Manual Uninstallation

```bash
# Deactivate virtual environment
deactivate

# Remove virtual environment
rm -rf .venv

# Stop Redis if running locally
redis-cli shutdown

# Remove the directory
cd ..
rm -rf DevTeamAutomated
```

---

## Verification Commands

Use these commands to verify your installation:

```bash
# Check Docker services
docker compose ps

# Check Redis connectivity
redis-cli -p 6380 ping

# Check API endpoints
curl -s http://localhost:3000/api/projects | jq
curl -s http://localhost:8000/health | jq

# Run tests
make test

# View logs
make logs
```

---

## Next Steps

After installation:

1. Read the [Configuration Reference](CONFIGURATION.md) to customize settings
2. Follow the [Tool Usage Guide](TOOL_USAGE.md) for a walkthrough
3. Review the [Architecture Overview](ARCHITECTURE.md) to understand the system
4. Check [Troubleshooting](TROUBLESHOOTING.md) if you encounter issues

---

## Getting Help

- **Issues**: Open an issue on GitHub
- **Documentation**: See the [docs/](.) directory
- **Logs**: Check `docker compose logs` for debugging
