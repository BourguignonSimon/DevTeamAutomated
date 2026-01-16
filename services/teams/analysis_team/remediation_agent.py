from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a remediation and mitigation specialist. Your role is to analyze identified risks and issues to propose actionable remediation strategies.

When proposing remediation, consider:
1. Immediate actions to mitigate urgent risks
2. Short-term fixes and workarounds
3. Long-term solutions and improvements
4. Required resources and stakeholders
5. Implementation timeline and dependencies

Respond with a JSON object containing:
{
    "remediation_status": "required|recommended|optional|not_needed",
    "immediate_actions": [
        {"action": "description", "priority": "critical|high|medium|low", "owner": "suggested owner"}
    ],
    "short_term": [
        {"action": "description", "effort": "low|medium|high", "impact": "low|medium|high"}
    ],
    "long_term": [
        {"action": "description", "benefit": "description of benefit"}
    ],
    "stakeholders": ["list of stakeholders to involve"],
    "dependencies": ["list of dependencies"],
    "estimated_effort": "minimal|moderate|significant|major",
    "risk_mitigation_summary": "summary of how proposed actions address risks"
}"""


class RemediationAgent(AIAgent):
    """AI agent that proposes remediation strategies using LLM.

    This agent uses configured LLM providers to analyze identified risks
    and propose actionable remediation and mitigation strategies.
    """

    def __init__(self) -> None:
        super().__init__(
            name="remediation_agent",
            role="remediation",
            system_prompt=SYSTEM_PROMPT,
            task_type="reasoning",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Propose remediation strategies using LLM.

        Args:
            task: Task containing the document text in payload["text"]
            shared_context: Shared context with classification and extraction results

        Returns:
            Dictionary with remediation proposals
        """
        context = shared_context.get()
        text = task.payload.get("text", "")
        classification = context.get("classification", {})
        extracted_info = context.get("extracted", {})
        pattern_info = context.get("document_pattern", {})

        # Check if remediation is needed
        risk_level = classification.get("risk_level", "unknown")
        if risk_level in ("none", "low") and not classification.get("risk_factors"):
            result = {
                "remediation_status": "not_needed",
                "immediate_actions": [],
                "short_term": [],
                "long_term": [],
                "stakeholders": [],
                "dependencies": [],
                "estimated_effort": "minimal",
                "risk_mitigation_summary": "No significant risks identified requiring remediation",
            }
            shared_context.update({"remediation": result})
            return result

        # Build context for remediation proposal
        context_parts = []
        if classification:
            context_parts.append(f"Classification Results:\n{json.dumps(classification, indent=2)}")
        if extracted_info:
            context_parts.append(f"Extracted Information:\n{json.dumps(extracted_info, indent=2)}")
        if pattern_info:
            context_parts.append(f"Document Pattern:\n{json.dumps(pattern_info, indent=2)}")

        context_str = "\n\n".join(context_parts)

        prompt = f"""Based on the following analysis, propose remediation and mitigation strategies:

{context_str}

Original Document Context (truncated):
---
{text[:3000]}
---

Analyze the identified risks and issues, then propose actionable remediation strategies. Include immediate actions, short-term fixes, and long-term solutions. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Remediation proposal completed. Tokens used: {usage}")

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
                    result = {
                        "remediation_status": "required",
                        "immediate_actions": [],
                        "short_term": [],
                        "long_term": [],
                        "stakeholders": [],
                        "dependencies": [],
                        "estimated_effort": "moderate",
                        "risk_mitigation_summary": content[:500],
                        "raw_proposal": content,
                    }
            else:
                result = content

        except Exception as e:
            log.error(f"Remediation proposal failed: {e}")
            result = {
                "remediation_status": "required",
                "immediate_actions": [
                    {
                        "action": "Manual review required due to analysis error",
                        "priority": "high",
                        "owner": "analyst",
                    }
                ],
                "short_term": [],
                "long_term": [],
                "stakeholders": ["analyst", "manager"],
                "dependencies": [],
                "estimated_effort": "unknown",
                "risk_mitigation_summary": f"Automated remediation failed: {str(e)}",
                "error": str(e),
            }

        shared_context.update({"remediation": result})
        return result
