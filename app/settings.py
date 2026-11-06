from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    auth_issuer: str
    auth_audience: str
    auth_jwks_url: str
    cors_origins: str = "http://localhost:3000"
    document_storage_root: str = "/tmp/immigrationos-dev-documents"
    document_encryption_key: str = ""
    uploads_enabled: bool = False
    experimental_ai_enabled: bool = False
    ai_api_key: str = ""
    ai_model: str = ""
    clamav_enabled: bool = False
    clamav_host: str = "127.0.0.1"
    clamav_port: int = 3310


    @field_validator("cors_origins")
    @classmethod
    def forbid_wildcard(cls, value: str) -> str:
        if "*" in value.split(","):
            raise ValueError("Wildcard CORS origins forbidden")
        return value

    @model_validator(mode="after")
    def validate_production(self):
        if self.uploads_enabled and not self.document_encryption_key:
            raise ValueError("Uploads require a configured encryption key")
        if self.experimental_ai_enabled and (not self.ai_api_key or not self.ai_model):
            raise ValueError("Experimental AI requires an API key and explicit model")
        if self.environment == "production":
            if self.experimental_ai_enabled:
                raise ValueError("Experimental AI blocked in production pending a full privacy/security review")
            if self.uploads_enabled:
                raise ValueError("Uploads remain disabled in production until malware scanning and storage review")
            if not self.auth_issuer.startswith("https://") or not self.auth_jwks_url.startswith("https://"):
                raise ValueError("Production OIDC issuer and JWKS URL must use HTTPS")
            if any(word in self.database_url.lower() for word in ["dev_only", "localhost", "sqlite"]):
                raise ValueError("Production database cannot use development credentials or SQLite")
        return self


@lru_cache

def get_settings() -> Settings:
    return Settings()
