import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    namespace: str = os.getenv("NAMESPACE", os.getenv("APP_NAMESPACE", "audit"))
    stream_name: str = os.getenv("STREAM_NAME", "")
    dlq_stream: str = os.getenv("DLQ_STREAM", "")

    consumer_group: str = os.getenv("CONSUMER_GROUP", "")
    consumer_name: str = os.getenv("CONSUMER_NAME", "consumer-1")

    block_ms: int = int(os.getenv("BLOCK_MS", os.getenv("XREAD_BLOCK_MS", "2000")))
    idle_reclaim_ms: int = int(os.getenv("IDLE_RECLAIM_MS", os.getenv("PENDING_RECLAIM_MIN_IDLE_MS", "60000")))
    reclaim_count: int = int(os.getenv("PENDING_RECLAIM_COUNT", "50"))

    max_attempts: int = int(os.getenv("MAX_ATTEMPTS", "5"))
    dedupe_ttl_s: int = int(os.getenv("DEDUPE_TTL_SECONDS", os.getenv("IDEMPOTENCE_TTL_S", "86400")))
    idempotence_ttl_s: int = dedupe_ttl_s

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    key_prefix: str = os.getenv("KEY_PREFIX", "")
    trace_prefix: str = os.getenv("TRACE_PREFIX", "")
    metrics_prefix: str = os.getenv("METRICS_PREFIX", "")
    idempotence_prefix: str = os.getenv("IDEMPOTENCE_PREFIX", "")

    def __post_init__(self) -> None:
        namespace = (self.namespace or "audit").strip(":")
        if not self.stream_name:
            object.__setattr__(self, "stream_name", f"{namespace}:events")
        if not self.dlq_stream:
            object.__setattr__(self, "dlq_stream", f"{namespace}:dlq")
        if not self.consumer_group:
            object.__setattr__(self, "consumer_group", f"{namespace}_stream_consumers")
        if not self.key_prefix:
            object.__setattr__(self, "key_prefix", namespace)
        if not self.trace_prefix:
            object.__setattr__(self, "trace_prefix", f"{namespace}:trace")
        if not self.metrics_prefix:
            object.__setattr__(self, "metrics_prefix", f"{namespace}:metrics")
        if not self.idempotence_prefix:
            object.__setattr__(self, "idempotence_prefix", f"{namespace}:processed")

    # Compatibility aliases for settings consumed across services
    @property
    def xread_block_ms(self) -> int:
        """Preferred block duration used by stream consumers."""
        return self.block_ms

    @property
    def pending_reclaim_min_idle_ms(self) -> int:
        """Minimum idle time before attempting to reclaim pending messages."""
        return self.idle_reclaim_ms

    @property
    def pending_reclaim_count(self) -> int:
        """Maximum number of pending messages to reclaim per iteration."""
        return self.reclaim_count

    @property
    def read_block_on(self) -> int:
        """Alias kept for backward compatibility with older worker code."""
        return self.block_ms
