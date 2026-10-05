import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    APP_TITLE: str = "신용등급 자동조사 시스템"
    APP_ENV: str = "development"
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/data/credit_rating.db"
    LOG_LEVEL: str = "INFO"
    CRON_SCHEDULE: str = "0 6 * * *"
    ENABLE_AUTO_SCHEDULER: bool = False
    API_V1_PREFIX: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure data directory exists
os.makedirs(BASE_DIR / "data", exist_ok=True)
