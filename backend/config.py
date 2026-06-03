"""Centralised configuration loaded from environment / .env.

Single source of truth shared by the pipeline, consumer and API so that
connection strings and thresholds never drift between components.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "store_intel"
    postgres_user: str = "store"
    postgres_password: str = "store_pass"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_stream: str = "store:events"
    redis_group: str = "store-consumers"
    redis_consumer: str = "consumer-1"

    # Pipeline
    yolo_model: str = "yolov8n.pt"
    detect_conf: float = 0.35
    target_fps: int = 10
    person_class_id: int = 0

    # Store config
    store_open_hour: int = 9
    store_close_hour: int = 21

    # Anomaly thresholds
    crowd_zscore: float = 2.5
    crowd_min_count: int = 5
    dwell_alert_seconds: int = 120
    anomaly_window: int = 60

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def pg_dsn(self) -> str:
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"dbname={self.postgres_db} user={self.postgres_user} "
            f"password={self.postgres_password}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
