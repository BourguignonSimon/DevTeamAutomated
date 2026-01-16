from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a document pattern analysis expert. Your role is to analyze documents and identify their structural patterns, document types, and key characteristics.

When analyzing a document, identify:
1. Document type (contract, report, email, memo, technical documentation, etc.)
2. Structural pattern (formal, informal, technical, legal, etc.)
3. Key sections and their purposes
4. Overall document purpose

Respond with a JSON object containing:
{
    "pattern": "document_type",
    "structure": "structural_pattern",
    "sections": ["list", "of", "key", "sections"],
    "purpose": "brief description of document purpose",
    "confidence": 0.0 to 1.0
}"""


class PatternAgent(AIAgent):
    """AI agent that analyzes document patterns using LLM.

    This agent uses configured LLM providers to identify document types,
    structural patterns, and key characteristics of input documents.
    """

    def __init__(self) -> None:
        super().__init__(
            name="pattern_agent",
            role="pattern",
            system_prompt=SYSTEM_PROMPT,
            task_type="text_analysis",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Analyze document patterns using LLM.

        Args:
            task: Task containing the document text in payload["text"]
            shared_context: Shared context for storing results

        Returns:
            Dictionary with pattern analysis results
        """
        text = task.payload.get("text", "")

        if not text:
            result = {
                "pattern": "unknown",
                "structure": "empty",
                "sections": [],
                "purpose": "No content provided",
                "confidence": 0.0,
            }
            shared_context.update({"document_pattern": result})
            return result

        prompt = f"""Analyze the following document and identify its pattern and structure:

---
{text[:8000]}
---

Provide your analysis as a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Pattern analysis completed. Tokens used: {usage}")

            # Parse the LLM response
            content = response.get("content", response.get("text", ""))
            if isinstance(content, str):
                # Try to extract JSON from the response
                try:
                    # Handle markdown code blocks
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0]
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0]
                    result = json.loads(content.strip())
                except json.JSONDecodeError:
                    # Fallback to structured result from text
                    result = {
                        "pattern": "analyzed",
                        "structure": "identified",
                        "sections": [],
                        "purpose": content[:200],
                        "confidence": 0.7,
                        "raw_analysis": content,
                    }
            else:
                result = content

        except Exception as e:
            log.error(f"Pattern analysis failed: {e}")
            result = {
                "pattern": "error",
                "structure": "unknown",
                "sections": [],
                "purpose": f"Analysis failed: {str(e)}",
                "confidence": 0.0,
            }

        shared_context.update({"document_pattern": result})
        return result
