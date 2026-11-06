# backend/config.py
from functools import lru_cache
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required: the app refuses to start without these.
    database_url: str
    agent_database_url: str | None = None
    jwt_secret_key: str = Field(min_length=32)

    # Authentication
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Database connection pool
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 1800

    # Frontend origins, comma-separated in .env
    cors_origins: str = "http://localhost:5173"

    # Chat pipeline
    llm_chat_enabled: bool = True
    model_server_url: str = "http://127.0.0.1:8001/predict"
    model_timeout_seconds: float = 60.0
    model_checkpoint_path: str = "data/artifacts/tickora_intent_model.pt"

    # Business defaults
    app_timezone: str = "Asia/Kolkata"

    agent_orchestration: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("jwt_algorithm")
    @classmethod
    def _only_hs256(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("This application requires HS256.")
        return value

@lru_cache
def get_settings() -> Settings:
    return Settings()