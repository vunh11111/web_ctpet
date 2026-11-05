from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = "postgresql+psycopg://petdemo:petdemo@127.0.0.1:55432/petdemo"
    storage_dir: Path = ROOT / "data"
    model_api_url: str = "http://127.0.0.1:8109"
    cors_origins: str = "http://localhost:3108,http://127.0.0.1:3108"
    upload_limit_mb: int = 2048
    archive_limit_mb: int = 4096
    auth_enabled: bool = True
    auth_mode: Literal["password", "guest"] = "password"
    auth_username: str = "demo"
    auth_password_hash: SecretStr = SecretStr("")
    auth_signing_secret: SecretStr = SecretStr("")
    auth_ttl_seconds: int = 28800

    @property
    def jobs_dir(self):
        return self.storage_dir.resolve() / "jobs"


@lru_cache
def get_settings():
    return Settings()
