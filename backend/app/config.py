from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "BSUIR Student Web App"
    bot_token: str = ""
    database_path: str = "./data/app.db"
    student_registry_path: str = "./data/student_registry.json"
    student_registry_pepper: str = "change-me"
    bsuir_api_base_url: str = "https://iis.bsuir.by/api/v1"
    telegram_init_data_max_age: int = 86400
    verification_attempts_per_hour: int = 5
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    timezone: str = "Europe/Minsk"
    web_app_url: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
