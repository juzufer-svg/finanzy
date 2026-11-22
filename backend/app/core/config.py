"""Configuración central de Finanzy; los secretos críticos nunca tienen defaults."""
from typing import List
from urllib.parse import urlparse
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Finanzy"
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    SECRET_KEY: str = Field(min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=5, le=1440)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    DATABASE_URL: str = ""
    BREVO_API_KEY: str = ""
    SENDGRID_API_KEY: str = ""
    FROM_EMAIL: str = ""
    FROM_NAME: str = "Finanzy"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, origins: List[str]) -> List[str]:
        cleaned = []
        for origin in origins:
            value = origin.strip().rstrip("/")
            parsed = urlparse(value)
            if value == "*" or not parsed.scheme or not parsed.netloc:
                raise ValueError("CORS_ORIGINS requiere orígenes HTTP(S) exactos, sin comodines")
            if parsed.scheme not in {"http", "https"} or parsed.path or parsed.query or parsed.fragment:
                raise ValueError("Cada origen CORS debe contener solo esquema y host HTTP(S)")
            if value not in cleaned:
                cleaned.append(value)
        return cleaned

    @model_validator(mode="after")
    def validate_production_configuration(self):
        if self.ALGORITHM != "HS256":
            raise ValueError("Solo se permite HS256 para los JWT de esta versión")
        if self.ENVIRONMENT.lower() == "production":
            if not self.SUPABASE_URL or not self.SUPABASE_KEY:
                raise ValueError("Producción requiere SUPABASE_URL y SUPABASE_KEY; no se permite modo demo")
            if self.DEBUG:
                raise ValueError("DEBUG debe estar deshabilitado en producción")
        return self

settings = Settings()
