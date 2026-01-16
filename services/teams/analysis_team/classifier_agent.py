from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a classification specialist. Your role is to analyze documents and extracted information to classify risks, categories, priorities, and required actions.

When classifying content, evaluate:
1. Risk level (critical, high, medium, low, none)
2. Content category (legal, financial, technical, operational, compliance, etc.)
3. Priority level (urgent, high, normal, low)
4. Required action type (immediate_action, review_needed, monitoring, archive)
5. Confidence in classification

Respond with a JSON object containing:
{
    "risk_level": "critical|high|medium|low|none",
    "risk_factors": ["list of identified risk factors"],
    "category": "primary category",
    "subcategories": ["additional categories"],
    "priority": "urgent|high|normal|low",
    "action_required": "action type",
    "reasoning": "brief explanation of classification",
    "confidence": 0.0 to 1.0
}"""


class ClassifierAgent(AIAgent):
    """AI agent that classifies documents and risks using LLM.

    This agent uses configured LLM providers to analyze document content
    and extracted data to determine risk levels, categories, and priorities.
    """

    def __init__(self) -> None:
        super().__init__(
            name="classifier_agent",
            role="classification",
            system_prompt=SYSTEM_PROMPT,
            task_type="classification",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Classify document content and risks using LLM.

        Args:
            task: Task containing the document text in payload["text"]
            shared_context: Shared context with pattern and extraction results

        Returns:
            Dictionary with classification results
        """
        context = shared_context.get()
        text = task.payload.get("text", "")
        pattern_info = context.get("document_pattern", {})
        extracted_info = context.get("extracted", {})

        if not text and not extracted_info:
            result = {
                "risk_level": "none",
                "risk_factors": [],
                "category": "unknown",
                "subcategories": [],
                "priority": "low",
                "action_required": "archive",
                "reasoning": "No content to classify",
                "confidence": 0.0,
            }
            shared_context.update({"classification": result})
            return result

        # Build context for classification
        context_parts = []
        if pattern_info:
            context_parts.append(f"Document Pattern: {json.dumps(pattern_info, indent=2)}")
        if extracted_info:
            context_parts.append(f"Extracted Data: {json.dumps(extracted_info, indent=2)}")

        context_str = "\n\n".join(context_parts) if context_parts else ""

        prompt = f"""Classify the following document based on its content and extracted information:

{context_str}

Original Document (truncated):
---
{text[:4000]}
---

Analyze the content and provide a classification including risk level, category, priority, and required actions. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Classification completed. Tokens used: {usage}")

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
                        "risk_level": "medium",
                        "risk_factors": [],
                        "category": "analyzed",
                        "subcategories": [],
                        "priority": "normal",
                        "action_required": "review_needed",
                        "reasoning": content[:300],
                        "confidence": 0.5,
                        "raw_classification": content,
                    }
            else:
                result = content

        except Exception as e:
            log.error(f"Classification failed: {e}")
            result = {
                "risk_level": "unknown",
                "risk_factors": [],
                "category": "error",
                "subcategories": [],
                "priority": "high",
                "action_required": "review_needed",
                "reasoning": f"Classification failed: {str(e)}",
                "confidence": 0.0,
                "error": str(e),
            }

        shared_context.update({"classification": result})
        return result
