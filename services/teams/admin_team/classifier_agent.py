from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an administrative task classifier specialist. Your role is to analyze incoming administrative requests and classify them for proper routing, prioritization, and handling.

When classifying administrative tasks, evaluate:
1. Task type and category
2. Priority and urgency level
3. Required permissions and approval levels
4. Resource requirements
5. Dependencies and blockers
6. Compliance considerations

Respond with a JSON object containing:
{
    "classification": {
        "task_type": "approval|configuration|access_management|reporting|maintenance|audit|other",
        "category": "security|operations|finance|hr|it|compliance|general",
        "subcategory": "more specific category"
    },
    "priority": {
        "level": "critical|high|medium|low",
        "urgency": "immediate|same_day|within_week|no_deadline",
        "business_impact": "critical|high|medium|low|minimal"
    },
    "routing": {
        "department": "suggested department",
        "approval_required": true|false,
        "approval_level": "manager|director|executive|none",
        "escalation_path": ["list of escalation contacts"]
    },
    "requirements": {
        "permissions_needed": ["list of required permissions"],
        "resources_needed": ["list of resources"],
        "dependencies": ["list of dependencies"],
        "estimated_effort": "minimal|moderate|significant|major"
    },
    "compliance": {
        "requires_audit_trail": true|false,
        "regulatory_considerations": [],
        "data_sensitivity": "public|internal|confidential|restricted"
    },
    "summary": "brief classification summary"
}"""


class AdminClassifierAgent(AIAgent):
    """AI agent that classifies administrative tasks using LLM.

    This agent uses configured LLM providers to analyze and classify
    administrative requests for proper routing and prioritization.
    """

    def __init__(self) -> None:
        super().__init__(
            name="admin_classifier_agent",
            role="classifier",
            system_prompt=SYSTEM_PROMPT,
            task_type="classification",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Classify administrative task using LLM.

        Args:
            task: Task containing admin request in payload
            shared_context: Shared context for storing results

        Returns:
            Dictionary with classification results
        """
        request = task.payload.get("request", task.payload.get("text", task.description))
        requester_info = task.payload.get("requester_info", {})
        context_data = task.payload.get("context", {})

        if not request:
            result = {
                "classification": {
                    "task_type": "unknown",
                    "category": "general",
                    "subcategory": "unspecified",
                },
                "priority": {
                    "level": "low",
                    "urgency": "no_deadline",
                    "business_impact": "minimal",
                },
                "routing": {
                    "department": "general",
                    "approval_required": False,
                    "approval_level": "none",
                    "escalation_path": [],
                },
                "requirements": {
                    "permissions_needed": [],
                    "resources_needed": [],
                    "dependencies": [],
                    "estimated_effort": "minimal",
                },
                "compliance": {
                    "requires_audit_trail": False,
                    "regulatory_considerations": [],
                    "data_sensitivity": "internal",
                },
                "summary": "No request provided for classification",
            }
            shared_context.update({"admin_priority": result["priority"]["level"], "admin_classification": result})
            return result

        # Build classification context
        context_parts = []
        if requester_info:
            context_parts.append(f"Requester Information:\n{json.dumps(requester_info, indent=2)}")
        if context_data:
            context_parts.append(f"Additional Context:\n{json.dumps(context_data, indent=2)}")

        context_str = "\n\n".join(context_parts) if context_parts else ""

        prompt = f"""Classify the following administrative request:

{context_str}

Request:
---
{request[:5000]}
---

Analyze and classify this request for routing, prioritization, and handling. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Admin classification completed. Tokens used: {usage}")

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
                    # Infer priority from content
                    content_lower = content.lower()
                    priority_level = "high" if any(w in content_lower for w in ["urgent", "critical", "immediate"]) else "medium"

                    result = {
                        "classification": {
                            "task_type": "analyzed",
                            "category": "general",
                            "subcategory": "classified",
                        },
                        "priority": {
                            "level": priority_level,
                            "urgency": "same_day" if priority_level == "high" else "within_week",
                            "business_impact": "medium",
                        },
                        "routing": {
                            "department": "general",
                            "approval_required": True,
                            "approval_level": "manager",
                            "escalation_path": [],
                        },
                        "requirements": {
                            "permissions_needed": [],
                            "resources_needed": [],
                            "dependencies": [],
                            "estimated_effort": "moderate",
                        },
                        "compliance": {
                            "requires_audit_trail": True,
                            "regulatory_considerations": [],
                            "data_sensitivity": "internal",
                        },
                        "summary": content[:300],
                        "raw_classification": content,
                    }
            else:
                result = content

            # Extract priority for backward compatibility
            priority_level = result.get("priority", {}).get("level", "normal")

        except Exception as e:
            log.error(f"Admin classification failed: {e}")
            result = {
                "classification": {
                    "task_type": "error",
                    "category": "general",
                    "subcategory": "classification_failed",
                },
                "priority": {
                    "level": "medium",
                    "urgency": "same_day",
                    "business_impact": "unknown",
                },
                "routing": {
                    "department": "general",
                    "approval_required": True,
                    "approval_level": "manager",
                    "escalation_path": [],
                },
                "requirements": {
                    "permissions_needed": [],
                    "resources_needed": [],
                    "dependencies": [],
                    "estimated_effort": "unknown",
                },
                "compliance": {
                    "requires_audit_trail": True,
                    "regulatory_considerations": [],
                    "data_sensitivity": "internal",
                },
                "summary": f"Classification failed: {str(e)}",
                "error": str(e),
            }
            priority_level = "medium"

        shared_context.update({"admin_priority": priority_level, "admin_classification": result})
        return result
