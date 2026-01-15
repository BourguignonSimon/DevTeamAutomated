from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert support response specialist. Your role is to craft helpful, accurate, and empathetic responses to support requests.

When crafting support responses, ensure:
1. Direct address of the customer's issue
2. Clear step-by-step solutions when applicable
3. Empathetic and professional tone
4. Appropriate technical detail level
5. Links to relevant resources
6. Clear next steps or follow-up actions

Respond with a JSON object containing:
{
    "response": {
        "greeting": "personalized greeting",
        "acknowledgment": "brief acknowledgment of the issue",
        "solution": "main solution or response content",
        "steps": [
            {"step": 1, "instruction": "first step", "note": "optional note"}
        ],
        "additional_info": "any additional helpful information",
        "closing": "appropriate closing with next steps"
    },
    "full_response": "complete formatted response text",
    "tone": "empathetic|professional|technical|friendly",
    "confidence": 0.0-1.0,
    "requires_followup": true|false,
    "alternative_solutions": [
        {"solution": "alternative approach", "when_to_use": "scenario"}
    ],
    "resources": [
        {"type": "documentation|faq|video|article", "title": "resource title", "url": "if available"}
    ],
    "internal_notes": "notes for support team"
}"""


class SupportAnswerAgent(AIAgent):
    """AI agent that generates support responses using LLM.

    This agent uses configured LLM providers to craft helpful,
    accurate, and empathetic responses to support requests.
    """

    def __init__(self) -> None:
        super().__init__(
            name="support_answer_agent",
            role="answer",
            system_prompt=SYSTEM_PROMPT,
            task_type="text_generation",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Generate support response using LLM.

        Args:
            task: Task containing support request in payload
            shared_context: Shared context with support context

        Returns:
            Dictionary with support response
        """
        context = shared_context.get()
        request = task.payload.get("request", task.payload.get("text", ""))
        support_context = context.get("support_context", {})
        customer_name = task.payload.get("customer_name", "")
        knowledge_base = task.payload.get("knowledge_base", {})

        if not request and not support_context:
            result = {
                "response": {
                    "greeting": "",
                    "acknowledgment": "",
                    "solution": "",
                    "steps": [],
                    "additional_info": "",
                    "closing": "",
                },
                "full_response": "",
                "tone": "professional",
                "confidence": 0.0,
                "requires_followup": True,
                "alternative_solutions": [],
                "resources": [],
                "internal_notes": "No request provided",
            }
            shared_context.update({"support_answer": result})
            return result

        # Build response context
        context_parts = []
        if support_context:
            context_parts.append(f"Context Analysis:\n{json.dumps(support_context, indent=2)}")
        if customer_name:
            context_parts.append(f"Customer Name: {customer_name}")
        if knowledge_base:
            context_parts.append(f"Relevant Knowledge:\n{json.dumps(knowledge_base, indent=2)}")

        context_str = "\n\n".join(context_parts)

        prompt = f"""Craft a helpful support response based on the following:

{context_str}

Original Support Request:
---
{request[:5000]}
---

Provide a complete, helpful response with clear solutions and next steps. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Support response generated. Tokens used: {usage}")

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
                    greeting = f"Hello{' ' + customer_name if customer_name else ''},"
                    result = {
                        "response": {
                            "greeting": greeting,
                            "acknowledgment": "Thank you for reaching out.",
                            "solution": content,
                            "steps": [],
                            "additional_info": "",
                            "closing": "Please let us know if you have any other questions.",
                        },
                        "full_response": f"{greeting}\n\nThank you for reaching out.\n\n{content}\n\nPlease let us know if you have any other questions.",
                        "tone": "professional",
                        "confidence": 0.7,
                        "requires_followup": False,
                        "alternative_solutions": [],
                        "resources": [],
                        "internal_notes": "",
                        "raw_response": content,
                    }
            else:
                result = content

            # Generate full response if not provided
            if not result.get("full_response") and result.get("response"):
                resp = result["response"]
                result["full_response"] = f"{resp.get('greeting', '')}\n\n{resp.get('acknowledgment', '')}\n\n{resp.get('solution', '')}\n\n{resp.get('closing', '')}"

        except Exception as e:
            log.error(f"Support response generation failed: {e}")
            result = {
                "response": {
                    "greeting": f"Hello{' ' + customer_name if customer_name else ''},",
                    "acknowledgment": "Thank you for contacting support.",
                    "solution": "I apologize, but I'm having difficulty processing your request. A support agent will follow up with you shortly.",
                    "steps": [],
                    "additional_info": "",
                    "closing": "We appreciate your patience.",
                },
                "full_response": "",
                "tone": "apologetic",
                "confidence": 0.0,
                "requires_followup": True,
                "alternative_solutions": [],
                "resources": [],
                "internal_notes": f"Automated response failed: {str(e)}",
                "error": str(e),
            }

        shared_context.update({"support_answer": result})
        return result
