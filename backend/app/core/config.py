"""
Configuración de la aplicación (variables de entorno).

Regla de diseño (CHG-002): una configuración insegura NUNCA impide que el
backend arranque; se corrige a un valor seguro y se avisa en los logs con
«[CONFIG]». Así un despliegue no deja la app caída por una variable que ya
existía en Railway, pero tampoco se usa un valor peligroso.
"""
import secrets
from typing import List
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valores de ejemplo que han aparecido en el repositorio: son públicos, así que
# quien los conozca podría firmar tokens válidos. Nunca deben usarse como clave.
_CLAVES_PUBLICAS = ("your-secret-key", "change-in-production", "replace_with")
_LONGITUD_RECOMENDADA = 32
_ALGORITMOS_PERMITIDOS = {"HS256", "HS384", "HS512"}
# Duración de la sesión: 7 días por defecto (REQ-F-002); se acepta de 5 min a 30 días.
_MINUTOS_SESION_POR_DEFECTO = 10080
_MINUTOS_SESION_MIN = 5
_MINUTOS_SESION_MAX = 43200


def _avisar(mensaje: str) -> None:
    print(f"[CONFIG] ⚠️  {mensaje}")


def _clave_es_publica(clave: str) -> bool:
    valor = (clave or "").strip().lower()
    return not valor or any(marca in valor for marca in _CLAVES_PUBLICAS)


def _origen_cors_valido(origen: str) -> bool:
    """Solo orígenes exactos http(s)://host[:puerto], sin comodines ni rutas."""
    if "*" in origen:
        return False
    partes = urlparse(origen)
    return (
        partes.scheme in {"http", "https"}
        and bool(partes.netloc)
        and not partes.username
        and not partes.password
        and partes.path in {"", "/"}
        and not partes.query
        and not partes.fragment
    )


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Finanzy"

    # CORS: orígenes exactos que pueden llamar al backend desde el navegador.
    # El frontend usa el proxy de Next.js (servidor a servidor), así que en
    # producción normalmente no hace falta configurar nada aquí.
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # JWT
    SECRET_KEY: str = Field(default="")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _MINUTOS_SESION_POR_DEFECTO

    # Supabase
    SUPABASE_URL: str = Field(default="")
    SUPABASE_KEY: str = Field(default="")
    SUPABASE_ANON_KEY: str = Field(default="")

    # Database
    DATABASE_URL: str = Field(default="")

    # Correo transaccional (Brevo)
    BREVO_API_KEY: str = Field(default="")
    FROM_EMAIL: str = Field(default="")  # remitente verificado en Brevo
    FROM_NAME: str = Field(default="Finanzy")

    # Environment
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=False)

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    @property
    def es_produccion(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "production"

    @model_validator(mode="after")
    def _corregir_configuracion_insegura(self):
        # 1) Clave de firma de los JWT
        if _clave_es_publica(self.SECRET_KEY):
            _avisar(
                "SECRET_KEY no está configurada o es un valor de ejemplo público. Se usa una clave "
                "aleatoria temporal: las sesiones se cerrarán en cada reinicio. Configura SECRET_KEY "
                f"en Railway con {_LONGITUD_RECOMENDADA} caracteres aleatorios o más."
            )
            self.SECRET_KEY = secrets.token_urlsafe(48)
        elif len(self.SECRET_KEY) < _LONGITUD_RECOMENDADA:
            _avisar(
                f"SECRET_KEY tiene menos de {_LONGITUD_RECOMENDADA} caracteres. Sigue funcionando, "
                "pero conviene reemplazarla por una más larga (cerrará las sesiones abiertas)."
            )

        # 2) Algoritmo: solo HMAC (security.py también lo fuerza)
        if self.ALGORITHM not in _ALGORITMOS_PERMITIDOS:
            _avisar(f"ALGORITHM='{self.ALGORITHM}' no está permitido; se usa HS256.")
            self.ALGORITHM = "HS256"

        # 3) Duración de la sesión dentro de un rango razonable
        if not _MINUTOS_SESION_MIN <= self.ACCESS_TOKEN_EXPIRE_MINUTES <= _MINUTOS_SESION_MAX:
            _avisar(
                f"ACCESS_TOKEN_EXPIRE_MINUTES={self.ACCESS_TOKEN_EXPIRE_MINUTES} está fuera del rango "
                f"{_MINUTOS_SESION_MIN}-{_MINUTOS_SESION_MAX}; se usa {_MINUTOS_SESION_POR_DEFECTO} (7 días)."
            )
            self.ACCESS_TOKEN_EXPIRE_MINUTES = _MINUTOS_SESION_POR_DEFECTO

        # 4) CORS: se descartan comodines y valores que no son un origen exacto
        limpios: list[str] = []
        for origen in self.CORS_ORIGINS:
            valor = str(origen).strip().rstrip("/")
            if not _origen_cors_valido(valor):
                _avisar(f"Origen CORS descartado por inseguro o inválido: '{valor}'")
                continue
            if valor not in limpios:
                limpios.append(valor)
        self.CORS_ORIGINS = limpios

        # 5) Producción
        if self.es_produccion:
            if self.DEBUG:
                _avisar("DEBUG=true no se permite en producción; se desactiva.")
                self.DEBUG = False
            if not (self.SUPABASE_URL and self.SUPABASE_KEY):
                _avisar(
                    "Producción sin SUPABASE_URL/SUPABASE_KEY: los datos NO se guardarán. "
                    "Configúralas en Railway."
                )
        return self


settings = Settings()
