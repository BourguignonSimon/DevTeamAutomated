from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an email parsing and analysis specialist. Your role is to analyze emails to extract intent, sentiment, key information, and required actions.

When parsing an email, identify:
1. Primary intent (request, complaint, inquiry, feedback, notification, etc.)
2. Sentiment (positive, negative, neutral, urgent)
3. Key entities (sender info, recipients, dates, references)
4. Action items and requests
5. Priority level
6. Required response type

Respond with a JSON object containing:
{
    "intent": {
        "primary": "request|complaint|inquiry|feedback|notification|response|other",
        "secondary": ["additional intents if any"],
        "confidence": 0.0-1.0
    },
    "sentiment": {
        "overall": "positive|negative|neutral|mixed",
        "urgency": "critical|high|medium|low",
        "tone": "formal|informal|friendly|frustrated|neutral"
    },
    "extracted_info": {
        "sender": {"name": "", "email": "", "organization": ""},
        "recipients": [],
        "dates_mentioned": [],
        "references": [],
        "attachments_mentioned": []
    },
    "action_items": [
        {"action": "description", "deadline": "if mentioned", "assignee": "if mentioned"}
    ],
    "key_points": ["list of main points"],
    "suggested_response_type": "acknowledgment|detailed_response|escalation|no_response_needed",
    "priority": "critical|high|medium|low"
}"""


class EmailParserAgent(AIAgent):
    """AI agent that parses and analyzes emails using LLM.

    This agent uses configured LLM providers to extract intent,
    sentiment, and key information from email content.
    """

    def __init__(self) -> None:
        super().__init__(
            name="parser_agent",
            role="parser",
            system_prompt=SYSTEM_PROMPT,
            task_type="text_analysis",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Parse and analyze email content using LLM.

        Args:
            task: Task containing email in payload["email"] or payload["text"]
            shared_context: Shared context for storing results

        Returns:
            Dictionary with parsed email analysis
        """
        email_content = task.payload.get("email", task.payload.get("text", ""))
        subject = task.payload.get("subject", "")
        sender = task.payload.get("sender", "")

        if not email_content:
            result = {
                "intent": {
                    "primary": "unknown",
                    "secondary": [],
                    "confidence": 0.0,
                },
                "sentiment": {
                    "overall": "neutral",
                    "urgency": "low",
                    "tone": "neutral",
                },
                "extracted_info": {
                    "sender": {"name": "", "email": "", "organization": ""},
                    "recipients": [],
                    "dates_mentioned": [],
                    "references": [],
                    "attachments_mentioned": [],
                },
                "action_items": [],
                "key_points": ["No email content provided"],
                "suggested_response_type": "no_response_needed",
                "priority": "low",
            }
            shared_context.update({"email_intent": result["intent"]["primary"], "email_parsed": result})
            return result

        # Build email context
        email_header = []
        if subject:
            email_header.append(f"Subject: {subject}")
        if sender:
            email_header.append(f"From: {sender}")

        header_str = "\n".join(email_header) if email_header else ""

        prompt = f"""Parse and analyze the following email:

{header_str}

Email Body:
---
{email_content[:6000]}
---

Extract intent, sentiment, key information, and action items. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Email parsing completed. Tokens used: {usage}")

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
                        "intent": {
                            "primary": "analyzed",
                            "secondary": [],
                            "confidence": 0.7,
                        },
                        "sentiment": {
                            "overall": "neutral",
                            "urgency": "medium",
                            "tone": "neutral",
                        },
                        "extracted_info": {},
                        "action_items": [],
                        "key_points": [content[:200]],
                        "suggested_response_type": "detailed_response",
                        "priority": "medium",
                        "raw_analysis": content,
                    }
            else:
                result = content

            # Extract primary intent for backward compatibility
            primary_intent = result.get("intent", {}).get("primary", "general")

        except Exception as e:
            log.error(f"Email parsing failed: {e}")
            result = {
                "intent": {
                    "primary": "error",
                    "secondary": [],
                    "confidence": 0.0,
                },
                "sentiment": {
                    "overall": "neutral",
                    "urgency": "medium",
                    "tone": "neutral",
                },
                "extracted_info": {},
                "action_items": [],
                "key_points": [f"Parsing failed: {str(e)}"],
                "suggested_response_type": "detailed_response",
                "priority": "medium",
                "error": str(e),
            }
            primary_intent = "error"

        shared_context.update({"email_intent": primary_intent, "email_parsed": result})
        return result
