# Architecture Overview

This document describes the system architecture of DevTeamAutomated, an event-driven workflow automation platform.

---

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Core Concepts](#core-concepts)
- [Component Details](#component-details)
- [Event-Driven Architecture](#event-driven-architecture)
- [Data Flow](#data-flow)
- [State Management](#state-management)
- [LLM Integration](#llm-integration)
- [Agent Teams](#agent-teams)
- [Reliability Patterns](#reliability-patterns)
- [Scalability](#scalability)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                │
│    │  Web Browser │    │   curl/API   │    │  3rd Party   │                │
│    │  (Dashboard) │    │   Clients    │    │ Integrations │                │
│    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                │
│           │                   │                   │                         │
└───────────┼───────────────────┼───────────────────┼─────────────────────────┘
            │                   │                   │
            ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    │
│    │   Frontend API   │    │   LLM Gateway    │    │  Order Intake    │    │
│    │   (Port 3000)    │    │   (Port 8000)    │    │  (Port 8080)     │    │
│    │                  │    │                  │    │                  │    │
│    │  - Projects      │    │  - Multi-LLM     │    │  - File Upload   │    │
│    │  - Questions     │    │  - Fallback      │    │  - Extraction    │    │
│    │  - Status        │    │  - Caching       │    │  - Validation    │    │
│    │  - Logs          │    │  - Rate Limit    │    │  - Approval      │    │
│    └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘    │
│             │                       │                       │               │
└─────────────┼───────────────────────┼───────────────────────┼───────────────┘
              │                       │                       │
              ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PROCESSING LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐    │
│    │ Orchestrator │    │  Validator   │    │       Workers            │    │
│    │              │    │              │    │                          │    │
│    │ - Backlog    │    │ - Schema     │    │  ┌────────┐ ┌────────┐  │    │
│    │ - Dispatch   │    │   Validation │    │  │  Time  │ │  Cost  │  │    │
│    │ - Clarify    │    │ - DLQ Route  │    │  │ Waste  │ │ Worker │  │    │
│    │              │    │              │    │  └────────┘ └────────┘  │    │
│    └──────┬───────┘    └──────┬───────┘    │  ┌────────┐ ┌────────┐  │    │
│           │                   │            │  │Friction│ │Scenario│  │    │
│           │                   │            │  │ Worker │ │ Worker │  │    │
│           │                   │            │  └────────┘ └────────┘  │    │
│           │                   │            │  ┌────────┐ ┌────────┐  │    │
│           │                   │            │  │  Dev   │ │  Test  │  │    │
│           │                   │            │  │ Worker │ │ Worker │  │    │
│           │                   │            │  └────────┘ └────────┘  │    │
│           │                   │            └──────────────┬───────────┘    │
│           │                   │                           │                 │
└───────────┼───────────────────┼───────────────────────────┼─────────────────┘
            │                   │                           │
            ▼                   ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MESSAGE LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌────────────────────────────────────────────────────────────────────┐   │
│    │                        Redis Streams                               │   │
│    │                                                                    │   │
│    │    ┌─────────────────┐    ┌─────────────────┐                     │   │
│    │    │  audit:events   │    │   audit:dlq     │                     │   │
│    │    │  (Main Stream)  │    │ (Dead Letter Q) │                     │   │
│    │    └─────────────────┘    └─────────────────┘                     │   │
│    │                                                                    │   │
│    │    Consumer Groups: orchestrator_group, validator_group,          │   │
│    │                     time_waste_workers, cost_workers, ...         │   │
│    └────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│    ┌────────────────────────────────────────────────────────────────────┐   │
│    │                        Redis Data Stores                           │   │
│    │                                                                    │   │
│    │    ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │   │
│    │    │  Backlog  │  │ Questions │  │   Locks   │  │Idempotence│    │   │
│    │    │   Store   │  │   Store   │  │           │  │  Tracking │    │   │
│    │    └───────────┘  └───────────┘  └───────────┘  └───────────┘    │   │
│    └────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Concepts

### Event Sourcing

All state changes in the system are represented as immutable events stored in Redis Streams:

- **Immutability**: Events are never modified after creation
- **Ordering**: Events are strictly ordered by Redis Stream IDs
- **Replay**: State can be reconstructed by replaying events
- **Audit Trail**: Complete history of all changes

### Consumer Groups

Redis consumer groups enable:

- **Parallel Processing**: Multiple consumers in a group share the workload
- **At-Least-Once Delivery**: Messages are re-delivered if not acknowledged
- **Horizontal Scaling**: Add more consumers to increase throughput
- **Failure Recovery**: Pending messages are reclaimed after timeout

### Event Correlation

Every event contains:

- **event_id**: Unique identifier for the event
- **correlation_id**: Links related events across the workflow
- **causation_id**: References the event that caused this event
- **timestamp**: When the event occurred

---

## Component Details

### Frontend API Gateway

**Location**: `services/frontend_api/`
**Port**: 3000
**Technology**: FastAPI

**Responsibilities:**
- Serve the web dashboard
- Expose REST API for project management
- Handle question answering
- Aggregate logs from services
- Publish events to Redis Streams

**Key Endpoints:**
```
GET  /api/projects              - List projects
POST /api/projects              - Create project
GET  /api/projects/:id/status   - Get status
POST /api/projects/:id/stop     - Stop project
GET  /api/questions             - Get open questions
POST /api/questions/:id/answer  - Submit answer
GET  /api/logs                  - Get system logs
```

---

### Orchestrator

**Location**: `services/orchestrator/`
**Technology**: Python with Redis Streams consumer

**Responsibilities:**
- Generate backlog items from project requests
- Dispatch tasks to appropriate workers
- Handle clarification requests
- Manage backlog state transitions
- Coordinate workflow execution

**Event Processing:**
```
PROJECT.INITIAL_REQUEST_RECEIVED
    │
    ├─→ Generate Backlog Items
    │
    ├─→ Check for Clarification Needs
    │   └─→ CLARIFICATION.NEEDED (if ambiguous)
    │
    └─→ Dispatch Ready Tasks
        └─→ WORK.ITEM_DISPATCHED
```

---

### Validator (Stream Consumer)

**Location**: `services/stream_consumer/`
**Technology**: Python with Redis Streams consumer

**Responsibilities:**
- Validate event envelope structure
- Validate event payload against schema
- Route invalid events to DLQ
- Ensure contract compliance

**Validation Flow:**
```
Event Received
    │
    ├─→ Validate Envelope Schema
    │   └─→ Invalid? → DLQ
    │
    ├─→ Extract Event Type
    │
    ├─→ Validate Payload Schema
    │   └─→ Invalid? → DLQ
    │
    └─→ Acknowledge
```

---

### Worker Agents

**Location**: `services/*_worker/`
**Technology**: Python with Redis Streams consumer + LLM

**Types:**

| Worker | Purpose |
|--------|---------|
| `time_waste_worker` | Analyzes time spent on tasks |
| `cost_worker` | Estimates costs based on time and rates |
| `friction_worker` | Detects recurring/redundant tasks |
| `scenario_worker` | Projects savings scenarios |
| `dev_worker` | Executes development tasks |
| `test_worker` | Runs tests and validates |
| `worker` | Generic task processing |

**Processing Flow:**
```
WORK.ITEM_DISPATCHED
    │
    ├─→ Validate Target Agent
    │
    ├─→ Check Idempotence
    │   └─→ Already Processed? → Skip
    │
    ├─→ WORK.ITEM_STARTED
    │
    ├─→ Execute Task (may use LLM)
    │
    ├─→ DELIVERABLE.PUBLISHED
    │
    └─→ WORK.ITEM_COMPLETED
```

---

### LLM Gateway

**Location**: `services/llm_gateway/`
**Port**: 8000
**Technology**: FastAPI

**Responsibilities:**
- Abstract LLM provider differences
- Implement fallback logic
- Cache responses
- Track usage and costs
- Rate limiting

**Request Flow:**
```
LLM Request
    │
    ├─→ Check Cache
    │   └─→ Cache Hit? → Return Cached
    │
    ├─→ Try Primary Provider
    │   └─→ Failed? → Try Next Provider
    │
    ├─→ Track Usage/Costs
    │
    └─→ Cache Response
```

---

## Event-Driven Architecture

### Event Types

**Project Events:**
- `PROJECT.INITIAL_REQUEST_RECEIVED` - New project intake
- `PROJECT.COMPLETED` - All work finished

**Work Events:**
- `WORK.ITEM_DISPATCHED` - Task assigned to worker
- `WORK.ITEM_STARTED` - Worker began processing
- `WORK.ITEM_COMPLETED` - Worker finished
- `WORK.ITEM_FAILED` - Worker encountered error
- `WORK.ITEM_REVIEWED` - Quality review completed

**Deliverable Events:**
- `DELIVERABLE.PUBLISHED` - Work artifact produced

**Clarification Events:**
- `CLARIFICATION.NEEDED` - Request for more info
- `QUESTION.CREATED` - Question posted
- `QUESTION.ANSWER_RECORDED` - Answer received

**Order Events:**
- `ORDER.INBOX_RECEIVED` - New order submitted
- `ORDER.DRAFT_CREATED` - Extraction completed
- `ORDER.VALIDATION_REQUIRED` - Awaiting approval
- `ORDER.VALIDATED` - Order approved
- `ORDER.EXPORT_READY` - Ready for export

### Event Envelope

All events follow a standard envelope format:

```json
{
  "event_id": "uuid-v4",
  "event_type": "WORK.ITEM_DISPATCHED",
  "event_version": 1,
  "timestamp": "2024-01-15T10:30:00Z",
  "source": "orchestrator",
  "instance": "orchestrator-1",
  "correlation_id": "uuid-v4",
  "causation_id": "uuid-v4",
  "payload": { ... }
}
```

### Schema Contracts

All events are validated against JSON Schema contracts:

```
schemas/
├── envelope/
│   └── event_envelope.v1.schema.json
├── events/
│   ├── project.initial_request_received.v1.schema.json
│   ├── work.item_dispatched.v1.schema.json
│   └── ...
└── objects/
    ├── execution_plan.v1.schema.json
    └── ...
```

---

## Data Flow

### Project Creation Flow

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Web Client  │────▶│ Frontend API │────▶│    Redis     │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
                           ┌──────────────────────┘
                           ▼
┌──────────────┐     ┌─────────────────┐
│  Orchestrator│◀────│ audit:events    │
└──────┬───────┘     └─────────────────┘
       │
       │ Generate Backlog
       ▼
┌──────────────┐
│ BacklogStore │
└──────┬───────┘
       │
       │ Dispatch Tasks
       ▼
┌─────────────────┐     ┌──────────────┐
│ audit:events    │────▶│   Workers    │
└─────────────────┘     └──────────────┘
```

### Clarification Flow

```
┌──────────────┐                    ┌──────────────┐
│ Orchestrator │                    │   Frontend   │
└──────┬───────┘                    └──────┬───────┘
       │                                   │
       │ CLARIFICATION.NEEDED              │
       ▼                                   │
┌─────────────────┐                        │
│ QuestionStore   │◀───────────────────────┤
└──────┬──────────┘                        │
       │                                   │
       │ QUESTION.CREATED                  │
       ▼                                   │
┌─────────────────┐     GET /questions     │
│ audit:events    │────────────────────────▶
└─────────────────┘                        │
                                           │
                        POST /answer       │
                     ◀─────────────────────┤
                                           │
       │ USER.ANSWER_SUBMITTED             │
       ▼                                   │
┌─────────────────┐                        │
│ Orchestrator    │                        │
│ (unblock task)  │                        │
└─────────────────┘
```

---

## State Management

### Backlog State Machine

```
                 ┌─────────┐
                 │ CREATED │
                 └────┬────┘
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
    ┌────────┐   ┌─────────┐  ┌─────────┐
    │ READY  │   │ BLOCKED │  │ FAILED  │
    └────┬───┘   └────┬────┘  └─────────┘
         │            │
         │            │ (clarification answered)
         │            │
         │    ┌───────┘
         ▼    ▼
    ┌─────────────┐
    │ IN_PROGRESS │
    └──────┬──────┘
           │
    ┌──────┴──────┐
    ▼             ▼
┌──────┐     ┌─────────┐
│ DONE │     │ FAILED  │
└──────┘     └─────────┘
```

### Allowed Transitions

| From | To |
|------|-----|
| CREATED | READY, BLOCKED, FAILED |
| READY | IN_PROGRESS, BLOCKED, FAILED |
| BLOCKED | READY, FAILED |
| IN_PROGRESS | DONE, FAILED, BLOCKED |
| DONE | (terminal) |
| FAILED | (terminal) |

---

## LLM Integration

### Provider Abstraction

```
┌─────────────────────────────────────────────────────────┐
│                     LLM Client                          │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │  Anthropic  │  │   OpenAI    │  │   Google    │     │
│  │   Adapter   │  │   Adapter   │  │   Adapter   │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
│         │                │                │             │
│         ▼                ▼                ▼             │
│  ┌─────────────────────────────────────────────────┐   │
│  │               Fallback Manager                   │   │
│  │  - Try primary provider                          │   │
│  │  - On failure, try next in fallback order       │   │
│  │  - Rate limiting per provider                   │   │
│  └─────────────────────────────────────────────────┘   │
│                          │                              │
│                          ▼                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │               Response Cache                     │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Configuration Priority

```
1. Agent-specific override (agent_overrides)
      ↓
2. Task-type override (task_type_overrides)
      ↓
3. Provider default (providers.*.default_model)
      ↓
4. Global default (global.default_provider)
```

---

## Agent Teams

### Team Structure

```
┌─────────────────────────────────────────────────────────┐
│                    Team Coordinator                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Shared Memory                       │    │
│  │  - Context for all team members                 │    │
│  │  - Accumulated findings                         │    │
│  │  - Intermediate results                         │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │ Agent 1 │  │ Agent 2 │  │ Agent 3 │  │ Agent 4 │    │
│  │         │  │         │  │         │  │         │    │
│  │ Pattern │  │ Extract │  │Classify │  │ Report  │    │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘    │
│       │            │            │            │          │
│       └────────────┴────────────┴────────────┘          │
│                          │                              │
│                          ▼                              │
│            ┌─────────────────────────┐                  │
│            │   Collaboration Pattern  │                  │
│            │   (sequential/parallel)  │                  │
│            └─────────────────────────┘                  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Available Teams

| Team | Agents | Purpose |
|------|--------|---------|
| Analysis Team | Pattern, Extractor, Classifier, Remediator, Reporter | Data analysis workflows |
| Admin Team | Classifier, Executor | Administrative task handling |
| Email Team | Parser, Writer | Email processing |
| Writing Team | Editor, Style Keeper | Document editing |
| Support Team | Context, Answer, Analytics | Customer support |

### Collaboration Patterns

**Sequential:**
```
Agent 1 → Agent 2 → Agent 3 → Agent 4
```

**Parallel:**
```
     ┌→ Agent 1 ─┐
     │           │
Input┼→ Agent 2 ─┼→ Aggregator → Output
     │           │
     └→ Agent 3 ─┘
```

**Hierarchical:**
```
            Coordinator
           ┌─────┴─────┐
        Team A       Team B
       ┌──┴──┐      ┌──┴──┐
      A1    A2     B1    B2
```

**Iterative:**
```
Input → Agent → Review → Acceptable? ─Yes→ Output
                  │
                  No
                  │
                  └────→ Refine → Agent
```

---

## Reliability Patterns

### Idempotence

```python
# Prevent duplicate processing
def process_event(event_id):
    if not mark_if_new(redis, event_id, ttl=86400):
        return  # Already processed

    # Process event...
```

### Dead Letter Queue

```python
# Route failures to DLQ
try:
    process(event)
    ack(event)
except Exception as e:
    if attempts >= MAX_ATTEMPTS:
        publish_dlq(event, reason=str(e))
        ack(event)
    else:
        # Will be retried
        pass
```

### Distributed Locks

```python
# Prevent concurrent orchestration
if acquire_lock(redis, "orchestrator", ttl=120):
    try:
        run_orchestration()
    finally:
        release_lock(redis, "orchestrator")
```

### Retry with Exponential Backoff

```python
for attempt in range(MAX_RETRIES):
    try:
        result = call_llm(request)
        break
    except RateLimitError:
        delay = min(2 ** attempt, MAX_DELAY)
        sleep(delay)
```

---

## Scalability

### Horizontal Scaling

**Workers:**
```yaml
# docker-compose.prod.yml
services:
  worker:
    deploy:
      replicas: 5
```

**Consumer Groups:**
- Each worker instance joins the same consumer group
- Redis distributes messages across consumers
- No coordination needed between instances

### Vertical Scaling

**Resource Limits:**
```yaml
services:
  orchestrator:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

### Redis Scaling

**Options:**
1. Redis Cluster for sharding
2. Redis Sentinel for high availability
3. Managed Redis (ElastiCache, Cloud Memorystore)

---

## See Also

- [Configuration Reference](CONFIGURATION.md)
- [API Reference](API_REFERENCE.md)
- [Agent Teams Guide](AGENT_TEAMS.md)
