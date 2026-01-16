from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a style and tone consistency expert. Your role is to analyze content for style consistency and ensure it adheres to brand voice, tone guidelines, and formatting standards.

When analyzing style, evaluate:
1. Tone consistency (formal, casual, technical, friendly, etc.)
2. Voice and perspective consistency
3. Terminology and vocabulary usage
4. Formatting and presentation standards
5. Brand alignment and messaging consistency
6. Cultural sensitivity and inclusivity

Respond with a JSON object containing:
{
    "style_analysis": {
        "detected_tone": "formal|casual|technical|friendly|neutral",
        "voice": "first_person|second_person|third_person|mixed",
        "formality_level": 1-10,
        "consistency_score": 0.0-1.0
    },
    "issues_found": [
        {"issue": "description", "location": "approximate location", "severity": "high|medium|low", "suggestion": "fix"}
    ],
    "tone_adjustments": [
        {"original": "original phrase", "suggested": "adjusted phrase", "reason": "why"}
    ],
    "vocabulary_suggestions": {
        "terms_to_avoid": ["list of terms"],
        "preferred_alternatives": {"old_term": "preferred_term"}
    },
    "overall_assessment": "summary of style quality",
    "recommendations": ["list of style improvement recommendations"]
}"""


class StyleKeeperAgent(AIAgent):
    """AI agent that ensures style and tone consistency using LLM.

    This agent uses configured LLM providers to analyze content for
    style consistency and adherence to tone guidelines.
    """

    def __init__(self) -> None:
        super().__init__(
            name="style_keeper_agent",
            role="style",
            system_prompt=SYSTEM_PROMPT,
            task_type="text_analysis",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Analyze and enforce style consistency using LLM.

        Args:
            task: Task containing content in payload["text"] or payload["content"]
            shared_context: Shared context with editing results

        Returns:
            Dictionary with style analysis and recommendations
        """
        text = task.payload.get("text", task.payload.get("content", ""))
        style_guide = task.payload.get("style_guide", "")
        brand_voice = task.payload.get("brand_voice", "")
        editing_result = shared_context.get().get("writing_outline", {})

        # Use edited content if available
        content_to_analyze = editing_result.get("edited_content", text)

        if not content_to_analyze:
            result = {
                "style_analysis": {
                    "detected_tone": "unknown",
                    "voice": "unknown",
                    "formality_level": 0,
                    "consistency_score": 0.0,
                },
                "issues_found": [],
                "tone_adjustments": [],
                "vocabulary_suggestions": {
                    "terms_to_avoid": [],
                    "preferred_alternatives": {},
                },
                "overall_assessment": "No content provided for style analysis",
                "recommendations": [],
            }
            shared_context.update({"writing_style": result})
            return result

        # Build style context
        context_parts = []
        if style_guide:
            context_parts.append(f"Style Guide Requirements:\n{style_guide}")
        if brand_voice:
            context_parts.append(f"Brand Voice Description:\n{brand_voice}")

        context_str = "\n\n".join(context_parts) if context_parts else ""

        prompt = f"""Analyze the following content for style and tone consistency:

{context_str}

Content to analyze:
---
{content_to_analyze[:8000]}
---

Evaluate tone, voice, formality, and consistency. Identify style issues and suggest improvements. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Style analysis completed. Tokens used: {usage}")

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
                        "style_analysis": {
                            "detected_tone": "analyzed",
                            "voice": "detected",
                            "formality_level": 5,
                            "consistency_score": 0.7,
                        },
                        "issues_found": [],
                        "tone_adjustments": [],
                        "vocabulary_suggestions": {
                            "terms_to_avoid": [],
                            "preferred_alternatives": {},
                        },
                        "overall_assessment": content[:500],
                        "recommendations": [],
                        "raw_analysis": content,
                    }
            else:
                result = content

        except Exception as e:
            log.error(f"Style analysis failed: {e}")
            result = {
                "style_analysis": {
                    "detected_tone": "error",
                    "voice": "unknown",
                    "formality_level": 0,
                    "consistency_score": 0.0,
                },
                "issues_found": [],
                "tone_adjustments": [],
                "vocabulary_suggestions": {
                    "terms_to_avoid": [],
                    "preferred_alternatives": {},
                },
                "overall_assessment": f"Style analysis failed: {str(e)}",
                "recommendations": ["Manual style review required"],
                "error": str(e),
            }

        shared_context.update({"writing_style": result})
        return result
