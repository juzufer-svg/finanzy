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

# Medios de pago permitidos (INV-022). Se guardan como código; la interfaz muestra el nombre.
MEDIOS_PAGO = ("debito", "credito", "efectivo", "transferencia", "nequi_daviplata")
MedioPago = Literal["debito", "credito", "efectivo", "transferencia", "nequi_daviplata"]


# Transacciones
class TransaccionCreate(BaseModel):
    """Crear transacción"""
    categoria_id: str = Field("", max_length=64)
    monto: float = Field(..., gt=0, le=MONTO_MAX)
    descripcion: str = Field("", max_length=255)
    fecha: str = Field(..., pattern=FECHA_REGEX)
    tipo: Tipo
    # Opcional: null = sin especificar (transacciones antiguas y abonos a metas)
    medio_pago: Optional[MedioPago] = None


class TransaccionResponse(BaseModel):
    """Respuesta de transacción"""
    id: str
    usuario_id: str
    categoria_id: Optional[str] = None
    monto: float
    descripcion: Optional[str] = ""
    fecha: str
    tipo: str
    medio_pago: Optional[str] = None


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


# Presupuestos: copiar los de un mes a otro (CHG-012, A3)
class CopiarPresupuestos(BaseModel):
    """Copiar los presupuestos de un mes a otro"""
    desde: str = Field(..., pattern=MES_PATTERN.pattern)
    hacia: str = Field(..., pattern=MES_PATTERN.pattern)


class CopiaPresupuestosResponse(BaseModel):
    """Resultado de la copia"""
    copiados: int
    omitidos: int
    presupuestos: list[PresupuestoResponse]


# Transacciones recurrentes (CHG-012, INV-025 e INV-026)
Frecuencia = Literal["mensual", "quincenal", "semanal"]
FECHA_EXACTA = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"  # YYYY-MM-DD sin hora


class RecurrenteCreate(BaseModel):
    """Crear o editar una transacción recurrente (plantilla)"""
    categoria_id: str = Field("", max_length=64)
    tipo: Tipo
    monto: float = Field(..., gt=0, le=MONTO_MAX)
    descripcion: str = Field("", max_length=255)
    medio_pago: Optional[MedioPago] = None
    frecuencia: Frecuencia
    # Primera fecha (al crear) o próxima fecha (al editar); define el día ancla
    proxima_fecha: str = Field(..., pattern=FECHA_EXACTA)
    activa: bool = True


class RecurrenteUpdate(RecurrenteCreate):
    """Editar una recurrente. La próxima fecha solo cambia si se envía, y solo si la que vio la
    persona (`proxima_fecha_vista`) sigue siendo la actual (INV-026): una edición o pausa con datos
    viejos nunca hace retroceder la fecha de una ocurrencia ya registrada."""
    proxima_fecha: Optional[str] = Field(None, pattern=FECHA_EXACTA)
    proxima_fecha_vista: Optional[str] = Field(None, pattern=FECHA_EXACTA)


class RecurrenteResponse(BaseModel):
    """Respuesta de una transacción recurrente"""
    id: str
    usuario_id: str
    categoria_id: Optional[str] = None
    tipo: str
    monto: float
    descripcion: Optional[str] = ""
    medio_pago: Optional[str] = None
    frecuencia: str
    dia_ancla: int
    proxima_fecha: str
    activa: bool


class OcurrenciaRecurrente(BaseModel):
    """Omitir la ocurrencia pendiente de una recurrente"""
    # La fecha pendiente que vio la persona: si ya no coincide (doble toque, otra pestaña) → 409
    ocurrencia: str = Field(..., pattern=FECHA_EXACTA)


class ConfirmarRecurrente(OcurrenciaRecurrente):
    """Confirmar la ocurrencia pendiente: crea la transacción (monto y fecha ajustables)"""
    monto: Optional[float] = Field(None, gt=0, le=MONTO_MAX)
    fecha: Optional[str] = Field(None, pattern=FECHA_EXACTA)


class ConfirmacionResponse(BaseModel):
    """Transacción creada y recurrente con su nueva próxima fecha"""
    transaccion: TransaccionResponse
    recurrente: RecurrenteResponse
