# Demo Scenarios

## Happy path
Run `demo/run_happy_path.sh` to seed a PROJECT.INITIAL_REQUEST_RECEIVED event and observe dispatch, grounding, validation, and completion.

## Failure and retry
Use `demo/run_failure_retry.sh` to emit a WORK.ITEM_COMPLETED without evidence. The orchestrator emits WORK.ITEM_FAILED and CLARIFICATION.NEEDED until evidence is supplied.

## Clarification required
`demo/run_clarification.sh` sends a request with missing rows; the grounding step raises MissingDataError and the orchestrator emits CLARIFICATION.NEEDED.

## Human approval gate
`demo/run_human_approval.sh` triggers HUMAN.APPROVAL_REQUESTED and then HUMAN.APPROVAL_SUBMITTED to clear the pending gate.
