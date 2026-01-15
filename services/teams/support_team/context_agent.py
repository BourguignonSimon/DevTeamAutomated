from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a support context analysis specialist. Your role is to analyze support requests and gather relevant context to help provide accurate responses.

When analyzing support context, identify:
1. Issue category and type
2. Customer/user background if available
3. Related past interactions or tickets
4. Technical environment details
5. Urgency and impact assessment
6. Required expertise areas

Respond with a JSON object containing:
{
    "issue_analysis": {
        "category": "technical|billing|account|feature_request|bug_report|general_inquiry",
        "subcategory": "more specific category",
        "complexity": "simple|moderate|complex|critical",
        "estimated_resolution_time": "minutes|hours|days"
    },
    "customer_context": {
        "identified_info": {},
        "sentiment": "frustrated|neutral|satisfied|urgent",
        "history_summary": "brief summary if history available"
    },
    "technical_context": {
        "environment": {},
        "error_details": {},
        "reproduction_steps": []
    },
    "knowledge_needed": ["list of knowledge areas required"],
    "suggested_resources": ["documentation", "faqs", "previous solutions"],
    "escalation_recommended": true|false,
    "priority_score": 1-10,
    "context_summary": "brief summary of the support context"
}"""


class SupportContextAgent(AIAgent):
    """AI agent that analyzes support request context using LLM.

    This agent uses configured LLM providers to gather and analyze
    relevant context for support requests.
    """

    def __init__(self) -> None:
        super().__init__(
            name="support_context_agent",
            role="context",
            system_prompt=SYSTEM_PROMPT,
            task_type="text_analysis",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Analyze support request context using LLM.

        Args:
            task: Task containing support request in payload
            shared_context: Shared context for storing results

        Returns:
            Dictionary with context analysis
        """
        request = task.payload.get("request", task.payload.get("text", ""))
        customer_info = task.payload.get("customer_info", {})
        history = task.payload.get("history", [])
        product = task.payload.get("product", "")

        if not request:
            result = {
                "issue_analysis": {
                    "category": "unknown",
                    "subcategory": "unspecified",
                    "complexity": "unknown",
                    "estimated_resolution_time": "unknown",
                },
                "customer_context": {
                    "identified_info": {},
                    "sentiment": "neutral",
                    "history_summary": "No history available",
                },
                "technical_context": {
                    "environment": {},
                    "error_details": {},
                    "reproduction_steps": [],
                },
                "knowledge_needed": [],
                "suggested_resources": [],
                "escalation_recommended": False,
                "priority_score": 1,
                "context_summary": "No support request provided",
            }
            shared_context.update({"support_context": result})
            return result

        # Build context for analysis
        context_parts = []
        if customer_info:
            context_parts.append(f"Customer Information:\n{json.dumps(customer_info, indent=2)}")
        if history:
            context_parts.append(f"Previous Interactions:\n{json.dumps(history[-5:], indent=2)}")  # Last 5 interactions
        if product:
            context_parts.append(f"Product/Service: {product}")

        context_str = "\n\n".join(context_parts) if context_parts else ""

        prompt = f"""Analyze the following support request and gather relevant context:

{context_str}

Support Request:
---
{request[:6000]}
---

Identify the issue category, gather technical context, and assess priority. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Support context analysis completed. Tokens used: {usage}")

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
                        "issue_analysis": {
                            "category": "analyzed",
                            "subcategory": "general",
                            "complexity": "moderate",
                            "estimated_resolution_time": "hours",
                        },
                        "customer_context": {
                            "identified_info": customer_info,
                            "sentiment": "neutral",
                            "history_summary": "Analysis completed",
                        },
                        "technical_context": {},
                        "knowledge_needed": [],
                        "suggested_resources": [],
                        "escalation_recommended": False,
                        "priority_score": 5,
                        "context_summary": content[:500],
                        "raw_analysis": content,
                    }
            else:
                result = content

        except Exception as e:
            log.error(f"Support context analysis failed: {e}")
            result = {
                "issue_analysis": {
                    "category": "error",
                    "subcategory": "analysis_failed",
                    "complexity": "unknown",
                    "estimated_resolution_time": "unknown",
                },
                "customer_context": {
                    "identified_info": customer_info,
                    "sentiment": "neutral",
                    "history_summary": "Analysis failed",
                },
                "technical_context": {},
                "knowledge_needed": [],
                "suggested_resources": [],
                "escalation_recommended": True,
                "priority_score": 7,
                "context_summary": f"Context analysis failed: {str(e)}",
                "error": str(e),
            }

        shared_context.update({"support_context": result})
        return result
