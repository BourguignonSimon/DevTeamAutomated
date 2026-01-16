from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a support analytics specialist. Your role is to analyze support interactions to extract insights, identify trends, and suggest improvements.

When analyzing support data, evaluate:
1. Resolution effectiveness
2. Customer satisfaction indicators
3. Common issue patterns
4. Agent performance metrics
5. Process improvement opportunities
6. Knowledge gaps

Respond with a JSON object containing:
{
    "interaction_metrics": {
        "resolution_likelihood": 0.0-1.0,
        "customer_satisfaction_prediction": "satisfied|neutral|dissatisfied",
        "response_quality_score": 1-10,
        "first_contact_resolution": true|false
    },
    "trend_indicators": {
        "issue_category_trend": "increasing|stable|decreasing",
        "similar_issues_frequency": "rare|occasional|common|frequent",
        "seasonal_pattern": "none|identified"
    },
    "insights": [
        {"insight": "key insight description", "impact": "high|medium|low", "actionable": true|false}
    ],
    "improvement_suggestions": [
        {"area": "knowledge_base|process|training|tools", "suggestion": "specific suggestion", "priority": "high|medium|low"}
    ],
    "knowledge_gaps": [
        {"topic": "topic needing documentation", "urgency": "high|medium|low"}
    ],
    "tagging": {
        "categories": ["relevant categories"],
        "keywords": ["important keywords"],
        "sentiment_tags": ["sentiment indicators"]
    },
    "summary": "brief analytics summary"
}"""


class SupportAnalyticsAgent(AIAgent):
    """AI agent that analyzes support interactions using LLM.

    This agent uses configured LLM providers to extract insights,
    identify trends, and suggest improvements from support data.
    """

    def __init__(self) -> None:
        super().__init__(
            name="support_analytics_agent",
            role="analytics",
            system_prompt=SYSTEM_PROMPT,
            task_type="text_analysis",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Analyze support interaction using LLM.

        Args:
            task: Task containing interaction data in payload
            shared_context: Shared context with support context and answer

        Returns:
            Dictionary with analytics results
        """
        context = shared_context.get()
        request = task.payload.get("request", task.payload.get("text", ""))
        support_context = context.get("support_context", {})
        support_answer = context.get("support_answer", {})
        historical_data = task.payload.get("historical_data", {})

        if not request and not support_context and not support_answer:
            result = {
                "interaction_metrics": {
                    "resolution_likelihood": 0.0,
                    "customer_satisfaction_prediction": "neutral",
                    "response_quality_score": 0,
                    "first_contact_resolution": False,
                },
                "trend_indicators": {
                    "issue_category_trend": "stable",
                    "similar_issues_frequency": "unknown",
                    "seasonal_pattern": "none",
                },
                "insights": [],
                "improvement_suggestions": [],
                "knowledge_gaps": [],
                "tagging": {
                    "categories": [],
                    "keywords": [],
                    "sentiment_tags": [],
                },
                "summary": "No interaction data provided for analysis",
            }
            shared_context.update({"support_metrics": result})
            return result

        # Build analytics context
        interaction_data = {
            "request": request[:2000] if request else None,
            "context_analysis": support_context,
            "response_provided": support_answer,
        }

        context_parts = [f"Interaction Data:\n{json.dumps(interaction_data, indent=2)}"]
        if historical_data:
            context_parts.append(f"Historical Data:\n{json.dumps(historical_data, indent=2)}")

        context_str = "\n\n".join(context_parts)

        prompt = f"""Analyze the following support interaction for insights and metrics:

{context_str}

Extract analytics, identify trends, and suggest improvements. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Support analytics completed. Tokens used: {usage}")

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
                        "interaction_metrics": {
                            "resolution_likelihood": 0.7,
                            "customer_satisfaction_prediction": "neutral",
                            "response_quality_score": 7,
                            "first_contact_resolution": True,
                        },
                        "trend_indicators": {
                            "issue_category_trend": "stable",
                            "similar_issues_frequency": "occasional",
                            "seasonal_pattern": "none",
                        },
                        "insights": [],
                        "improvement_suggestions": [],
                        "knowledge_gaps": [],
                        "tagging": {
                            "categories": [support_context.get("issue_analysis", {}).get("category", "general")],
                            "keywords": [],
                            "sentiment_tags": [],
                        },
                        "summary": content[:500],
                        "raw_analytics": content,
                    }
            else:
                result = content

        except Exception as e:
            log.error(f"Support analytics failed: {e}")
            result = {
                "interaction_metrics": {
                    "resolution_likelihood": 0.5,
                    "customer_satisfaction_prediction": "neutral",
                    "response_quality_score": 0,
                    "first_contact_resolution": False,
                },
                "trend_indicators": {
                    "issue_category_trend": "unknown",
                    "similar_issues_frequency": "unknown",
                    "seasonal_pattern": "unknown",
                },
                "insights": [
                    {"insight": f"Analytics processing error: {str(e)}", "impact": "low", "actionable": False}
                ],
                "improvement_suggestions": [],
                "knowledge_gaps": [],
                "tagging": {
                    "categories": ["error"],
                    "keywords": [],
                    "sentiment_tags": [],
                },
                "summary": f"Analytics failed: {str(e)}",
                "error": str(e),
            }

        shared_context.update({"support_metrics": result})
        return result
