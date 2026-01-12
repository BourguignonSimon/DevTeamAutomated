# Corrections to Apply

This document tracks corrections that must be addressed following the last pull request. Update the list below with concrete, actionable items as they are identified.

## Corrections

- [ ] **Issue:** Orchestrator DLQ entries can miss event metadata when `_dlq` is called with decoded events or missing `event` fields.
  - **Location:** `services/orchestrator/main.py` (`_dlq`) and `core/dlq.py` (`_try_parse_event`).
  - **Impact:** DLQ records may omit `event_id`, `event_type`, and `original_event`, which breaks tooling/tests that expect those fields.
  - **Fix:** Restore a fallback that treats non-raw payloads as the original event or pass an explicit `original_event` into `publish_dlq`.
  - **Owner:** _(Name or team)_
  - **Status:** _(Not started / In progress / Done)_

- [ ] **Issue:** Orchestrator Docker image no longer contains demo/test assets after the Dockerfile removed COPY steps.
  - **Location:** `services/orchestrator/Dockerfile`.
  - **Impact:** Docker-based smoke/integration workflows that expect `demo/`, `tests/`, or `pytest.ini` fail inside the container.
  - **Fix:** Restore the COPY steps or update the build pipeline to provide the required assets another way.
  - **Owner:** _(Name or team)_
  - **Status:** _(Not started / In progress / Done)_

- [ ] **Issue:** Documentation states `assert_transition` raises `ValueError`, but the implementation raises `IllegalTransition`.
  - **Location:** `docs/DOCUMENTATION.md` (`core.state_machine.assert_transition` description) and `core/state_machine.py`.
  - **Impact:** Engineers or tests relying on the documented exception type may implement the wrong error handling.
  - **Fix:** Update the docs to reference `IllegalTransition`, or change the code to raise `ValueError` for parity.
  - **Owner:** _(Name or team)_
  - **Status:** _(Not started / In progress / Done)_

## Notes

- Keep entries concise and actionable.
- Add new corrections as separate checklist items.
- Remove entries only after the fix is merged and verified.
