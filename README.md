# Audit Flash OS (EPIC 1 + EPIC 2)

This package includes:
- **EPIC 1**: strict JSON contracts (EventEnvelope + payload schemas) and a generic validator consumer.
- **EPIC 2**: Orchestrator (state machine, backlog generation, dispatch, DoD enforcement).

## Quickstart

```bash
make up
make demo
make logs
```

Redis is exposed on **localhost:6380**.

## What to look for

1. `PROJECT.INITIAL_REQUEST_RECEIVED` is seeded by the demo script.
2. Orchestrator generates a small backlog and emits `WORK.ITEM_DISPATCHED`.
3. Any invalid event is pushed to `audit:dlq`.

## Tests

```bash
make test
```
