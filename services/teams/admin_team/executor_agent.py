from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an administrative task execution specialist. Your role is to plan and coordinate the execution of administrative tasks based on their classification and requirements.

When planning task execution, consider:
1. Execution strategy and steps
2. Resource allocation
3. Timeline and milestones
4. Risk mitigation
5. Communication plan
6. Success criteria

Respond with a JSON object containing:
{
    "execution_plan": {
        "strategy": "immediate|scheduled|phased|delegated",
        "status": "approved|pending_approval|queued|expedited|on_hold",
        "steps": [
            {"step": 1, "action": "action description", "responsible": "who", "deadline": "when"}
        ],
        "timeline": {
            "start": "when to start",
            "estimated_completion": "expected completion",
            "milestones": [{"name": "milestone", "date": "target date"}]
        }
    },
    "resource_allocation": {
        "team_members": ["assigned team members"],
        "tools_required": ["required tools/systems"],
        "budget_impact": "none|minimal|moderate|significant"
    },
    "risk_assessment": {
        "identified_risks": [
            {"risk": "description", "probability": "high|medium|low", "mitigation": "strategy"}
        ],
        "contingency_plan": "backup plan if primary fails"
    },
    "communication": {
        "stakeholders": ["list of stakeholders"],
        "update_frequency": "daily|weekly|on_completion|as_needed",
        "notification_triggers": ["events that trigger notifications"]
    },
    "success_criteria": {
        "metrics": ["measurable outcomes"],
        "acceptance_criteria": ["criteria for completion"],
        "verification_steps": ["how to verify success"]
    },
    "outcome": "expedited|queued|scheduled|delegated|on_hold",
    "summary": "brief execution plan summary"
}"""


class AdminExecutorAgent(AIAgent):
    """AI agent that plans administrative task execution using LLM.

    This agent uses configured LLM providers to create execution
    plans for administrative tasks based on their classification.
    """

    def __init__(self) -> None:
        super().__init__(
            name="admin_executor_agent",
            role="executor",
            system_prompt=SYSTEM_PROMPT,
            task_type="reasoning",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Plan administrative task execution using LLM.

        Args:
            task: Task containing admin request in payload
            shared_context: Shared context with classification results

        Returns:
            Dictionary with execution plan
        """
        context = shared_context.get()
        request = task.payload.get("request", task.payload.get("text", task.description))
        classification = context.get("admin_classification", {})
        priority = context.get("admin_priority", "normal")
        available_resources = task.payload.get("resources", {})

        if not request and not classification:
            result = {
                "execution_plan": {
                    "strategy": "queued",
                    "status": "on_hold",
                    "steps": [],
                    "timeline": {
                        "start": "pending",
                        "estimated_completion": "unknown",
                        "milestones": [],
                    },
                },
                "resource_allocation": {
                    "team_members": [],
                    "tools_required": [],
                    "budget_impact": "none",
                },
                "risk_assessment": {
                    "identified_risks": [],
                    "contingency_plan": "N/A",
                },
                "communication": {
                    "stakeholders": [],
                    "update_frequency": "as_needed",
                    "notification_triggers": [],
                },
                "success_criteria": {
                    "metrics": [],
                    "acceptance_criteria": [],
                    "verification_steps": [],
                },
                "outcome": "on_hold",
                "summary": "No task provided for execution planning",
            }
            shared_context.update({"admin_outcome": result["outcome"], "admin_execution": result})
            return result

        # Build execution context
        context_parts = []
        if classification:
            context_parts.append(f"Task Classification:\n{json.dumps(classification, indent=2)}")
        context_parts.append(f"Priority Level: {priority}")
        if available_resources:
            context_parts.append(f"Available Resources:\n{json.dumps(available_resources, indent=2)}")

        context_str = "\n\n".join(context_parts)

        prompt = f"""Create an execution plan for the following administrative task:

{context_str}

Original Request:
---
{request[:4000]}
---

Develop a comprehensive execution plan including strategy, resources, timeline, and success criteria. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Admin execution plan created. Tokens used: {usage}")

            # Parse the LLM response
            content = response.get("content", response.get("text", ""))
            if isinstance(content, str):
                try:
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0]
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0]
                    result = json.loads(content.strip())
                except json.JSONDecodeError:
                    # Determine outcome based on priority
                    outcome = "expedited" if priority in ("critical", "high") else "queued"

                    result = {
                        "execution_plan": {
                            "strategy": "scheduled",
                            "status": outcome,
                            "steps": [],
                            "timeline": {
                                "start": "pending",
                                "estimated_completion": "to be determined",
                                "milestones": [],
                            },
                        },
                        "resource_allocation": {
                            "team_members": [],
                            "tools_required": [],
                            "budget_impact": "minimal",
                        },
                        "risk_assessment": {
                            "identified_risks": [],
                            "contingency_plan": "Manual intervention if needed",
                        },
                        "communication": {
                            "stakeholders": [],
                            "update_frequency": "as_needed",
                            "notification_triggers": ["completion", "blockers"],
                        },
                        "success_criteria": {
                            "metrics": [],
                            "acceptance_criteria": [],
                            "verification_steps": [],
                        },
                        "outcome": outcome,
                        "summary": content[:500],
                        "raw_plan": content,
                    }
            else:
                result = content

            # Extract outcome for backward compatibility
            outcome = result.get("outcome", result.get("execution_plan", {}).get("status", "queued"))

        except Exception as e:
            log.error(f"Admin execution planning failed: {e}")
            outcome = "queued"
            result = {
                "execution_plan": {
                    "strategy": "delegated",
                    "status": "pending_approval",
                    "steps": [
                        {"step": 1, "action": "Manual review required", "responsible": "admin", "deadline": "ASAP"}
                    ],
                    "timeline": {
                        "start": "pending",
                        "estimated_completion": "unknown",
                        "milestones": [],
                    },
                },
                "resource_allocation": {
                    "team_members": ["admin"],
                    "tools_required": [],
                    "budget_impact": "unknown",
                },
                "risk_assessment": {
                    "identified_risks": [
                        {"risk": "Automated planning failed", "probability": "high", "mitigation": "Manual handling"}
                    ],
                    "contingency_plan": "Escalate to manager",
                },
                "communication": {
                    "stakeholders": ["requester", "admin"],
                    "update_frequency": "as_needed",
                    "notification_triggers": ["any_progress"],
                },
                "success_criteria": {
                    "metrics": [],
                    "acceptance_criteria": ["Task completed"],
                    "verification_steps": ["Manual verification"],
                },
                "outcome": outcome,
                "summary": f"Execution planning failed: {str(e)}",
                "error": str(e),
            }

        shared_context.update({"admin_outcome": outcome, "admin_execution": result})
        return result
