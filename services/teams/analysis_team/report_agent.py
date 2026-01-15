from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agent_team import AIAgent, SharedContext, TeamTask

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a report generation specialist. Your role is to synthesize analysis results into comprehensive, well-structured reports.

When generating reports, include:
1. Executive summary highlighting key findings
2. Detailed analysis breakdown
3. Risk assessment summary
4. Recommendations and next steps
5. Supporting data and evidence

Respond with a JSON object containing:
{
    "executive_summary": "brief summary for executives (2-3 sentences)",
    "key_findings": [
        {"finding": "description", "severity": "critical|high|medium|low|info", "evidence": "supporting data"}
    ],
    "risk_summary": {
        "overall_risk": "critical|high|medium|low|none",
        "risk_count_by_level": {"critical": 0, "high": 0, "medium": 0, "low": 0}
    },
    "recommendations": [
        {"recommendation": "description", "priority": "high|medium|low", "rationale": "why this matters"}
    ],
    "detailed_sections": [
        {"title": "section title", "content": "section content"}
    ],
    "appendix": {
        "data_sources": ["list of sources"],
        "methodology": "brief description of analysis approach"
    },
    "report_metadata": {
        "generated_at": "timestamp",
        "confidence_level": "high|medium|low"
    }
}"""


class ReportAgent(AIAgent):
    """AI agent that generates comprehensive reports using LLM.

    This agent uses configured LLM providers to synthesize all analysis
    results into well-structured, actionable reports.
    """

    def __init__(self) -> None:
        super().__init__(
            name="report_agent",
            role="report",
            system_prompt=SYSTEM_PROMPT,
            task_type="text_generation",
        )

    def execute(self, task: TeamTask, shared_context: SharedContext) -> Dict[str, Any]:
        """Generate comprehensive report using LLM.

        Args:
            task: Task containing the document text in payload["text"]
            shared_context: Shared context with all analysis results

        Returns:
            Dictionary with generated report
        """
        import datetime

        context = shared_context.get()
        text = task.payload.get("text", "")
        pattern_info = context.get("document_pattern", {})
        extracted_info = context.get("extracted", {})
        classification = context.get("classification", {})
        remediation = context.get("remediation", {})

        # Check if we have enough data to generate a report
        if not any([pattern_info, extracted_info, classification, remediation]):
            result = {
                "executive_summary": "Insufficient data for report generation",
                "key_findings": [],
                "risk_summary": {
                    "overall_risk": "unknown",
                    "risk_count_by_level": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                },
                "recommendations": [],
                "detailed_sections": [],
                "appendix": {
                    "data_sources": [],
                    "methodology": "No analysis data available",
                },
                "report_metadata": {
                    "generated_at": datetime.datetime.now().isoformat(),
                    "confidence_level": "low",
                },
            }
            shared_context.update({"report": result})
            return result

        # Build comprehensive context for report generation
        analysis_data = {
            "document_pattern": pattern_info,
            "extracted_data": extracted_info,
            "classification": classification,
            "remediation_proposal": remediation,
        }

        prompt = f"""Generate a comprehensive analysis report based on the following analysis results:

Analysis Data:
{json.dumps(analysis_data, indent=2)}

Original Document (truncated for context):
---
{text[:2000]}
---

Create a well-structured report that synthesizes all findings, provides an executive summary, highlights key risks, and offers actionable recommendations. Respond with a JSON object."""

        try:
            response, usage = self.predict(prompt)
            log.info(f"Report generation completed. Tokens used: {usage}")

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
                        "executive_summary": content[:500],
                        "key_findings": [],
                        "risk_summary": {
                            "overall_risk": classification.get("risk_level", "unknown"),
                            "risk_count_by_level": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                        },
                        "recommendations": [],
                        "detailed_sections": [{"title": "Analysis", "content": content}],
                        "appendix": {
                            "data_sources": ["document analysis"],
                            "methodology": "LLM-based analysis",
                        },
                        "report_metadata": {
                            "generated_at": datetime.datetime.now().isoformat(),
                            "confidence_level": "medium",
                        },
                        "raw_report": content,
                    }
            else:
                result = content

            # Ensure metadata is present
            if "report_metadata" not in result:
                result["report_metadata"] = {}
            result["report_metadata"]["generated_at"] = datetime.datetime.now().isoformat()

        except Exception as e:
            log.error(f"Report generation failed: {e}")
            result = {
                "executive_summary": f"Report generation encountered an error: {str(e)}",
                "key_findings": [],
                "risk_summary": {
                    "overall_risk": classification.get("risk_level", "unknown"),
                    "risk_count_by_level": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                },
                "recommendations": [
                    {
                        "recommendation": "Manual review required",
                        "priority": "high",
                        "rationale": "Automated report generation failed",
                    }
                ],
                "detailed_sections": [],
                "appendix": {
                    "data_sources": ["partial analysis data"],
                    "methodology": "Incomplete due to error",
                },
                "report_metadata": {
                    "generated_at": datetime.datetime.now().isoformat(),
                    "confidence_level": "low",
                    "error": str(e),
                },
            }

        shared_context.update({"report": result})
        return {"report": result, "context": context}
