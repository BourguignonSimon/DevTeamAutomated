"""LLM-Powered Development Worker.

This worker uses LLM capabilities to perform intelligent development tasks.
It demonstrates how to use the LLMAgent base class for AI-powered agents.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from core.config import Settings
from core.dlq import publish_dlq
from core.event_utils import envelope, now_iso
from core.idempotence import mark_if_new
from core.llm_agent import AgentContext, AgentResponse, LLMAgent
from core.locks import acquire_lock, release_lock
from core.logging import setup_logging
from core.redis_streams import ack, build_redis_client, ensure_consumer_group, read_group
from core.schema_registry import load_registry
from core.schema_validate import validate_envelope, validate_payload

AGENT_NAME = "llm_dev_worker"
log = logging.getLogger(AGENT_NAME)


class LLMDevWorker(LLMAgent):
    """LLM-powered development worker agent.

    This agent uses LLM capabilities to:
    - Analyze code and requirements
    - Generate code solutions
    - Review and suggest improvements
    - Execute tool calls for development tasks
    """

    @property
    def agent_name(self) -> str:
        return "dev_worker"

    def build_system_prompt(self, context: AgentContext) -> str:
        """Build the system prompt for development tasks."""
        return f"""You are an expert software development agent working on project {context.project_id}.

Your role is to analyze work items and produce high-quality development output.

When analyzing work:
1. Understand the requirements from the work context
2. Identify the key technical challenges
3. Propose a solution approach
4. Generate any necessary code or documentation

Always respond with a JSON object containing:
{{
    "analysis": {{
        "summary": "Brief summary of what needs to be done",
        "challenges": ["List of technical challenges identified"],
        "approach": "Proposed solution approach"
    }},
    "output": {{
        "type": "code|documentation|review",
        "content": "The actual output content",
        "files_affected": ["List of files that would be affected"]
    }},
    "recommendations": ["List of recommendations for next steps"],
    "confidence": 0.0-1.0
}}
"""

    def get_tools(self) -> Optional[List[Dict[str, Any]]]:
        """Define tools available to this agent."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "analyze_code",
                    "description": "Analyze code structure and identify patterns",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code_snippet": {
                                "type": "string",
                                "description": "The code to analyze"
                            },
                            "analysis_type": {
                                "type": "string",
                                "enum": ["complexity", "patterns", "bugs", "security"],
                                "description": "Type of analysis to perform"
                            }
                        },
                        "required": ["code_snippet", "analysis_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_tests",
                    "description": "Generate test cases for a function or module",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "function_name": {
                                "type": "string",
                                "description": "Name of the function to test"
                            },
                            "function_signature": {
                                "type": "string",
                                "description": "The function signature"
                            },
                            "test_type": {
                                "type": "string",
                                "enum": ["unit", "integration", "e2e"],
                                "description": "Type of tests to generate"
                            }
                        },
                        "required": ["function_name", "test_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "suggest_refactoring",
                    "description": "Suggest code refactoring improvements",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code_snippet": {
                                "type": "string",
                                "description": "The code to refactor"
                            },
                            "goals": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Refactoring goals (e.g., 'readability', 'performance')"
                            }
                        },
                        "required": ["code_snippet"]
                    }
                }
            }
        ]

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool call.

        In a real implementation, this would connect to actual development tools.
        """
        if tool_name == "analyze_code":
            code = arguments.get("code_snippet", "")
            analysis_type = arguments.get("analysis_type", "patterns")
            return json.dumps({
                "analysis_type": analysis_type,
                "lines_of_code": len(code.split("\n")),
                "complexity_score": 5,
                "findings": [
                    f"Code analyzed for {analysis_type}",
                    "No critical issues found"
                ]
            })

        elif tool_name == "generate_tests":
            func_name = arguments.get("function_name", "unknown")
            test_type = arguments.get("test_type", "unit")
            return json.dumps({
                "test_type": test_type,
                "test_cases": [
                    f"test_{func_name}_basic_input",
                    f"test_{func_name}_edge_cases",
                    f"test_{func_name}_error_handling"
                ],
                "coverage_estimate": "80%"
            })

        elif tool_name == "suggest_refactoring":
            return json.dumps({
                "suggestions": [
                    "Extract common logic into helper function",
                    "Use more descriptive variable names",
                    "Add type hints for better documentation"
                ],
                "priority": "medium"
            })

        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    def process(self, context: AgentContext) -> AgentResponse:
        """Process a development work item using LLM.

        Args:
            context: Agent context with work details

        Returns:
            AgentResponse with the development output
        """
        system_prompt = self.build_system_prompt(context)

        # Format work context for the LLM
        work_data = json.dumps(context.work_context, indent=2)
        user_message = f"""Please analyze and process this development work item:

