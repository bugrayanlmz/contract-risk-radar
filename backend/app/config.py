from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://radar:radar@localhost:5432/radar"
    environment: str = "development"
    jwt_secret: str = Field(
        default="local-demo-only-change-this-secret-before-hosting", min_length=32
    )
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    llm_provider: str = "claude"
    llm_model: str = ""
    anthropic_api_key: str = ""
    anthropic_workspace_id: str = ""
    gemini_api_key: str = ""
    allow_real_documents: bool = False
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pdf_pages: int = 30
    max_text_chars: int = 80_000
    samples_dir: Path = Path(__file__).resolve().parents[2] / "samples"

    @model_validator(mode="after")
    def production_secret(self):
        if self.environment != "development" and self.jwt_secret.startswith("local-demo"):
            raise ValueError("Set a unique JWT_SECRET outside development.")
        return self

    @property
    def real_documents_allowed(self) -> bool:
        return self.environment == "development" and self.allow_real_documents

    @property
    def origins(self) -> set[str]:
        return {item.strip().rstrip("/") for item in self.allowed_origins.split(",")}

    @property
    def secure_cookie(self) -> bool:
        return self.environment != "development"

    @property
    def queue_conninfo(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
