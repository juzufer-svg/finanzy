"""
Pydantic schemas for Finanzy
"""
import re
from pydantic import BaseModel, Field
from typing import Optional, Literal

# Formatos aceptados
MES_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")          # YYYY-MM
FECHA_REGEX = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"  # YYYY-MM-DD (admite hora después)
MONTO_MAX = 1_000_000_000_000  # tope razonable para evitar valores absurdos

Tipo = Literal["ingreso", "gasto"]


# Transacciones
class TransaccionCreate(BaseModel):
    """Crear transacción"""
    categoria_id: str = Field("", max_length=64)
    monto: float = Field(..., gt=0, le=MONTO_MAX)
    descripcion: str = Field("", max_length=255)
    fecha: str = Field(..., pattern=FECHA_REGEX)
    tipo: Tipo


class TransaccionResponse(BaseModel):
    """Respuesta de transacción"""
    id: str
    usuario_id: str
    categoria_id: Optional[str] = None
    monto: float
    descripcion: Optional[str] = ""
    fecha: str
    tipo: str


class ResumenTransacciones(BaseModel):
    """Resumen de transacciones"""
    ingresos: float
    gastos: float
    balance: float
    total_transacciones: int


# Categorías
class CategoriaCreate(BaseModel):
    """Crear categoría"""
    nombre: str = Field(..., min_length=1, max_length=100)
    icono: str = Field("", max_length=16)
    tipo: Tipo


class CategoriaUpdate(BaseModel):
    """Actualizar categoría"""
    nombre: str = Field(..., min_length=1, max_length=100)
    icono: str = Field("", max_length=16)
    tipo: Tipo


class CategoriaResponse(BaseModel):
    """Respuesta de categoría"""
    id: str
    usuario_id: str
    nombre: str
    icono: str
    tipo: str


# Presupuestos
class PresupuestoCreate(BaseModel):
    """Crear presupuesto"""
    categoria_id: str = Field(..., min_length=1, max_length=64)
    limite_mensual: float = Field(..., gt=0, le=MONTO_MAX)
    mes_ano: str = Field(..., pattern=MES_PATTERN.pattern)


class PresupuestoResponse(BaseModel):
    """Respuesta de presupuesto"""
    id: str
    usuario_id: str
    categoria_id: str
    limite_mensual: float
    mes_ano: str


# Presupuestos (update)
class PresupuestoUpdate(BaseModel):
    """Actualizar presupuesto"""
    limite_mensual: float = Field(..., gt=0, le=MONTO_MAX)


# Metas
class MetaCreate(BaseModel):
    """Crear meta"""
    nombre: str = Field(..., min_length=1, max_length=100)
    monto_objetivo: float = Field(..., gt=0, le=MONTO_MAX)
    fecha_objetivo: str = Field(..., pattern=FECHA_REGEX)


class MetaResponse(BaseModel):
    """Respuesta de meta"""
    id: str
    usuario_id: str
    nombre: str
    monto_objetivo: float
    monto_actual: float
    fecha_objetivo: str
    porcentaje_completado: Optional[float] = None


class ActualizarMeta(BaseModel):
    """Actualizar meta (todos los campos opcionales)"""
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    monto_objetivo: Optional[float] = Field(None, gt=0, le=MONTO_MAX)
    monto_actual: Optional[float] = Field(None, ge=0, le=MONTO_MAX)
    fecha_objetivo: Optional[str] = Field(None, pattern=FECHA_REGEX)


class AbonarMeta(BaseModel):
    """Abonar un monto a una meta de ahorro"""
    monto: float = Field(..., gt=0, le=MONTO_MAX)
    descripcion: str = Field("Abono a meta de ahorro", max_length=255)
    fecha: str = Field(..., pattern=FECHA_REGEX)