Work Context:
{work_data}

Provide your analysis and any code or documentation output.
"""

        # Use tool-enabled conversation if tools are available
        if self.get_tools():
            response = self.run_with_tools(
                user_message=user_message,
                system_prompt=system_prompt,
                max_tool_calls=5,
            )
        else:
            response = self.chat(
                user_message=user_message,
                system_prompt=system_prompt,
            )

        return response


# Worker instance
worker_agent: Optional[LLMDevWorker] = None


def get_worker() -> LLMDevWorker:
    """Get or create the worker agent instance."""
    global worker_agent
    if worker_agent is None:
        worker_agent = LLMDevWorker()
    return worker_agent


def _emit_started(r, settings: Settings, env: dict, project_id: str, backlog_item_id: str) -> None:
    """Emit WORK.ITEM_STARTED event."""
    started_env = envelope(
        event_type="WORK.ITEM_STARTED",
        payload={
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
            "started_at": now_iso(),
            "agent": AGENT_NAME,
        },
        source=AGENT_NAME,
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(started_env)})


def _emit_clarification(r, settings: Settings, env: dict, project_id: str, backlog_item_id: str, reason: str) -> None:
    """Emit CLARIFICATION.NEEDED event."""
    clar_env = envelope(
        event_type="CLARIFICATION.NEEDED",
        payload={
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
            "reason": reason,
            "agent": AGENT_NAME,
        },
        source=AGENT_NAME,
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(clar_env)})


def _emit_results(
    r,
    settings: Settings,
    env: dict,
    project_id: str,
    backlog_item_id: str,
    response: AgentResponse,
    work_context: dict,
) -> None:
    """Emit DELIVERABLE.PUBLISHED and WORK.ITEM_COMPLETED events."""
    # Build deliverable from LLM response
    deliverable = {
        "type": "llm_development_output",
        "project_id": project_id,
        "backlog_item_id": backlog_item_id,
        "timestamp": now_iso(),
        "agent": AGENT_NAME,
        "llm_provider": response.provider_used,
        "llm_model": response.model_used,
        "content": response.structured_output or {"raw_response": response.content},
        "token_usage": {
            "input": response.usage.input_tokens if response.usage else 0,
            "output": response.usage.output_tokens if response.usage else 0,
            "total": response.usage.total_tokens if response.usage else 0,
        },
        "latency_ms": response.latency_ms,
    }

    # Publish deliverable
    dlv_env = envelope(
        event_type="DELIVERABLE.PUBLISHED",
        payload={
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
            "deliverable": deliverable,
        },
        source=AGENT_NAME,
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(dlv_env)})

    # Mark work as completed
    completed_env = envelope(
        event_type="WORK.ITEM_COMPLETED",
        payload={
            "project_id": project_id,
            "backlog_item_id": backlog_item_id,
            "evidence": {
                "agent": AGENT_NAME,
                "llm_provider": response.provider_used,
                "success": response.success,
            },
        },
        source=AGENT_NAME,
        correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
        causation_id=env.get("event_id"),
    )
    r.xadd(settings.stream_name, {"event": json.dumps(completed_env)})


def _process_message(r, reg, settings: Settings, msg_id: str, fields: dict) -> None:
    """Process a single message from the stream."""
    if "event" not in fields:
        publish_dlq(r, settings.dlq_stream, "missing field 'event'", fields)
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    try:
        env = json.loads(fields["event"])
    except Exception as e:
        publish_dlq(r, settings.dlq_stream, f"invalid json: {e}", fields)
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    res_env = validate_envelope(reg, env)
    if not res_env.ok:
        publish_dlq(r, settings.dlq_stream, res_env.error or "invalid envelope", fields, schema_id=res_env.schema_id)
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    # Only process WORK.ITEM_DISPATCHED events
    if env.get("event_type") != "WORK.ITEM_DISPATCHED":
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    payload = env.get("payload", {})
    res_pl = validate_payload(reg, env["event_type"], payload)
    if not res_pl.ok:
        publish_dlq(r, settings.dlq_stream, res_pl.error or "invalid payload", fields, schema_id=res_pl.schema_id)
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    # Check if this message is for us
    agent_target = payload.get("agent_target")
    if agent_target not in (AGENT_NAME, "dev_worker"):
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    # Idempotence check
    event_id = env.get("event_id")
    idem_key = f"{event_id}:{settings.consumer_group}"
    if not mark_if_new(r, event_id=idem_key, ttl_s=settings.idempotence_ttl_s, prefix=settings.idempotence_prefix):
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    project_id = payload["project_id"]
    backlog_item_id = payload["backlog_item_id"]
    work_context = payload.get("work_context") or {}

    # Acquire lock
    lock = acquire_lock(r, f"{settings.key_prefix}:lock:backlog:{backlog_item_id}", ttl_ms=settings.lock_ttl_s * 1000)
    if not lock:
        log.info("backlog lock busy backlog_item_id=%s", backlog_item_id)
        ack(r, settings.stream_name, settings.consumer_group, msg_id)
        return

    try:
        # Emit started event
        try:
            if reg.get("WORK.ITEM_STARTED"):
                _emit_started(r, settings, env, project_id, backlog_item_id)
        except Exception:
            pass

        # Create agent context
        context = AgentContext(
            project_id=project_id,
            backlog_item_id=backlog_item_id,
            work_context=work_context,
            correlation_id=env.get("correlation_id") or str(uuid.uuid4()),
            event_id=env.get("event_id") or str(uuid.uuid4()),
        )

        # Process with LLM agent
        worker = get_worker()
        response = worker.process(context)

        if response.success:
            _emit_results(r, settings, env, project_id, backlog_item_id, response, work_context)
        else:
            _emit_clarification(
                r, settings, env, project_id, backlog_item_id,
                f"LLM processing failed: {response.error}"
            )

    except Exception as e:
        log.error(f"Error processing message: {e}")
        publish_dlq(r, settings.dlq_stream, str(e), fields)
    finally:
        release_lock(r, lock)

    ack(r, settings.stream_name, settings.consumer_group, msg_id)


def main() -> None:
    """Main entry point for the LLM dev worker."""
    settings = Settings()
    setup_logging(settings.log_level)

    reg = load_registry("/app/schemas")
    r = build_redis_client(settings.redis_host, settings.redis_port, settings.redis_db)

    ensure_consumer_group(r, settings.stream_name, settings.consumer_group)
    log.info(
        "%s listening stream=%s group=%s consumer=%s",
        AGENT_NAME,
        settings.stream_name,
        settings.consumer_group,
        settings.consumer_name,
    )

    while True:
        msgs = read_group(
            r,
            stream=settings.stream_name,
            group=settings.consumer_group,
            consumer=settings.consumer_name,
            block_ms=settings.xread_block_ms,
            reclaim_min_idle_ms=settings.pending_reclaim_min_idle_ms,
            reclaim_count=settings.pending_reclaim_count,
        )
        if not msgs:
            continue

        for msg_id, fields in msgs:
            _process_message(r, reg, settings, msg_id, fields)


if __name__ == "__main__":
    main()
