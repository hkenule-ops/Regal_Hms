from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "regal_hms"
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    session_cookie_name: str = "regal_session"
    session_max_age: int = 60 * 30  # 30 min idle
    trusted_device_max_age: int = 60 * 60 * 24 * 30  # 30 days
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    environment: str = "development"
    # Rate limit / lockout
    max_failed_attempts: int = 5
    lockout_minutes: int = 5
    invite_expiry_hours: int = 72
    reset_expiry_minutes: int = 30

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
