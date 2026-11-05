from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    storage_dir: Path = ROOT / "data"
    model_checkpoint: str = ""
    model_label: str = "RegGAN baseline"
    model_device: str = "cpu"
    model_registry_path: str = ""
    archive_limit_mb: int = 4096
    max_voxels: int = 268435456

    @property
    def jobs_dir(self):
        return self.storage_dir.resolve() / "jobs"


@lru_cache
def get_settings():
    return Settings()
