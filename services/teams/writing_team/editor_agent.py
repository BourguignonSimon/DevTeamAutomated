from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert editor and content strategist. Your role is to review, structure, and improve written content for clarity, coherence, and impact.

When editing content, focus on:
1. Document structure and organization
2. Clarity and readability
3. Logical flow and transitions
4. Grammar, spelling, and punctuation
5. Tone and voice consistency
6. Content completeness

Respond with a JSON object containing:
{
    "edited_content": "the improved content",
    "outline": {
        "sections": [
            {"title": "section title", "key_points": ["point1", "point2"]}
        ],
        "structure_type": "narrative|technical|persuasive|informational"
    },
    "changes_made": [
        {"type": "structural|clarity|grammar|tone", "description": "what was changed"}
    ],
    "suggestions": ["additional improvement suggestions"],
    "readability_score": "elementary|intermediate|advanced|technical",
    "word_count": {"original": 0, "edited": 0}
}"""


class EditorAgent(AIAgent):
    """AI agent that edits and structures written content using LLM.

    This agent uses configured LLM providers to review, improve, and
    structure written content for clarity, coherence, and impact.
    """

    def __init__(self) -> None:
        super().__init__(
            name="editor_agent",
            role="editor",
            system_prompt=SYSTEM_PROMPT,
            task_type="text_generation",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Edit and structure content using LLM.

        Args:
            task: Task containing content in payload["text"] or payload["content"]
            shared_context: Shared context for storing results

        Returns:
            Dictionary with edited content and structural analysis
        """
        text = task.payload.get("text", task.payload.get("content", ""))
        style_guide = task.payload.get("style_guide", "")
        target_audience = task.payload.get("target_audience", "general")

        if not text:
            result = {
                "edited_content": "",
                "outline": {
                    "sections": [],
                    "structure_type": "unknown",
                },
                "changes_made": [],
                "suggestions": ["No content provided for editing"],
                "readability_score": "unknown",
                "word_count": {"original": 0, "edited": 0},
            }
            shared_context.update({"writing_outline": result})
            return result

        # Build editing context
        context_parts = []
        if style_guide:
            context_parts.append(f"Style Guide: {style_guide}")
        if target_audience:
            context_parts.append(f"Target Audience: {target_audience}")

        context_str = "\n".join(context_parts) if context_parts else ""

        prompt = f"""Review and edit the following content for clarity, structure, and impact:

{context_str}

Content to edit:
---
{text[:10000]}
---

Provide structural improvements, create an outline, and suggest enhancements. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Content editing completed. Tokens used: {usage}")

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
                        "edited_content": content,
                        "outline": {
                            "sections": [],
                            "structure_type": "analyzed",
                        },
                        "changes_made": [],
                        "suggestions": [],
                        "readability_score": "intermediate",
                        "word_count": {
                            "original": len(text.split()),
                            "edited": len(content.split()),
                        },
                        "raw_edit": content,
                    }
            else:
                result = content

        except Exception as e:
            log.error(f"Content editing failed: {e}")
            result = {
                "edited_content": text,
                "outline": {
                    "sections": [],
                    "structure_type": "original",
                },
                "changes_made": [],
                "suggestions": [f"Automated editing failed: {str(e)}"],
                "readability_score": "unknown",
                "word_count": {"original": len(text.split()), "edited": len(text.split())},
                "error": str(e),
            }

        shared_context.update({"writing_outline": result})
        return result
