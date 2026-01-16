# DevTeamAutomated - Agentic Workflow Platform

A powerful event-driven workflow automation platform that orchestrates AI agents to handle complex multi-step workflows. Built on Redis Streams with support for multiple LLM providers.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Web Interface](#web-interface)
- [API Endpoints](#api-endpoints)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

DevTeamAutomated is a general-purpose event-driven workflow toolkit designed for orchestrating AI agents across various domains:

- **Audit Operations** - Automated audit workflows and compliance checks
- **Healthcare** - Clinical workflow automation
- **Financial Services** - Financial process automation
- **Manufacturing** - Production workflow management
- **DevSecOps** - Security review and vulnerability management
- **CI/CD** - Release governance and pipeline automation

The platform provides a robust foundation for building AI-powered automation solutions with built-in support for:
- Event sourcing and replay
- Multi-provider LLM integration (Anthropic, OpenAI, Google Gemini, Local LLMs)
- Distributed task processing
- Human-in-the-loop workflows
- Dead letter queues for error handling

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Event-Driven Architecture** | All state changes are events published to Redis Streams with full correlation tracking |
| **Multi-Provider LLM Support** | Seamlessly switch between Anthropic Claude, OpenAI GPT, Google Gemini, and local LLMs |
| **AI Agent Teams** | Specialized agent teams for analysis, admin, email, writing, and support tasks |
| **Human-in-the-Loop** | Built-in clarification system for human approval and input |
| **Dead Letter Queue** | Automatic error handling with DLQ for failed events |
| **Distributed Locks** | Redis-based mutual exclusion for concurrent operations |
| **Schema Validation** | Strict JSON Schema contracts for all events |
| **Idempotent Processing** | Guaranteed exactly-once processing with deduplication |
| **Web Interface** | Real-time project management dashboard |
| **REST API** | Full HTTP API for integration |

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/DevTeamAutomated.git
cd DevTeamAutomated
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys (optional for test mode)
```

### 3. Start the Platform

```bash
docker compose up --build
```

### 4. Access the Web Interface

Open your browser and navigate to:
- **Frontend Dashboard**: http://localhost:3000
- **LLM Gateway**: http://localhost:8000
- **Order Intake**: http://localhost:8080

### 5. Create Your First Project

Using the web interface or curl:

```bash
curl -X POST http://localhost:3000/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name": "My First Project", "description": "Automated workflow demo"}'
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Installation Guide](docs/INSTALLATION.md) | Detailed setup instructions for all environments |
| [Configuration Reference](docs/CONFIGURATION.md) | Complete configuration options and environment variables |
| [Architecture Overview](docs/ARCHITECTURE.md) | System design and component interaction |
| [API Reference](docs/API_REFERENCE.md) | REST API endpoints and usage |
| [Agent Teams Guide](docs/AGENT_TEAMS.md) | AI agent teams and collaboration patterns |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [Tool Usage Guide](docs/TOOL_USAGE.md) | Step-by-step usage walkthrough |
| [Security Best Practices](SECURITY.md) | Security considerations and recommendations |

---

## Architecture

```
                          +------------------+
                          |   Web Frontend   |
                          |   (Port 3000)    |
                          +--------+---------+
                                   |
                          +--------v---------+
                          |  Frontend API    |
                          |    Gateway       |
                          +--------+---------+
                                   |
        +-------------+------------+------------+-------------+
        |             |            |            |             |
+-------v------+ +----v----+ +-----v-----+ +---v----+ +------v------+
| Orchestrator | |Validator| | Workers   | |  LLM   | |Order Intake |
|              | |         | | (6 types) | |Gateway | |   Agent     |
+--------------+ +---------+ +-----------+ +--------+ +-------------+
        |             |            |            |             |
        +-------------+------------+------------+-------------+
                                   |
                          +--------v---------+
                          |  Redis Streams   |
                          |  (Event Store)   |
                          +------------------+
```

### Core Components

| Component | Description |
|-----------|-------------|
| **Frontend API** | HTTP gateway for web interface and REST API |
| **Orchestrator** | Generates backlogs, dispatches tasks, handles clarifications |
| **Validator** | Schema validation consumer, routes invalid events to DLQ |
| **Workers** | Specialized agents for different task types |
| **LLM Gateway** | Multi-provider LLM abstraction layer |
| **Redis Streams** | Persistent event log with consumer groups |

---

## Project Structure

```
DevTeamAutomated/
├── core/                    # Core infrastructure modules
│   ├── config.py           # Centralized settings
│   ├── redis_streams.py    # Redis client helpers
│   ├── stream_runtime.py   # Reliable event processor
│   ├── schema_registry.py  # JSON Schema loading
│   ├── llm_client.py       # Unified LLM interface
│   ├── llm_config.py       # LLM configuration loader
│   ├── agent_team.py       # Agent team base classes
│   └── ...                 # Additional modules
│
├── services/               # Executable microservices
│   ├── orchestrator/       # Task orchestration
│   ├── frontend_api/       # HTTP API gateway
│   ├── llm_gateway/        # LLM provider abstraction
│   ├── stream_consumer/    # Schema validation
│   ├── worker/             # Generic work processor
│   ├── time_waste_worker/  # Time analysis agent
│   ├── cost_worker/        # Cost estimation agent
│   ├── friction_worker/    # Friction detection agent
│   ├── scenario_worker/    # Savings projection agent
│   ├── dev_worker/         # Development task agent
│   ├── test_worker/        # Testing task agent
│   ├── order_intake_agent/ # Order processing
│   └── teams/              # AI agent teams
│
├── schemas/                # JSON Schema contracts
│   ├── envelope/           # Event envelope schema
│   ├── events/             # Event payload schemas
│   └── objects/            # Domain object schemas
│
├── config/                 # Configuration files
│   └── llm_config.yaml     # LLM provider configuration
│
├── docs/                   # Documentation
├── tests/                  # Test suite
├── demo/                   # Demo scripts
│
├── docker-compose.yml      # Development setup
├── docker-compose.prod.yml # Production setup
├── .env.example            # Environment template
└── Makefile               # Build commands
```

---

## Configuration

### Environment Variables

The platform uses environment variables for configuration. Copy `.env.example` to `.env` and customize:

```bash
# Redis Connection
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=              # Required in production

# Namespace (audit, healthcare, finserv, manufacturing, devsecops, cicd)
NAMESPACE=audit

# LLM Configuration
LLM_PROVIDER_ORDER=anthropic,openai,google,local
LLM_TEST_MODE=true           # Set to false in production

# API Keys (required when LLM_TEST_MODE=false)
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
GEMINI_API_KEY=xxx
```

For complete configuration options, see [Configuration Reference](docs/CONFIGURATION.md).

### LLM Configuration

The platform supports multiple LLM providers with automatic fallback. Configure providers in `config/llm_config.yaml`:

```yaml
global:
  default_provider: anthropic
  fallback_order:
    - anthropic
    - openai
    - google
    - local
  timeout_seconds: 120

providers:
  anthropic:
    models:
      claude-3-5-sonnet:
        max_tokens: 8192
        temperature: 0.7
```

---

## Web Interface

The web interface provides a real-time dashboard for managing projects and workflows.

### Features

- **Project Management** - Create, view, and manage projects
- **Question Answering** - Respond to clarification requests
- **Status Monitoring** - Real-time project status updates
- **Log Viewer** - Filterable system logs with severity levels
- **Orchestrator Messaging** - Send messages to the orchestrator

### Screenshots

Access the dashboard at http://localhost:3000 after starting the platform.

---

## API Endpoints

### Frontend API (Port 3000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/projects` | List all projects |
| POST | `/api/projects` | Create new project |
| GET | `/api/projects/:id/status` | Get project status |
| POST | `/api/projects/:id/stop` | Stop a project |
| POST | `/api/projects/:id/message` | Send message to orchestrator |
| GET | `/api/questions` | Get open questions |
| POST | `/api/questions/:id/answer` | Answer a question |
| GET | `/api/logs` | Get system logs |

### LLM Gateway (Port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/v1/providers` | List available providers |
| POST | `/v1/chat` | Chat completion |
| POST | `/v1/predict` | General prediction |
| POST | `/v1/extract/order` | Extract structured data |
| GET | `/v1/usage` | Usage statistics |

### Order Intake (Port 8080)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/orders/inbox` | Submit order (multipart form) |
| GET | `/orders/pending-validation` | List pending orders |
| POST | `/orders/:id/validate` | Validate/approve order |

For complete API documentation, see [API Reference](docs/API_REFERENCE.md).

---

## Testing

### Run All Tests

```bash
make test
# or
pytest
```

### Run Specific Tests

```bash
# Unit tests only
pytest tests/ -m "not integration"

# Integration tests (requires Docker)
pytest tests/ -m integration

# Specific test file
pytest tests/test_llm_client.py -v
```

### Test Coverage

```bash
pytest --cov=core --cov=services --cov-report=html
```

---

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make up` | Start all services with Docker Compose |
| `make down` | Stop and remove all containers |
| `make build` | Build Docker images |
| `make logs` | Follow service logs |
| `make ps` | List running containers |
| `make test` | Run test suite |
| `make demo` | Run all demo scripts |
| `make demo-happy` | Run happy path demo |
| `make demo-failure` | Run failure/DLQ demo |
| `make demo-clarification` | Run clarification loop demo |

---

## Demo Scripts

### Interactive Demo

```bash
python -m demo.interactive_demo
```

Provides a menu-driven interface for:
- Sending intake events
- Dispatching manual work
- Simulating worker outputs
- Viewing DLQ entries

### Clarification Demo

```bash
python -m demo.clarification_demo
```

Demonstrates the human-in-the-loop clarification flow.

### HTTP Gateway Demo

```bash
# Terminal 1
python -m demo.http_gateway

# Terminal 2
curl -X POST http://localhost:8080/initial-request \
  -H 'Content-Type: application/json' \
  -d '{"request_text": "full audit via curl"}'
```

---

## Inspecting Redis Streams

```bash
# View recent events
redis-cli -p 6380 XRANGE audit:events - + COUNT 20

# View deliverables
redis-cli -p 6380 XRANGE audit:events - + COUNT 20 | grep DELIVERABLE

# View DLQ entries
redis-cli -p 6380 XRANGE audit:dlq - + COUNT 5

# Reset consumer group
redis-cli -p 6380 XGROUP DESTROY audit:events my_group
redis-cli -p 6380 XGROUP CREATE audit:events my_group 0-0 MKSTREAM
```

---

## Namespace Customization

By default, the platform uses the `audit` namespace. Switch to other domains:

```bash
# Healthcare
export NAMESPACE=healthcare

# Financial Services
export NAMESPACE=finserv

# Manufacturing
export NAMESPACE=manufacturing

# DevSecOps
export NAMESPACE=devsecops

# CI/CD
export NAMESPACE=cicd
```

Or use granular overrides:

```bash
export STREAM_NAME=custom:events
export DLQ_STREAM=custom:dlq
export KEY_PREFIX=custom
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/your-org/DevTeamAutomated/issues)
- **Documentation**: [docs/](docs/)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)

---

**Built with Redis Streams, FastAPI, and Multi-Provider LLM Support**
