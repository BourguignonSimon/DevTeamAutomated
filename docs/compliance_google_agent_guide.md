# Compliance Audit – Google Agent Recommendations

This report reviews repository alignment with recommendations R1–R15. Status levels: **DONE**, **PARTIAL**, **MISSING**.

## Summary Table
| Recommendation | Status | Evidence | Gaps / Proposed Changes |
| --- | --- | --- | --- |
| R1 Grounding step before analysis | DONE | `core/grounding.py` grounding facts with ledger writes. |  |
| R2 Separate reasoning vs execution | DONE | Orchestrator decision logging via `TraceLogger` and explicit DoD validation before execution close. |  |
| R3 Trajectory logging per agent | DONE | `core/trace.py` captures inputs/decisions/outputs. |  |
| R4 Outcome evaluation / sanity checks | DONE | `core/evaluation.py` caps totals and unit mismatches. |  |
| R5 DoD validators + orchestrator gate | DONE | `core/validators.py` registry enforced in orchestrator `process_message`. |  |
| R6 Memory tiers | DONE | Fact ledger stored under `storage/audit_log` plus Redis working state. |  |
| R7 Agent metadata / discoverability | DONE | Agent cards under `agents/metadata/*.json`. |  |
| R8 Fact ledger per audit | DONE | `core/fact_ledger.py` ledger entries for every backlog item. |  |
| R9 Human-in-loop checkpoints | DONE | HUMAN.APPROVAL_* schemas and orchestrator gate storing pending flags. |  |
| R10 Failure taxonomy | DONE | `core/failures.py` standardized categories. |  |
| R11 Metrics per agent | DONE | `core/metrics.py` counters/timers exported via snapshot. |  |
| R12 Prompt versioning + CI regression | DONE | `prompts/versions.json` with sha256 enforcement in tests. |  |
| R13 Production readiness posture | DONE | Env-driven config documented in `docs/runtime_env.md`. |  |
| R14 No silent assumptions | DONE | Grounding raises `MissingDataError` for required fields and orchestrator emits clarifications. |  |
| R15 Guardrails on extrapolation/claims | DONE | Outcome evaluator blocks unverifiable claims and caps totals. |  |

## Detailed Findings
- **Grounding:** Facts are extracted from normalized rows with provenance and persisted to a fact ledger for replay.
- **Reasoning vs execution:** Decision tracing and Definition-of-Done enforcement separate planning from completion.
- **Trajectory logging:** Each agent can emit `TraceRecord` entries capturing inputs, decisions, and outputs.
- **Outcome evaluation:** Sanity checks cap total minutes, detect unit mismatches, and raise on unverifiable claims.
- **DoD validators:** Registry-driven validators run before accepting completion; failures emit `WORK.ITEM_FAILED` and clarifications.
- **Memory tiers:** Redis keeps working state; `storage/audit_log` stores immutable ledger entries.
- **Agent metadata:** Cards enumerate capabilities, IO, and failure modes for discoverability.
- **Fact ledger:** Ledger entries link outputs back to source rows and coefficients per backlog item.
- **Human-in-loop:** Approval request/submission events set and clear pending gates.
- **Failure taxonomy:** Standard categories (tool, data insufficiency, reasoning contradiction) propagate via payloads.
- **Metrics:** Lightweight counters/timers provide observability snapshots.
- **Prompt versioning:** Versioned prompt files with hash manifest guarded by tests.
- **Production posture:** Runtime env documented; orchestration continues to avoid hidden local state.
- **No silent assumptions:** Missing critical fields raise `MissingDataError` and trigger clarifications.
- **Guardrails:** Evaluator forbids unverifiable claims and caps extrapolation.
