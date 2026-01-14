# Agent Teams Guide

This document describes the AI agent teams in DevTeamAutomated, their capabilities, and how to configure and extend them.

---

## Table of Contents

- [Overview](#overview)
- [Core Concepts](#core-concepts)
- [Available Teams](#available-teams)
  - [Analysis Team](#analysis-team)
  - [Admin Team](#admin-team)
  - [Email Team](#email-team)
  - [Writing Team](#writing-team)
  - [Support Team](#support-team)
- [Worker Agents](#worker-agents)
- [Collaboration Patterns](#collaboration-patterns)
- [Shared Memory](#shared-memory)
- [LLM Configuration](#llm-configuration)
- [Creating Custom Teams](#creating-custom-teams)
- [Best Practices](#best-practices)

---

## Overview

DevTeamAutomated uses AI agent teams to process complex workflows. Each team consists of specialized agents that collaborate to complete tasks.

**Key Features:**
- Modular agent design
- Configurable LLM backends per agent
- Shared context across team members
- Multiple collaboration patterns
- Cost and usage tracking

---

## Core Concepts

### Agent Team Structure

```
┌─────────────────────────────────────────────────────────┐
│                   Team Coordinator                       │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Shared Memory (Context)             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │ Agent 1 │  │ Agent 2 │  │ Agent 3 │  │ Agent N │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │           Collaboration Pattern                  │    │
│  │        (Sequential / Parallel / etc.)           │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Team Member

Each team member (agent) has:

| Property | Description |
|----------|-------------|
| `name` | Unique identifier within the team |
| `role` | Functional description |
| `capabilities` | List of what the agent can do |
| `llm_config` | Provider/model configuration |
| `prompts` | System and task prompts |

### Team Coordinator

The coordinator manages:
- Agent initialization
- Task distribution
- Context sharing
- Result aggregation
- Error handling

---

## Available Teams

### Analysis Team

**Location**: `services/teams/analysis_team/`

**Purpose**: Analyze data, detect patterns, and generate reports.

**Agents:**

| Agent | Role | LLM Model | Temperature |
|-------|------|-----------|-------------|
| Pattern Agent | Detect patterns in data | claude-3-5-sonnet | 0.3 |
| Extraction Agent | Extract structured data | claude-3-5-sonnet | 0.1 |
| Classifier Agent | Categorize findings | gpt-4o-mini | 0.2 |
| Remediation Agent | Suggest fixes | claude-3-5-sonnet | 0.5 |
| Report Agent | Generate reports | claude-3-5-sonnet | 0.7 |

**Workflow:**

```
Input Data
    │
    ▼
┌──────────────┐
│Pattern Agent │ ──▶ Identify anomalies, trends
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│Extraction Agent  │ ──▶ Extract key data points
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│Classifier Agent  │ ──▶ Categorize findings
└──────┬───────────┘
       │
       ▼
┌───────────────────┐
│Remediation Agent  │ ──▶ Suggest actions
└──────┬────────────┘
       │
       ▼
┌──────────────┐
│Report Agent  │ ──▶ Generate final report
└──────────────┘
```

**Example Usage:**

```python
from services.teams.analysis_team import AnalysisTeam

team = AnalysisTeam()
result = team.analyze({
    "data": financial_records,
    "focus_areas": ["discrepancies", "compliance"]
})
```

---

### Admin Team

**Location**: `services/teams/admin_team/`

**Purpose**: Handle administrative tasks and classify incoming requests.

**Agents:**

| Agent | Role | LLM Model | Temperature |
|-------|------|-----------|-------------|
| Classifier Agent | Categorize admin tasks | gpt-4o-mini | 0.1 |
| Executor Agent | Execute classified tasks | claude-3-5-sonnet | 0.3 |

**Task Categories:**
- Scheduling
- Document management
- Data entry
- Report generation
- Communication drafting

**Workflow:**

```
Admin Request
    │
    ▼
┌────────────────────┐
│Classifier Agent    │ ──▶ Determine task type
└──────┬─────────────┘
       │
       ▼
┌────────────────────┐
│Executor Agent      │ ──▶ Perform the action
└────────────────────┘
```

---

### Email Team

**Location**: `services/teams/email_team/`

**Purpose**: Parse incoming emails and draft responses.

**Agents:**

| Agent | Role | LLM Model | Temperature |
|-------|------|-----------|-------------|
| Parser Agent | Extract email structure | gpt-4o-mini | 0.1 |
| Writer Agent | Draft email responses | claude-3-5-sonnet | 0.7 |

**Parser Agent Extracts:**
- Sender information
- Subject classification
- Key requests/questions
- Urgency level
- Required actions
- Attachments metadata

**Writer Agent Produces:**
- Professional response
- Action items addressed
- Tone matching (formal/informal)
- Follow-up suggestions

**Workflow:**

```
Incoming Email
    │
    ▼
┌──────────────┐
│Parser Agent  │ ──▶ Extract: sender, intent, urgency
└──────┬───────┘
       │
       ▼
┌──────────────┐
│Writer Agent  │ ──▶ Draft appropriate response
└──────────────┘
```

**Example:**

```python
from services.teams.email_team import EmailTeam

team = EmailTeam()
result = team.process_email({
    "from": "client@example.com",
    "subject": "Urgent: Project Status",
    "body": "Can you provide an update on the Q1 audit?"
})

# Result:
# {
#   "parsed": {
#     "intent": "status_request",
#     "urgency": "high",
#     "project": "Q1 audit"
#   },
#   "draft_response": "Dear Client, ..."
# }
```

---

### Writing Team

**Location**: `services/teams/writing_team/`

**Purpose**: Edit and improve documents while maintaining style consistency.

**Agents:**

| Agent | Role | LLM Model | Temperature |
|-------|------|-----------|-------------|
| Editor Agent | Improve clarity and flow | claude-3-5-sonnet | 0.7 |
| Style Keeper Agent | Ensure brand consistency | claude-3-5-sonnet | 0.5 |

**Editor Agent Capabilities:**
- Grammar and spelling correction
- Clarity improvements
- Structure optimization
- Tone adjustment
- Redundancy removal

**Style Keeper Agent Ensures:**
- Brand voice consistency
- Terminology standardization
- Formatting compliance
- Accessibility standards

**Workflow:**

```
Draft Document
    │
    ▼
┌──────────────┐
│Editor Agent  │ ──▶ Improve content quality
└──────┬───────┘
       │
       ▼
┌───────────────────┐
│Style Keeper Agent │ ──▶ Apply style guidelines
└───────────────────┘
       │
       ▼
  Final Document
```

---

### Support Team

**Location**: `services/teams/support_team/`

**Purpose**: Handle customer support queries with context-aware responses.

**Agents:**

| Agent | Role | LLM Model | Temperature |
|-------|------|-----------|-------------|
| Context Agent | Retrieve relevant context | gpt-4o | 0.3 |
| Answer Agent | Generate helpful responses | claude-3-5-sonnet | 0.7 |
| Analytics Agent | Track support patterns | gemini-1.5-flash | 0.2 |

**Context Agent Sources:**
- Knowledge base articles
- Previous interactions
- Product documentation
- Account information
- Common issues database

**Answer Agent Produces:**
- Accurate responses
- Step-by-step solutions
- Links to resources
- Escalation recommendations

**Analytics Agent Tracks:**
- Common issues
- Resolution rates
- Customer satisfaction signals
- Knowledge gaps

**Workflow:**

```
Support Query
    │
    ▼
┌──────────────────┐
│Context Agent     │ ──▶ Gather relevant information
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│Answer Agent      │ ──▶ Generate response
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│Analytics Agent   │ ──▶ Log patterns (async)
└──────────────────┘
```

---

## Worker Agents

In addition to teams, DevTeamAutomated includes specialized worker agents:

### Time Waste Worker

**Location**: `services/time_waste_worker/`

**Purpose**: Analyze time spent on tasks and identify inefficiencies.

**Inputs:**
```json
{
  "rows": [
    {"category": "meetings", "estimated_minutes": 60, "text": "Status meeting"},
    {"category": "admin", "estimated_minutes": 30, "text": "Email triage"}
  ]
}
```

**Outputs:**
- Total time per category
- Time distribution percentages
- Inefficiency indicators

---

### Cost Worker

**Location**: `services/cost_worker/`

**Purpose**: Calculate costs based on time and hourly rates.

**Inputs:**
```json
{
  "rows": [...],
  "hourly_rate": 150,
  "period": {"type": "monthly", "working_days": 20}
}
```

**Outputs:**
- Hourly costs
- Monthly projections
- Annual estimates

---

### Friction Worker

**Location**: `services/friction_worker/`

**Purpose**: Detect recurring tasks and redundant work.

**Outputs:**
- Recurring task clusters
- Automation opportunities
- Avoidable work percentage

---

### Scenario Worker

**Location**: `services/scenario_worker/`

**Purpose**: Project savings from reducing friction.

**Outputs:**
- Recovered hours estimate
- Cost savings projection
- Implementation recommendations

---

### Dev Worker

**Location**: `services/dev_worker/`

**Purpose**: Execute development tasks.

**Capabilities:**
- Code generation
- Code review
- Refactoring suggestions
- Documentation generation

---

### Test Worker

**Location**: `services/test_worker/`

**Purpose**: Execute testing tasks.

**Capabilities:**
- Test case generation
- Test execution analysis
- Coverage recommendations
- Bug report analysis

---

## Collaboration Patterns

### Sequential Pattern

Agents execute one after another, passing results forward.

```python
from core.collaboration_patterns import SequentialPattern

pattern = SequentialPattern([
    pattern_agent,
    extraction_agent,
    classifier_agent
])

result = pattern.execute(input_data)
```

```
Agent 1 ──▶ Agent 2 ──▶ Agent 3 ──▶ Result
```

---

### Parallel Pattern

Agents execute simultaneously, results are aggregated.

```python
from core.collaboration_patterns import ParallelPattern

pattern = ParallelPattern([
    cost_agent,
    time_agent,
    friction_agent
])

result = pattern.execute(input_data)
# Result contains outputs from all agents
```

```
        ┌──▶ Agent 1 ──┐
        │              │
Input ──┼──▶ Agent 2 ──┼──▶ Aggregate ──▶ Result
        │              │
        └──▶ Agent 3 ──┘
```

---

### Hierarchical Pattern

Coordinator delegates to sub-teams.

```python
from core.collaboration_patterns import HierarchicalPattern

pattern = HierarchicalPattern(
    coordinator=main_coordinator,
    teams=[analysis_team, support_team]
)

result = pattern.execute(input_data)
```

```
              Coordinator
             ┌─────┴─────┐
          Team A       Team B
         ┌──┴──┐      ┌──┴──┐
        A1    A2     B1    B2
```

---

### Iterative Pattern

Agent refines output until quality threshold is met.

```python
from core.collaboration_patterns import IterativePattern

pattern = IterativePattern(
    worker=editor_agent,
    reviewer=quality_agent,
    max_iterations=3
)

result = pattern.execute(input_data)
```

```
Input ──▶ Worker ──▶ Reviewer ──▶ Acceptable?
              ▲                      │
              │        No            │
              └──────────────────────┘
                       │
                      Yes
                       ▼
                    Result
```

---

## Shared Memory

Teams share context through a thread-safe shared memory system.

### Structure

```python
shared_memory = {
    "context": {
        "project_id": "...",
        "task_type": "analysis",
        "constraints": [...]
    },
    "findings": [
        {"agent": "pattern", "type": "anomaly", "data": {...}},
        {"agent": "extractor", "type": "data_point", "data": {...}}
    ],
    "intermediate_results": {
        "pattern_output": {...},
        "extraction_output": {...}
    },
    "metadata": {
        "started_at": "...",
        "token_usage": {...}
    }
}
```

### Usage

```python
from core.shared_memory import SharedMemory

memory = SharedMemory()

# Agent writes
memory.add_finding("pattern", {"type": "anomaly", "data": {...}})

# Another agent reads
findings = memory.get_findings_by_agent("pattern")

# Store intermediate result
memory.set_result("pattern_output", {...})

# Retrieve for next agent
prev_result = memory.get_result("pattern_output")
```

---

## LLM Configuration

### Agent-Level Configuration

Configure specific agents in `config/llm_config.yaml`:

```yaml
agent_overrides:
  pattern_agent:
    provider: anthropic
    model: claude-3-5-sonnet-20241022
    temperature: 0.3
    max_tokens: 4096

  classifier_agent:
    provider: openai
    model: gpt-4o-mini
    temperature: 0.2
    max_tokens: 2048
```

### Runtime Override

```python
from core.llm_client import LLMClient

client = LLMClient(
    provider="anthropic",
    model="claude-3-opus-20240229",  # Override for specific task
    temperature=0.1
)

response = client.complete(prompt)
```

---

## Creating Custom Teams

### Step 1: Define Team Structure

```python
# services/teams/custom_team/team.py

from core.agent_team import AgentTeam, TeamMember

class CustomTeam(AgentTeam):
    def __init__(self):
        super().__init__(
            name="custom_team",
            members=[
                TeamMember(
                    name="analyzer",
                    role="Analyze input data",
                    capabilities=["pattern_detection", "anomaly_detection"],
                    llm_config={
                        "provider": "anthropic",
                        "model": "claude-3-5-sonnet-20241022"
                    }
                ),
                TeamMember(
                    name="summarizer",
                    role="Summarize findings",
                    capabilities=["summarization"],
                    llm_config={
                        "provider": "google",
                        "model": "gemini-1.5-flash"
                    }
                )
            ]
        )
```

### Step 2: Implement Agent Logic

```python
# services/teams/custom_team/agents/analyzer.py

from core.agent_team import BaseAgent

class AnalyzerAgent(BaseAgent):
    def execute(self, input_data, shared_memory):
        # Get context
        context = shared_memory.get_context()

        # Call LLM
        response = self.llm_client.complete(
            system_prompt=self.system_prompt,
            user_prompt=f"Analyze: {input_data}"
        )

        # Store findings
        shared_memory.add_finding(self.name, {
            "analysis": response,
            "confidence": 0.85
        })

        return response
```

### Step 3: Define Workflow

```python
# services/teams/custom_team/workflow.py

from core.collaboration_patterns import SequentialPattern

class CustomWorkflow:
    def __init__(self, team):
        self.team = team
        self.pattern = SequentialPattern([
            team.get_member("analyzer"),
            team.get_member("summarizer")
        ])

    def run(self, input_data):
        return self.pattern.execute(input_data)
```

### Step 4: Register with Config

Add to `config/llm_config.yaml`:

```yaml
agent_overrides:
  custom_analyzer:
    provider: anthropic
    model: claude-3-5-sonnet-20241022
    temperature: 0.3

  custom_summarizer:
    provider: google
    model: gemini-1.5-flash
    temperature: 0.5
```

---

## Best Practices

### Agent Design

1. **Single Responsibility**: Each agent should do one thing well
2. **Clear Interfaces**: Define input/output schemas
3. **Graceful Degradation**: Handle LLM failures gracefully
4. **Logging**: Log all agent decisions for debugging

### LLM Selection

| Task Type | Recommended Model | Reason |
|-----------|-------------------|--------|
| Code generation | Claude 3.5 Sonnet | Best code quality |
| Classification | GPT-4o-mini | Fast and accurate |
| Summarization | Gemini 1.5 Flash | Cost-effective |
| Complex reasoning | Claude 3 Opus / o1 | Deep analysis |
| Simple extraction | GPT-4o-mini | Fast turnaround |

### Temperature Guidelines

| Task | Temperature | Reason |
|------|-------------|--------|
| Data extraction | 0.1-0.2 | Deterministic output |
| Classification | 0.1-0.3 | Consistent categories |
| Analysis | 0.3-0.5 | Balance accuracy/creativity |
| Writing | 0.6-0.8 | Creative flexibility |
| Brainstorming | 0.8-1.0 | Maximum creativity |

### Cost Optimization

1. **Use cheaper models for simple tasks** (GPT-4o-mini, Gemini Flash)
2. **Cache repeated queries**
3. **Batch similar requests**
4. **Set token limits appropriately**
5. **Monitor usage dashboards**

### Error Handling

```python
class RobustAgent(BaseAgent):
    def execute(self, input_data, shared_memory):
        try:
            response = self.llm_client.complete(...)
            return response
        except ProviderError as e:
            # Log and try fallback
            logger.warning(f"Provider error: {e}")
            return self.fallback_response(input_data)
        except RateLimitError:
            # Back off and retry
            time.sleep(self.backoff_delay)
            return self.execute(input_data, shared_memory)
```

---

## See Also

- [Architecture Overview](ARCHITECTURE.md)
- [Configuration Reference](CONFIGURATION.md)
- [API Reference](API_REFERENCE.md)
