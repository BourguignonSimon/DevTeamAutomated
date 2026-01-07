# Runtime Environment

All services are stateless. Configuration is provided exclusively through environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| REDIS_HOST | redis | Redis hostname |
| REDIS_PORT | 6379 | Redis port |
| REDIS_DB | 0 | Redis database index |
| STREAM_NAME | audit:events | Event stream name |
| DLQ_STREAM | audit:dlq | Dead-letter stream |
| CONSUMER_GROUP | audit_stream_consumers | Consumer group for stream readers |
| CONSUMER_NAME | consumer-1 | Consumer name |
| BLOCK_MS | 2000 | XREAD block duration |
| IDLE_RECLAIM_MS | 60000 | Min idle for reclamation |
| PENDING_RECLAIM_COUNT | 50 | Max reclaim count |
| LOG_LEVEL | INFO | Logging verbosity |

Artifacts (fact ledgers and audit traces) write to `storage/audit_log` and can be mounted as a volume in Docker Compose. No local mutable state is relied on beyond Redis and the audit log directory.
