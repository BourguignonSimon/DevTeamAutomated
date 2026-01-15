from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a data extraction specialist. Your role is to extract key information, entities, and structured data from documents.

When extracting information, identify:
1. Key entities (names, organizations, dates, locations, amounts)
2. Important facts and statements
3. Numerical data and metrics
4. Relationships between entities
5. Action items or requirements

Respond with a JSON object containing:
{
    "entities": {
        "people": [],
        "organizations": [],
        "dates": [],
        "locations": [],
        "amounts": []
    },
    "key_facts": ["list of important facts"],
    "metrics": {"metric_name": "value"},
    "relationships": ["entity1 -> relationship -> entity2"],
    "action_items": ["list of action items if any"],
    "summary": "brief summary of extracted content"
}"""


class ExtractionAgent(AIAgent):
    """AI agent that extracts structured data from documents using LLM.

    This agent uses configured LLM providers to identify and extract
    entities, facts, metrics, and relationships from input documents.
    """

    def __init__(self) -> None:
        super().__init__(
            name="extraction_agent",
            role="extraction",
            system_prompt=SYSTEM_PROMPT,
            task_type="data_extraction",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Extract structured data from document using LLM.

        Args:
            task: Task containing the document text in payload["text"]
            shared_context: Shared context for storing results

        Returns:
            Dictionary with extracted data
        """
        text = task.payload.get("text", "")
        pattern_info = shared_context.get().get("document_pattern", {})

        if not text:
            result = {
                "entities": {
                    "people": [],
                    "organizations": [],
                    "dates": [],
                    "locations": [],
                    "amounts": [],
                },
                "key_facts": [],
                "metrics": {},
                "relationships": [],
                "action_items": [],
                "summary": "No content to extract from",
            }
            shared_context.update({"extracted": result})
            return result

        # Include pattern context if available
        context_hint = ""
        if pattern_info:
            pattern = pattern_info.get("pattern", "unknown")
            context_hint = f"\nDocument type hint: {pattern}\n"

        prompt = f"""Extract key information from the following document:
{context_hint}
---
{text[:8000]}
---

Extract all entities, facts, metrics, relationships, and action items. Provide your extraction as a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Data extraction completed. Tokens used: {usage}")

            # Parse the LLM response
            content = response.get("content", response.get("text", ""))
            if isinstance(content, str):
                try:
                    # Handle markdown code blocks
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0]
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0]
                    result = json.loads(content.strip())
                except json.JSONDecodeError:
                    result = {
                        "entities": {},
                        "key_facts": [],
                        "metrics": {},
                        "relationships": [],
                        "action_items": [],
                        "summary": content[:500],
                        "raw_extraction": content,
                    }
            else:
                result = content

        except Exception as e:
            log.error(f"Data extraction failed: {e}")
            result = {
                "entities": {},
                "key_facts": [],
                "metrics": {},
                "relationships": [],
                "action_items": [],
                "summary": f"Extraction failed: {str(e)}",
                "error": str(e),
            }

        shared_context.update({"extracted": result})
        return result
