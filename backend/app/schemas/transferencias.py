"""
Esquemas de las transferencias entre cuentas de dinero (CHG-024, CT-012 §Transferencias, INV-049, INV-051).
"""
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.plataapp import FECHA_EXACTA, decimales_validos
from app.utils.rango_fechas import validar_rango_fecha


class TransferenciaCreate(BaseModel):
    """Crear una transferencia. Campos desconocidos = 422. Los ids se verifican (dueño) en la ruta, no aquí."""
    model_config = ConfigDict(extra="forbid")
    cuenta_origen_id: str = Field(..., min_length=1, max_length=64)
    cuenta_destino_id: str = Field(..., min_length=1, max_length=64)
    monto: Decimal
    fecha: str = Field(..., pattern=FECHA_EXACTA)
    descripcion: Optional[str] = Field(None, max_length=255)

    @field_validator("monto")
    @classmethod
    def _monto(cls, v: Decimal) -> Decimal:
        # > 0, ≤ 9 999 999 999,99 y a lo sumo 2 decimales; NaN e infinito caen en `decimales_validos` (INV-051)
        if not decimales_validos(v) or v <= 0:
            raise ValueError("El monto debe ser mayor que 0, tener máximo 2 decimales y no superar 9.999.999.999,99")
        return v

    @field_validator("fecha")
    @classmethod
    def _fecha(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("La fecha no existe")
        return validar_rango_fecha(v)   # INV-063

    @field_validator("descripcion")
    @classmethod
    def _descripcion(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() or None if v is not None else None


class TransferenciaResponse(BaseModel):
    """Respuesta de transferencia (lista blanca de CT-012)."""
    id: str
    usuario_id: str
    cuenta_origen_id: str
    cuenta_destino_id: str
    monto: float
    fecha: str
    descripcion: Optional[str] = None
    created_at: Optional[str] = None
