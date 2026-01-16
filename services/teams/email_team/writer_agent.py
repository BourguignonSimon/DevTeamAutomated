from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert email writer and communication specialist. Your role is to compose professional, clear, and effective email responses based on context and requirements.

When writing emails, ensure:
1. Appropriate tone matching the context
2. Clear and concise messaging
3. Professional formatting and structure
4. Proper addressing and sign-off
5. Complete response to all points raised
6. Call to action when needed

Respond with a JSON object containing:
{
    "email_draft": {
        "subject": "suggested subject line",
        "greeting": "appropriate greeting",
        "body": "main email content",
        "closing": "appropriate closing",
        "signature": "suggested signature"
    },
    "full_email": "complete formatted email text",
    "tone_used": "formal|semi-formal|friendly|apologetic|assertive",
    "key_points_addressed": ["list of points covered"],
    "suggested_attachments": ["if any attachments should be included"],
    "follow_up_needed": true|false,
    "alternative_versions": [
        {"tone": "different tone", "preview": "brief preview of alternative"}
    ]
}"""


class EmailWriterAgent(AIAgent):
    """AI agent that composes email responses using LLM.

    This agent uses configured LLM providers to generate professional,
    contextually appropriate email responses.
    """

    def __init__(self) -> None:
        super().__init__(
            name="writer_agent",
            role="writer",
            system_prompt=SYSTEM_PROMPT,
            task_type="text_generation",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Compose email response using LLM.

        Args:
            task: Task containing context in payload
            shared_context: Shared context with parsed email info

        Returns:
            Dictionary with composed email draft
        """
        context = shared_context.get()
        original_email = task.payload.get("email", task.payload.get("text", ""))
        parsed_info = context.get("email_parsed", {})
        email_intent = context.get("email_intent", "general")
        response_guidelines = task.payload.get("guidelines", "")
        sender_name = task.payload.get("sender_name", "")

        if not original_email and not parsed_info:
            result = {
                "email_draft": {
                    "subject": "",
                    "greeting": "",
                    "body": "",
                    "closing": "",
                    "signature": "",
                },
                "full_email": "",
                "tone_used": "neutral",
                "key_points_addressed": [],
                "suggested_attachments": [],
                "follow_up_needed": False,
                "alternative_versions": [],
                "error": "No context provided for email composition",
            }
            shared_context.update({"email_draft": result})
            return result

        # Build composition context
        context_parts = []
        if parsed_info:
            context_parts.append(f"Email Analysis:\n{json.dumps(parsed_info, indent=2)}")
        if response_guidelines:
            context_parts.append(f"Response Guidelines:\n{response_guidelines}")
        if sender_name:
            context_parts.append(f"Sender Name (for signature): {sender_name}")

        context_str = "\n\n".join(context_parts)

        prompt = f"""Compose a professional email response based on the following context:

{context_str}

Original Email (if available):
---
{original_email[:4000] if original_email else 'See analysis above'}
---

Intent to address: {email_intent}

Write a complete email response. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Email composition completed. Tokens used: {usage}")

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
                    # If JSON parsing fails, treat the response as the email body
                    result = {
                        "email_draft": {
                            "subject": f"Re: {parsed_info.get('extracted_info', {}).get('subject', 'Your message')}",
                            "greeting": "Hello,",
                            "body": content,
                            "closing": "Best regards,",
                            "signature": sender_name or "",
                        },
                        "full_email": content,
                        "tone_used": "professional",
                        "key_points_addressed": [],
                        "suggested_attachments": [],
                        "follow_up_needed": False,
                        "alternative_versions": [],
                        "raw_draft": content,
                    }
            else:
                result = content

            # Generate full email if not provided
            if not result.get("full_email") and result.get("email_draft"):
                draft = result["email_draft"]
                result["full_email"] = f"{draft.get('greeting', '')}\n\n{draft.get('body', '')}\n\n{draft.get('closing', '')}\n{draft.get('signature', '')}"

        except Exception as e:
            log.error(f"Email composition failed: {e}")
            result = {
                "email_draft": {
                    "subject": "",
                    "greeting": "",
                    "body": "",
                    "closing": "",
                    "signature": "",
                },
                "full_email": "",
                "tone_used": "error",
                "key_points_addressed": [],
                "suggested_attachments": [],
                "follow_up_needed": True,
                "alternative_versions": [],
                "error": f"Email composition failed: {str(e)}",
            }

        shared_context.update({"email_draft": result})
        return result
