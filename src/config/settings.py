from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_path(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sf_client_id: str = Field(..., min_length=1, description="Salesforce Connected App Consumer Key")
    sf_client_secret: str = Field(..., min_length=1, description="Salesforce Connected App Consumer Secret")
    sf_redirect_uri: str = Field(..., min_length=1, description="OAuth callback URL")
    sf_api_version: str = Field(default="59.0", description="Salesforce API version")
    sf_login_domain: str = Field(default="login", description="login (prod) or test (sandbox)")
    neo4j_mode: str = Field(default="local", pattern="^(local|remote)$")
    neo4j_local_uri: str = Field(default="bolt://127.0.0.1:7687")
    neo4j_local_user: str = Field(default="neo4j")
    neo4j_local_password: str = Field(default="salesforce-impact-local", min_length=8)
    neo4j_uri: str | None = Field(default=None)
    neo4j_username: str | None = Field(default=None)
    neo4j_password: str | None = Field(default=None)
    neo4j_database: str = Field(default="neo4j")


def get_settings() -> Settings:
    return Settings()
