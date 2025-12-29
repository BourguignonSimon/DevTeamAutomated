# core/config.py
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    # Agent manager timeouts (seconds)
    analyze_timeout_s: int = int(os.getenv("ANALYZE_TIMEOUT_S", "600"))
    architecture_timeout_s: int = int(os.getenv("ARCHITECTURE_TIMEOUT_S", "600"))
    code_timeout_s: int = int(os.getenv("CODE_TIMEOUT_S", "900"))
    review_timeout_s: int = int(os.getenv("REVIEW_TIMEOUT_S", "300"))
    review_max_retries: int = int(os.getenv("REVIEW_MAX_RETRIES", "3"))

    stream_name: str = os.getenv("STREAM_NAME", "audit:events")
    dlq_stream: str = os.getenv("DLQ_STREAM", "audit:dlq")

    consumer_group: str = os.getenv("CONSUMER_GROUP", "audit_stream_consumers")
    consumer_name: str = os.getenv("CONSUMER_NAME", "consumer-1")

    xread_block_ms: int = int(os.getenv("XREAD_BLOCK_MS", "5000"))

    lock_ttl_s: int = int(os.getenv("LOCK_TTL_S", "300"))
    idempotence_ttl_s: int = int(os.getenv("IDEMPOTENCE_TTL_S", "604800"))

    pending_reclaim_min_idle_ms: int = int(os.getenv("PENDING_RECLAIM_MIN_IDLE_MS", "5000"))
    pending_reclaim_count: int = int(os.getenv("PENDING_RECLAIM_COUNT", "50"))

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
