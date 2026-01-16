# API Reference

Complete reference for all REST API endpoints in DevTeamAutomated.

---

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Frontend API (Port 3000)](#frontend-api-port-3000)
- [LLM Gateway (Port 8000)](#llm-gateway-port-8000)
- [Order Intake Agent (Port 8080)](#order-intake-agent-port-8080)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [Examples](#examples)

---

## Overview

DevTeamAutomated exposes three main API services:

| Service | Port | Base URL | Purpose |
|---------|------|----------|---------|
| Frontend API | 3000 | `http://localhost:3000` | Project management, questions, logs |
| LLM Gateway | 8000 | `http://localhost:8000` | LLM abstraction and chat |
| Order Intake | 8080 | `http://localhost:8080` | Order processing |

All APIs return JSON responses and accept JSON request bodies unless otherwise noted.

---

## Authentication

Currently, the APIs do not require authentication for development use. In production, implement authentication using:

- API keys in headers
- JWT tokens
- OAuth 2.0

**Recommended Header:**
```
Authorization: Bearer <token>
```

---

## Frontend API (Port 3000)

### Projects

#### List All Projects

```http
GET /api/projects
```

**Response:**
```json
{
  "projects": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Audit Q1 2024",
      "description": "Quarterly financial audit",
      "status": "IN_PROGRESS",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T14:45:00Z"
    }
  ]
}
```

**Status Codes:**
- `200 OK` - Success
- `500 Internal Server Error` - Redis connection error

---

#### Create Project

```http
POST /api/projects
Content-Type: application/json
```

**Request Body:**
```json
{
  "name": "My New Project",
  "description": "Description of the project"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Project name (1-200 chars) |
| `description` | string | Yes | Project description |

**Response:**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Project created successfully"
}
```

**Status Codes:**
- `201 Created` - Project created
- `400 Bad Request` - Invalid input
- `500 Internal Server Error` - Server error

---

#### Get Project Status

```http
GET /api/projects/{project_id}/status
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | string (UUID) | Project identifier |

**Response:**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "IN_PROGRESS",
  "backlog_items": {
    "total": 5,
    "completed": 2,
    "in_progress": 1,
    "ready": 1,
    "blocked": 1
  },
  "deliverables": [
    {
      "id": "del-001",
      "type": "time_analysis",
      "created_at": "2024-01-15T11:00:00Z"
    }
  ],
  "last_activity": "2024-01-15T14:45:00Z"
}
```

**Status Codes:**
- `200 OK` - Success
- `404 Not Found` - Project not found

---

#### Stop Project

```http
POST /api/projects/{project_id}/stop
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | string (UUID) | Project identifier |

**Response:**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "STOPPED",
  "message": "Project stopped successfully"
}
```

**Status Codes:**
- `200 OK` - Project stopped
- `404 Not Found` - Project not found
- `409 Conflict` - Project already completed

---

#### Send Message to Orchestrator

```http
POST /api/projects/{project_id}/message
Content-Type: application/json
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_id` | string (UUID) | Project identifier |

**Request Body:**
```json
{
  "message": "Please prioritize the cost analysis"
}
```

**Response:**
```json
{
  "message_id": "msg-123",
  "status": "delivered"
}
```

**Status Codes:**
- `200 OK` - Message sent
- `404 Not Found` - Project not found

---

### Questions

#### Get Open Questions

```http
GET /api/questions
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_id` | string | (all) | Filter by project |
| `status` | string | `OPEN` | Filter by status |

**Response:**
```json
{
  "questions": [
    {
      "id": "q-001",
      "project_id": "550e8400-e29b-41d4-a716-446655440000",
      "backlog_item_id": "item-123",
      "question_text": "What is the hourly rate for consultants?",
      "answer_type": "NUMBER",
      "status": "OPEN",
      "created_at": "2024-01-15T12:00:00Z",
      "correlation_id": "corr-456"
    }
  ]
}
```

---

#### Answer a Question

```http
POST /api/questions/{question_id}/answer
Content-Type: application/json
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `question_id` | string | Question identifier |

**Request Body:**
```json
{
  "answer": "150"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `answer` | string/number/object | Yes | The answer value |

**Response:**
```json
{
  "question_id": "q-001",
  "status": "CLOSED",
  "message": "Answer recorded successfully"
}
```

**Status Codes:**
- `200 OK` - Answer recorded
- `400 Bad Request` - Invalid answer format
- `404 Not Found` - Question not found

---

### Logs

#### Get System Logs

```http
GET /api/logs
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `level` | string | (all) | Filter by level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `service` | string | (all) | Filter by service name |
| `limit` | integer | 100 | Maximum entries to return |
| `offset` | integer | 0 | Pagination offset |
| `since` | string | (none) | ISO timestamp to filter from |

**Response:**
```json
{
  "logs": [
    {
      "timestamp": "2024-01-15T14:45:00Z",
      "level": "INFO",
      "service": "orchestrator",
      "message": "Dispatched work item",
      "metadata": {
        "project_id": "550e8400-e29b-41d4-a716-446655440000",
        "item_id": "item-123"
      }
    }
  ],
  "total": 1523,
  "limit": 100,
  "offset": 0
}
```

---

## LLM Gateway (Port 8000)

### Health Check

#### Get Health Status

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "providers": {
    "anthropic": "available",
    "openai": "available",
    "google": "available",
    "local": "unavailable"
  },
  "cache": "enabled",
  "uptime_seconds": 3600
}
```

---

### Providers

#### List Available Providers

```http
GET /v1/providers
```

**Response:**
```json
{
  "providers": [
    {
      "name": "anthropic",
      "enabled": true,
      "default_model": "claude-3-5-sonnet-20241022",
      "models": [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229"
      ]
    },
    {
      "name": "openai",
      "enabled": true,
      "default_model": "gpt-4o",
      "models": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo"
      ]
    }
  ]
}
```

---

### Chat Completion

#### Send Chat Request

```http
POST /v1/chat
Content-Type: application/json
```

**Request Body:**
```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "What is the capital of France?"
    }
  ],
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "max_tokens": 1024,
  "temperature": 0.7
}
```

**Parameters:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `messages` | array | Yes | - | Chat messages |
| `provider` | string | No | (from config) | LLM provider |
| `model` | string | No | (provider default) | Model name |
| `max_tokens` | integer | No | 1024 | Max response tokens |
| `temperature` | float | No | 0.7 | Sampling temperature |
| `stream` | boolean | No | false | Stream response |

**Response:**
```json
{
  "id": "chat-12345",
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "message": {
    "role": "assistant",
    "content": "The capital of France is Paris."
  },
  "usage": {
    "input_tokens": 25,
    "output_tokens": 10,
    "total_tokens": 35
  },
  "cached": false
}
```

**Status Codes:**
- `200 OK` - Success
- `400 Bad Request` - Invalid request
- `429 Too Many Requests` - Rate limited
- `503 Service Unavailable` - All providers failed

---

### Prediction

#### General Prediction

```http
POST /v1/predict
Content-Type: application/json
```

**Request Body:**
```json
{
  "prompt": "Classify this text: 'Great product, highly recommend!'",
  "task_type": "classification",
  "options": {
    "categories": ["positive", "negative", "neutral"]
  }
}
```

**Response:**
```json
{
  "prediction": "positive",
  "confidence": 0.95,
  "metadata": {
    "model": "gpt-4o-mini",
    "processing_time_ms": 150
  }
}
```

---

### Data Extraction

#### Extract Order Data

```http
POST /v1/extract/order
Content-Type: application/json
```

**Request Body:**
```json
{
  "text": "Order from John Doe, 123 Main St, for 5 units of Widget A at $10 each.",
  "schema": {
    "customer_name": "string",
    "address": "string",
    "items": "array",
    "total": "number"
  }
}
```

**Response:**
```json
{
  "extracted": {
    "customer_name": "John Doe",
    "address": "123 Main St",
    "items": [
      {
        "name": "Widget A",
        "quantity": 5,
        "unit_price": 10
      }
    ],
    "total": 50
  },
  "confidence": 0.92,
  "missing_fields": []
}
```

---

### Usage Statistics

#### Get Usage Stats

```http
GET /v1/usage
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `day` | `hour`, `day`, `week`, `month` |
| `provider` | string | (all) | Filter by provider |

**Response:**
```json
{
  "period": "day",
  "start": "2024-01-15T00:00:00Z",
  "end": "2024-01-15T23:59:59Z",
  "totals": {
    "requests": 1500,
    "input_tokens": 250000,
    "output_tokens": 75000,
    "estimated_cost_usd": 12.50
  },
  "by_provider": {
    "anthropic": {
      "requests": 800,
      "input_tokens": 150000,
      "output_tokens": 45000,
      "estimated_cost_usd": 7.50
    },
    "openai": {
      "requests": 700,
      "input_tokens": 100000,
      "output_tokens": 30000,
      "estimated_cost_usd": 5.00
    }
  }
}
```

---

## Order Intake Agent (Port 8080)

### Submit Order

#### Create Order from Email

```http
POST /orders/inbox
Content-Type: multipart/form-data
```

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `from_email` | string | Yes | Sender email address |
| `subject` | string | No | Email subject |
| `body` | string | No | Email body text |
| `delivery_address` | string | No | Delivery address |
| `delivery_date` | string | No | Requested delivery date |
| `files` | file(s) | No | Attachments (Excel, PDF) |

**Example with curl:**
```bash
curl -X POST http://localhost:8080/orders/inbox \
  -F 'from_email=customer@example.com' \
  -F 'subject=New Order Request' \
  -F 'delivery_address=123 Main St' \
  -F 'delivery_date=2024-02-01' \
  -F 'files=@order.xlsx'
```

**Response:**
```json
{
  "order_id": "ord-550e8400",
  "status": "DRAFT_CREATED",
  "extracted_data": {
    "customer_email": "customer@example.com",
    "delivery_address": "123 Main St",
    "delivery_date": "2024-02-01",
    "line_items": [
      {
        "product": "Widget A",
        "quantity": 10
      }
    ]
  },
  "validation_required": true,
  "missing_fields": ["phone_number"]
}
```

**Status Codes:**
- `201 Created` - Order created
- `400 Bad Request` - Invalid input
- `415 Unsupported Media Type` - Invalid file type

---

### List Pending Validation

#### Get Orders Awaiting Validation

```http
GET /orders/pending-validation
```

**Response:**
```json
{
  "orders": [
    {
      "order_id": "ord-550e8400",
      "status": "VALIDATION_REQUIRED",
      "created_at": "2024-01-15T10:00:00Z",
      "customer_email": "customer@example.com",
      "issues": [
        {
          "field": "phone_number",
          "type": "missing",
          "message": "Phone number is required"
        }
      ]
    }
  ]
}
```

---

### Validate Order

#### Approve and Validate Order

```http
POST /orders/{order_id}/validate
Content-Type: application/json
```

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `order_id` | string | Order identifier |

**Request Body:**
```json
{
  "corrections": {
    "phone_number": "+1-555-123-4567"
  },
  "approved": true,
  "notes": "Verified customer details by phone"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `corrections` | object | No | Field corrections |
| `approved` | boolean | No | Approval flag (default: true) |
| `notes` | string | No | Validation notes |

**Response:**
```json
{
  "order_id": "ord-550e8400",
  "status": "VALIDATED",
  "export_path": "/storage/exports/ord-550e8400.csv",
  "message": "Order validated and exported successfully"
}
```

**Status Codes:**
- `200 OK` - Order validated
- `400 Bad Request` - Invalid corrections
- `404 Not Found` - Order not found
- `409 Conflict` - Order already validated

---

## Error Handling

All APIs return errors in a consistent format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid project name",
    "details": {
      "field": "name",
      "constraint": "max_length",
      "value": 200
    }
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid input data |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | State conflict |
| `RATE_LIMITED` | 429 | Too many requests |
| `PROVIDER_ERROR` | 502 | LLM provider error |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable |
| `INTERNAL_ERROR` | 500 | Internal server error |

---

## Rate Limiting

API rate limits are configured per service:

| Service | Requests/minute | Notes |
|---------|-----------------|-------|
| Frontend API | 100 | Per client IP |
| LLM Gateway | 60 | Per provider |
| Order Intake | 30 | Per client IP |

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705315200
```

When rate limited:
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests",
    "retry_after": 60
  }
}
```

---

## Examples

### Complete Project Workflow

```bash
# 1. Create a project
PROJECT_ID=$(curl -s -X POST http://localhost:3000/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name": "Q1 Audit", "description": "First quarter audit"}' \
  | jq -r '.project_id')

echo "Created project: $PROJECT_ID"

# 2. Check project status
curl -s http://localhost:3000/api/projects/$PROJECT_ID/status | jq

# 3. Check for questions
curl -s "http://localhost:3000/api/questions?project_id=$PROJECT_ID" | jq

# 4. Answer a question (if any)
QUESTION_ID="q-001"
curl -s -X POST http://localhost:3000/api/questions/$QUESTION_ID/answer \
  -H 'Content-Type: application/json' \
  -d '{"answer": "150"}'

# 5. Monitor logs
curl -s "http://localhost:3000/api/logs?service=orchestrator&limit=10" | jq
```

### LLM Chat Example

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "messages": [
      {"role": "user", "content": "Summarize this text: ..."}
    ],
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 500
  }' | jq
```

### Order Processing Example

```bash
# 1. Submit order
ORDER_ID=$(curl -s -X POST http://localhost:8080/orders/inbox \
  -F 'from_email=customer@example.com' \
  -F 'subject=New Order' \
  -F 'delivery_address=123 Main St' \
  | jq -r '.order_id')

echo "Created order: $ORDER_ID"

# 2. Check pending validations
curl -s http://localhost:8080/orders/pending-validation | jq

# 3. Validate order
curl -s -X POST http://localhost:8080/orders/$ORDER_ID/validate \
  -H 'Content-Type: application/json' \
  -d '{"approved": true}' | jq
```

---

## See Also

- [Architecture Overview](ARCHITECTURE.md)
- [Configuration Reference](CONFIGURATION.md)
- [Troubleshooting](TROUBLESHOOTING.md)
