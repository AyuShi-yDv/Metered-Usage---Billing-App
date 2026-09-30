from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    rabbitmq_url: str
    internal_token: str
    max_body_bytes: int = 16_384
    # Fixed-window limit per account. The counter lives in process memory, so it
    # is exact only when one worker process runs (the default, WEB_CONCURRENCY=1).
    rate_limit_per_minute: int = 600
    # A revoked key keeps working for at most this long (per-process cache TTL).
    key_cache_ttl_seconds: float = 5.0
    outbox_batch_size: int = 100
    outbox_poll_seconds: float = 0.25
    outbox_retention_hours: int = 168
    cors_origins: str = "http://localhost:5173"


settings = Settings()
