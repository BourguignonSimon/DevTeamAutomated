import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    stream_name: str = os.getenv("STREAM_NAME", "audit:events")
    dlq_stream: str = os.getenv("DLQ_STREAM", "audit:dlq")

    consumer_group: str = os.getenv("CONSUMER_GROUP", "audit_stream_consumers")
    consumer_name: str = os.getenv("CONSUMER_NAME", "consumer-1")

    block_ms: int = int(os.getenv("BLOCK_MS", os.getenv("XREAD_BLOCK_MS", "2000")))
    idle_reclaim_ms: int = int(os.getenv("IDLE_RECLAIM_MS", os.getenv("PENDING_RECLAIM_MIN_IDLE_MS", "60000")))
    reclaim_count: int = int(os.getenv("PENDING_RECLAIM_COUNT", "50"))

    max_attempts: int = int(os.getenv("MAX_ATTEMPTS", "5"))
    dedupe_ttl_s: int = int(os.getenv("DEDUPE_TTL_SECONDS", os.getenv("IDEMPOTENCE_TTL_S", "86400")))
    idempotence_ttl_s: int = dedupe_ttl_s

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
