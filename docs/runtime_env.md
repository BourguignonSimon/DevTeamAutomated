# Runtime Environment

All services are stateless. Configuration is provided exclusively through environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| REDIS_HOST | redis | Redis hostname |
| REDIS_PORT | 6379 | Redis port |
| REDIS_DB | 0 | Redis database index |
| NAMESPACE | audit | Base namespace for streams/keys (used when specific prefixes are unset) |
| STREAM_NAME | audit:events | Event stream name |
| DLQ_STREAM | audit:dlq | Dead-letter stream |
| CONSUMER_GROUP | audit_stream_consumers | Consumer group for stream readers |
| CONSUMER_NAME | consumer-1 | Consumer name |
| BLOCK_MS | 2000 | XREAD block duration |
| IDLE_RECLAIM_MS | 60000 | Min idle for reclamation |
| PENDING_RECLAIM_COUNT | 50 | Max reclaim count |
| KEY_PREFIX | audit | Base prefix for workflow keys (backlog/questions) |
| TRACE_PREFIX | audit:trace | Prefix for trace streams |
| METRICS_PREFIX | audit:metrics | Prefix for metrics keys |
| IDEMPOTENCE_PREFIX | audit:processed | Prefix for idempotence keys |
| LEDGER_DIR | storage/audit_log | Fact ledger directory |
| ORDERS_PREFIX | audit:orders | Prefix for order intake keys |
| VALIDATION_SET_KEY | audit:orders:pending_validation | Pending validation set for order intake |
| LOG_LEVEL | INFO | Logging verbosity |

Artifacts (fact ledgers and trace logs) write to `storage/audit_log` by default and can be mounted as a volume in Docker Compose. No local mutable state is relied on beyond Redis and the ledger directory.
