# Configuration Reference

This document provides a complete reference for all configuration options in DevTeamAutomated.

---

## Table of Contents

- [Configuration Overview](#configuration-overview)
- [Environment Variables](#environment-variables)
  - [Redis Configuration](#redis-configuration)
  - [Namespace Configuration](#namespace-configuration)
  - [Consumer Configuration](#consumer-configuration)
  - [Stream Processing Settings](#stream-processing-settings)
  - [Reliability Settings](#reliability-settings)
  - [Logging Configuration](#logging-configuration)
  - [LLM Gateway Configuration](#llm-gateway-configuration)
  - [LLM API Keys](#llm-api-keys)
  - [Local LLM Configuration](#local-llm-configuration)
  - [Service-Specific Settings](#service-specific-settings)
- [LLM Configuration File](#llm-configuration-file)
  - [Global Settings](#global-settings)
  - [Provider Configurations](#provider-configurations)
  - [Agent Overrides](#agent-overrides)
  - [Task Type Overrides](#task-type-overrides)
  - [Rate Limiting](#rate-limiting)
  - [Cost Tracking](#cost-tracking)
- [Docker Compose Configuration](#docker-compose-configuration)
- [Configuration Best Practices](#configuration-best-practices)

---

## Configuration Overview

DevTeamAutomated uses a layered configuration system:

1. **Environment Variables** (`.env`) - Core infrastructure settings
2. **LLM Configuration** (`config/llm_config.yaml`) - LLM provider and model settings
3. **Docker Compose** (`docker-compose.yml`) - Service orchestration and resource limits

**Priority Order:**
```
Environment Variables > LLM Config File > Default Values
```

---

## Environment Variables

Create a `.env` file in the project root (copy from `.env.example`):

```bash
cp .env.example .env
```

### Redis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `redis` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `REDIS_DB` | `0` | Redis database index |
| `REDIS_PASSWORD` | (none) | Redis password (required in production) |

**Example:**
```bash
# Development
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Production
REDIS_HOST=redis.internal
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_secure_password_here
```

**Notes:**
- In Docker, Redis is exposed on port `6380` (external) mapped to `6379` (internal)
- Always set `REDIS_PASSWORD` in production environments
- Redis password should be at least 32 characters with mixed case, numbers, and symbols

---

### Namespace Configuration

The namespace determines the prefix for all Redis keys and stream names.

| Variable | Default | Description |
|----------|---------|-------------|
| `NAMESPACE` | `audit` | Base namespace for all keys and streams |
| `STREAM_NAME` | `{namespace}:events` | Main event stream name |
| `DLQ_STREAM` | `{namespace}:dlq` | Dead letter queue stream name |
| `KEY_PREFIX` | `{namespace}` | Prefix for Redis keys |
| `TRACE_PREFIX` | `{namespace}:trace` | Prefix for trace data |
| `METRICS_PREFIX` | `{namespace}:metrics` | Prefix for metrics data |
| `IDEMPOTENCE_PREFIX` | `{namespace}:processed` | Prefix for idempotence tracking |

**Preset Namespaces:**

| Namespace | Use Case |
|-----------|----------|
| `audit` | Financial audit workflows (default) |
| `healthcare` | Clinical and healthcare workflows |
| `finserv` | Financial services automation |
| `manufacturing` | Production and manufacturing |
| `devsecops` | Security review workflows |
| `cicd` | CI/CD pipeline automation |

**Example:**
```bash
# Use healthcare namespace
NAMESPACE=healthcare

# Or customize individual prefixes
NAMESPACE=custom
STREAM_NAME=custom:events
DLQ_STREAM=custom:dlq
KEY_PREFIX=custom
```

---

### Consumer Configuration

Settings for Redis Stream consumers.

| Variable | Default | Description |
|----------|---------|-------------|
| `CONSUMER_GROUP` | `{namespace}_stream_consumers` | Consumer group name |
| `CONSUMER_NAME` | `consumer-1` | Consumer instance identifier |

**Example:**
```bash
CONSUMER_GROUP=audit_stream_consumers
CONSUMER_NAME=worker-pod-1
```

**Notes:**
- Each service instance should have a unique `CONSUMER_NAME`
- Use pod names or instance IDs in Kubernetes/container environments

---

### Stream Processing Settings

Control how streams are processed.

| Variable | Default | Description |
|----------|---------|-------------|
| `BLOCK_MS` | `2000` | XREAD block duration in milliseconds |
| `IDLE_RECLAIM_MS` | `60000` | Minimum idle time before reclaiming pending messages |
| `PENDING_RECLAIM_COUNT` | `50` | Maximum pending messages to reclaim per iteration |

**Example:**
```bash
# Fast polling for low latency
BLOCK_MS=1000
IDLE_RECLAIM_MS=30000
PENDING_RECLAIM_COUNT=100

# Conservative settings for high load
BLOCK_MS=5000
IDLE_RECLAIM_MS=120000
PENDING_RECLAIM_COUNT=25
```

**Tuning Guidelines:**

| Scenario | BLOCK_MS | IDLE_RECLAIM_MS | PENDING_RECLAIM_COUNT |
|----------|----------|-----------------|----------------------|
| Low latency | 500-1000 | 30000 | 100 |
| Balanced | 2000 | 60000 | 50 |
| High throughput | 5000 | 120000 | 25 |

---

### Reliability Settings

Configure retry behavior and deduplication.

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_ATTEMPTS` | `5` | Maximum retry attempts before DLQ |
| `DEDUPE_TTL_SECONDS` | `86400` | TTL for idempotence tracking (24 hours) |
| `IDEMPOTENCE_TTL_S` | `86400` | Alias for DEDUPE_TTL_SECONDS |
| `LOCK_TTL_S` | `120` | TTL for distributed locks in seconds |

**Example:**
```bash
# More retries for unreliable networks
MAX_ATTEMPTS=10
DEDUPE_TTL_SECONDS=172800  # 48 hours

# Shorter locks for faster recovery
LOCK_TTL_S=60
```

**Retry Behavior:**
- Events are retried up to `MAX_ATTEMPTS` times
- After max attempts, events are moved to DLQ
- Idempotence keys expire after `DEDUPE_TTL_SECONDS`

---

### Logging Configuration

| Variable | Default | Options | Description |
|----------|---------|---------|-------------|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Logging verbosity |

**Example:**
```bash
# Development - verbose logging
LOG_LEVEL=DEBUG

# Production - reduce log volume
LOG_LEVEL=WARNING
```

**Log Levels:**

| Level | Use Case |
|-------|----------|
| `DEBUG` | Development, troubleshooting |
| `INFO` | Normal operation monitoring |
| `WARNING` | Production (important events only) |
| `ERROR` | Production (errors only) |
| `CRITICAL` | Alerting systems |

---

### LLM Gateway Configuration

Settings for the LLM abstraction layer.

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER_ORDER` | `anthropic,openai,google,local` | Fallback order (comma-separated) |
| `LLM_TEST_MODE` | `true` | Use mock responses instead of real APIs |
| `LLM_GATEWAY_URL` | `http://llm_gateway:8000` | LLM Gateway service URL |
| `LLM_CONFIG_PATH` | `/app/config/llm_config.yaml` | Path to LLM config file |
| `LLM_TIMEOUT_S` | `120` | Request timeout in seconds |
| `LLM_MAX_RETRIES` | `3` | Maximum retries per provider |
| `LLM_CACHE_ENABLED` | `true` | Enable response caching |
| `LLM_CACHE_TTL_S` | `3600` | Cache TTL in seconds |

**Example:**
```bash
# Development - use mocks
LLM_TEST_MODE=true
LLM_PROVIDER_ORDER=anthropic,openai,google,local

# Production - use real APIs with Anthropic preference
LLM_TEST_MODE=false
LLM_PROVIDER_ORDER=anthropic,openai,google
LLM_TIMEOUT_S=180
LLM_CACHE_ENABLED=true
```

---

### LLM API Keys

Required when `LLM_TEST_MODE=false`.

| Variable | Provider | Where to Get |
|----------|----------|--------------|
| `ANTHROPIC_API_KEY` | Anthropic Claude | https://console.anthropic.com/ |
| `OPENAI_API_KEY` | OpenAI GPT | https://platform.openai.com/api-keys |
| `OPENAI_ORG_ID` | OpenAI (optional) | https://platform.openai.com/organization |
| `GEMINI_API_KEY` | Google Gemini | https://makersuite.google.com/app/apikey |

**Example:**
```bash
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_ORG_ID=org-xxxxxxxxxxxx
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Security Notes:**
- Never commit API keys to version control
- Use secrets management (Vault, AWS Secrets Manager, etc.) in production
- Rotate keys regularly
- Set usage limits on API provider dashboards

---

### Local LLM Configuration

For using local LLM servers (Ollama, LocalAI, vLLM, etc.).

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_LLM_URL` | `http://localhost:11434` | Local LLM server URL |
| `LOCAL_LLM_SERVER_TYPE` | `ollama` | Server type (see options below) |
| `LOCAL_LLM_API_KEY` | (none) | API key if server requires auth |

**Server Types:**

| Type | Description | Default Port |
|------|-------------|--------------|
| `ollama` | Ollama server | 11434 |
| `localai` | LocalAI server | 8080 |
| `lmstudio` | LM Studio server | 1234 |
| `vllm` | vLLM server | 8000 |
| `openai_compatible` | Any OpenAI-compatible API | varies |

**Example:**
```bash
# Ollama
LOCAL_LLM_URL=http://localhost:11434
LOCAL_LLM_SERVER_TYPE=ollama

# vLLM
LOCAL_LLM_URL=http://gpu-server:8000
LOCAL_LLM_SERVER_TYPE=vllm
LOCAL_LLM_API_KEY=my-vllm-key
```

---

### Service-Specific Settings

Override settings for specific services.

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_DIR` | `/storage` | Storage directory for Order Intake Agent |
| `ORCHESTRATOR_LOCK_TTL_S` | `300` | Lock TTL for orchestrator |
| `ORCHESTRATOR_IDEMPOTENCE_TTL_S` | `604800` | Idempotence TTL for orchestrator |
| `WORKER_TIMEOUT_S` | `300` | Worker timeout |

---

## LLM Configuration File

The `config/llm_config.yaml` file provides detailed LLM configuration.

### Global Settings

```yaml
global:
  # Default provider when not specified
  default_provider: anthropic

  # Fallback order when primary fails
  fallback_order:
    - anthropic
    - openai
    - google
    - local

  # Request timeout (seconds)
  timeout_seconds: 120

  # Maximum retries before fallback
  max_retries: 3

  # Retry delay configuration
  retry_base_delay_seconds: 1
  retry_max_delay_seconds: 30

  # Response caching
  cache_enabled: true
  cache_ttl_seconds: 3600

  # Logging (disable in production for privacy)
  logging_enabled: true
  log_level: INFO
```

---

### Provider Configurations

#### Anthropic (Claude)

```yaml
providers:
  anthropic:
    enabled: true
    api_key: ${ANTHROPIC_API_KEY}
    base_url: https://api.anthropic.com
    api_version: "2023-06-01"
    default_model: claude-3-5-sonnet-20241022

    models:
      claude-3-5-sonnet-20241022:
        max_tokens: 8192
        temperature: 0.7
        supports_vision: true
        supports_tools: true
        context_window: 200000
        cost_per_1k_input_tokens: 0.003
        cost_per_1k_output_tokens: 0.015

      claude-3-5-haiku-20241022:
        max_tokens: 8192
        temperature: 0.7
        supports_vision: true
        supports_tools: true
        context_window: 200000
        cost_per_1k_input_tokens: 0.001
        cost_per_1k_output_tokens: 0.005

      claude-3-opus-20240229:
        max_tokens: 4096
        temperature: 0.7
        supports_vision: true
        supports_tools: true
        context_window: 200000
        cost_per_1k_input_tokens: 0.015
        cost_per_1k_output_tokens: 0.075
```

#### OpenAI (GPT)

```yaml
  openai:
    enabled: true
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
    organization_id: ${OPENAI_ORG_ID}
    default_model: gpt-4o

    models:
      gpt-4o:
        max_tokens: 16384
        temperature: 0.7
        supports_vision: true
        supports_tools: true
        context_window: 128000
        cost_per_1k_input_tokens: 0.005
        cost_per_1k_output_tokens: 0.015

      gpt-4o-mini:
        max_tokens: 16384
        temperature: 0.7
        supports_vision: true
        supports_tools: true
        context_window: 128000
        cost_per_1k_input_tokens: 0.00015
        cost_per_1k_output_tokens: 0.0006

      o1-preview:
        max_tokens: 32768
        temperature: 1.0  # Fixed for o1 models
        supports_vision: false
        supports_tools: false
        context_window: 128000
```

#### Google (Gemini)

```yaml
  google:
    enabled: true
    api_key: ${GEMINI_API_KEY}
    base_url: https://generativelanguage.googleapis.com/v1beta
    default_model: gemini-1.5-pro

    models:
      gemini-1.5-pro:
        max_tokens: 8192
        temperature: 0.7
        supports_vision: true
        supports_tools: true
        context_window: 2097152

      gemini-1.5-flash:
        max_tokens: 8192
        temperature: 0.7
        supports_vision: true
        supports_tools: true
        context_window: 1048576

    settings:
      safety_settings:
        harassment: BLOCK_MEDIUM_AND_ABOVE
        hate_speech: BLOCK_MEDIUM_AND_ABOVE
        sexually_explicit: BLOCK_MEDIUM_AND_ABOVE
        dangerous_content: BLOCK_MEDIUM_AND_ABOVE
```

#### Local LLM

```yaml
  local:
    enabled: false  # Enable when using local LLM
    server_type: ollama
    base_url: ${LOCAL_LLM_URL:-http://localhost:11434}
    api_key: ${LOCAL_LLM_API_KEY}
    default_model: llama3.1:8b

    models:
      llama3.1:8b:
        max_tokens: 4096
        temperature: 0.7
        supports_vision: false
        supports_tools: true
        context_window: 131072

      mistral:7b:
        max_tokens: 4096
        temperature: 0.7
        context_window: 32768

      codellama:13b:
        max_tokens: 4096
        temperature: 0.2  # Lower for code
        context_window: 16384

    settings:
      timeout_seconds: 300  # Local models may be slower
      gpu_memory_utilization: 0.9
      tensor_parallel_size: 1
```

---

### Agent Overrides

Configure specific models for specific agents:

```yaml
agent_overrides:
  # Use Claude for complex analysis
  pattern_agent:
    provider: anthropic
    model: claude-3-5-sonnet-20241022
    temperature: 0.3
    max_tokens: 4096

  # Use GPT-4o-mini for fast classification
  classifier_agent:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.2
    max_tokens: 2048

  # Use Gemini Flash for analytics
  support_analytics_agent:
    provider: google
    model: gemini-1.5-flash
    temperature: 0.2
    max_tokens: 4096

  # Development tasks need capable models
  dev_worker:
    provider: anthropic
    model: claude-3-5-sonnet-20241022
    temperature: 0.3
    max_tokens: 8192
```

**Available Agents:**

| Agent | Default Provider | Use Case |
|-------|------------------|----------|
| `pattern_agent` | anthropic | Pattern detection |
| `extraction_agent` | anthropic | Data extraction |
| `classifier_agent` | openai | Classification |
| `remediation_agent` | anthropic | Issue remediation |
| `report_agent` | anthropic | Report generation |
| `editor_agent` | anthropic | Document editing |
| `style_keeper_agent` | anthropic | Style consistency |
| `parser_agent` | openai | Parsing |
| `writer_agent` | anthropic | Content writing |
| `support_context_agent` | openai | Context retrieval |
| `support_answer_agent` | anthropic | Answer generation |
| `support_analytics_agent` | google | Analytics |
| `admin_classifier_agent` | openai | Task classification |
| `admin_executor_agent` | anthropic | Task execution |
| `dev_worker` | anthropic | Development tasks |
| `test_worker` | anthropic | Testing tasks |
| `requirements_manager` | anthropic | Requirements management |

---

### Task Type Overrides

Configure models based on task type:

```yaml
task_type_overrides:
  code_generation:
    provider: anthropic
    model: claude-3-5-sonnet-20241022
    temperature: 0.2
    max_tokens: 8192

  code_review:
    provider: anthropic
    model: claude-3-5-sonnet-20241022
    temperature: 0.3

  text_analysis:
    provider: openai
    model: gpt-4o
    temperature: 0.3

  summarization:
    provider: google
    model: gemini-1.5-flash
    temperature: 0.3

  classification:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.1

  reasoning:
    provider: openai
    model: o1-mini
    temperature: 1.0  # Fixed for o1
```

---

### Rate Limiting

Prevent API quota exhaustion:

```yaml
rate_limiting:
  enabled: true

  providers:
    anthropic:
      requests_per_minute: 60
      tokens_per_minute: 100000

    openai:
      requests_per_minute: 60
      tokens_per_minute: 150000

    google:
      requests_per_minute: 60
      tokens_per_minute: 120000

    local:
      requests_per_minute: 100
      tokens_per_minute: 1000000
```

---

### Cost Tracking

Monitor and limit API spending:

```yaml
cost_tracking:
  enabled: true

  # Budget limits (USD)
  daily_budget: 100.0
  monthly_budget: 2000.0

  # Alert when reaching this percentage
  alert_at_percentage: 80

  # Tracking dimensions
  track_by_agent: true
  track_by_task_type: true
  track_by_project: true
```

---

## Docker Compose Configuration

### Development (docker-compose.yml)

Key service configurations:

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"

  frontend:
    build:
      context: .
      dockerfile: services/frontend_api/Dockerfile
    ports:
      - "3000:3000"
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379

  llm_gateway:
    build:
      context: .
      dockerfile: services/llm_gateway/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - LLM_TEST_MODE=true
```

### Production (docker-compose.prod.yml)

Additional production settings:

```yaml
services:
  redis:
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data

  frontend:
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M
      replicas: 2
    restart: unless-stopped

  orchestrator:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
    restart: unless-stopped
```

---

## Configuration Best Practices

### Development

```bash
# .env for development
REDIS_HOST=redis
REDIS_PORT=6379
NAMESPACE=audit
LLM_TEST_MODE=true
LOG_LEVEL=DEBUG
```

### Production

```bash
# .env for production
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=<secure-password>
NAMESPACE=audit
LLM_TEST_MODE=false
LLM_PROVIDER_ORDER=anthropic,openai,google
LOG_LEVEL=INFO
ANTHROPIC_API_KEY=<api-key>
OPENAI_API_KEY=<api-key>
```

### Security Checklist

- [ ] `REDIS_PASSWORD` set and strong
- [ ] API keys stored securely (not in code)
- [ ] `LLM_TEST_MODE=false` in production
- [ ] `LOG_LEVEL` set to `INFO` or higher
- [ ] Logging disabled in `llm_config.yaml` for privacy
- [ ] Rate limiting enabled
- [ ] Cost tracking enabled with alerts

### Performance Tuning

| Scenario | Recommended Settings |
|----------|---------------------|
| Low latency | `BLOCK_MS=500`, fast models |
| High throughput | `PENDING_RECLAIM_COUNT=100`, worker replicas |
| Cost optimization | Cheaper models, caching enabled |
| Reliability | `MAX_ATTEMPTS=10`, multiple providers |

---

## See Also

- [Installation Guide](INSTALLATION.md)
- [Architecture Overview](ARCHITECTURE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
