"""
Pydantic schemas for Finanzy
"""
import re
import uuid
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, Literal

from app.utils.rango_fechas import validar_rango_fecha

# Formatos aceptados
MES_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")          # YYYY-MM
FECHA_REGEX = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"  # YYYY-MM-DD (admite hora después)
MONTO_MAX = 1_000_000_000_000  # tope razonable para evitar valores absurdos

Tipo = Literal["ingreso", "gasto"]

# Medios de pago permitidos (INV-022). Se guardan como código; la interfaz muestra el nombre.
MEDIOS_PAGO = ("debito", "credito", "efectivo", "transferencia", "nequi_daviplata")
MedioPago = Literal["debito", "credito", "efectivo", "transferencia", "nequi_daviplata"]


# Cuentas de dinero (CHG-019, INV-051): tope real de NUMERIC(12,2) y 2 decimales; los montos se leen con Decimal
SALDO_MAX = Decimal("9999999999.99")
TipoCuenta = Literal["efectivo", "ahorros_corriente", "billetera_digital", "tarjeta_credito"]
MSG_MONTO_CON_CUENTA = "El monto de esta transacción no cumple el máximo permitido con cuenta de dinero"


def decimales_validos(valor: Decimal) -> bool:
    """¿Es finito, con a lo sumo 2 decimales y con valor absoluto ≤ 9 999 999 999,99 (INV-051)?"""
    return valor.is_finite() and valor.as_tuple().exponent >= -2 and abs(valor) <= SALDO_MAX


def a_decimal(valor) -> Optional[Decimal]:
    """Lee un monto sin pasar por float (`str` del número tal como lo guardó el JSON o la BD). None si no es un número."""
    try:
        return valor if isinstance(valor, Decimal) else Decimal(str(valor))
    except Exception:
        return None


def monto_valido_con_cuenta(valor) -> bool:
    """Una transacción CON cuenta de dinero: > 0, ≤ 9 999 999 999,99 y 2 decimales como máximo (INV-051)."""
    d = a_decimal(valor)
    return d is not None and d > 0 and decimales_validos(d)


def _uuid_o_none(valor: Optional[str]) -> Optional[str]:
    """El id en su forma canónica, o None si no es un UUID."""
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, AttributeError, TypeError):
        return None


def es_uuid(valor) -> bool:
    return _uuid_o_none(valor) is not None


def _cuenta_uuid_o_error(v: Optional[str]) -> Optional[str]:
    """Validador común de `cuenta_id` opcional (CHG-019/CHG-025): None se conserva; si viene, debe ser un UUID."""
    if v is None:
        return v
    canonico = _uuid_o_none(v)
    if canonico is None:
        raise ValueError("cuenta_id debe ser un UUID")
    return canonico


class CuentaCreate(BaseModel):
    """Crear cuenta de dinero"""
    nombre: str = Field(..., min_length=1, max_length=100)
    tipo: TipoCuenta
    saldo_inicial: Decimal = Field(Decimal("0"))

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v

    @field_validator("saldo_inicial")
    @classmethod
    def _saldo(cls, v: Decimal) -> Decimal:
        if not decimales_validos(v):
            raise ValueError("El saldo inicial debe tener máximo 2 decimales y no superar 9.999.999.999,99")
        return v

    @model_validator(mode="after")
    def _solo_tarjeta_negativa(self):
        if self.saldo_inicial < 0 and self.tipo != "tarjeta_credito":
            raise ValueError("Solo la tarjeta de crédito puede empezar con saldo negativo")
        return self


class CuentaUpdate(BaseModel):
    """Editar cuenta de dinero: el tipo NO se puede cambiar (si llega, 422)."""
    model_config = ConfigDict(extra="forbid")
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    saldo_inicial: Optional[Decimal] = None
    archivada: Optional[bool] = None

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = " ".join(v.split())
        if not v:
            raise ValueError("El nombre no puede estar vacío")
        return v

    @field_validator("saldo_inicial")
    @classmethod
    def _saldo(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and not decimales_validos(v):
            raise ValueError("El saldo inicial debe tener máximo 2 decimales y no superar 9.999.999.999,99")
        return v


class CuentaResponse(BaseModel):
    """Respuesta de cuenta de dinero (lista blanca: nunca datos de la cuenta de usuario)"""
    id: str
    usuario_id: str
    nombre: str
    tipo: str
    saldo_inicial: float
    saldo: float
    archivada: bool
    created_at: Optional[str] = None


# Transacciones
class TransaccionBase(BaseModel):
    """Campos de una transacción (sin la regla de rango de fechas: la aplican Create y, en la ruta, Update)"""
    categoria_id: str = Field("", max_length=64)
    # Decimal: la regla de 2 decimales de INV-051 (solo con cuenta de dinero) no puede depender de float
    monto: Decimal = Field(..., gt=0, le=MONTO_MAX)
    descripcion: str = Field("", max_length=255)
    fecha: str = Field(..., pattern=FECHA_REGEX)
    tipo: Tipo
    # Opcional: null = sin especificar (transacciones antiguas y abonos a metas)
    medio_pago: Optional[MedioPago] = None
    # Opcional (CHG-019, CT-003 v1.2): null/ausente = sin cuenta de dinero; si viene, debe ser un UUID
    cuenta_id: Optional[str] = Field(None, max_length=64)

    @field_validator("cuenta_id")
    @classmethod
    def _cuenta_uuid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        canonico = _uuid_o_none(v)
        if canonico is None:
            raise ValueError("cuenta_id debe ser un UUID")
        return canonico


class TransaccionCreate(TransaccionBase):
    """Crear transacción: la fecha debe estar en el rango permitido (INV-063)"""

    @field_validator("fecha")
    @classmethod
    def _fecha_en_rango(cls, v: str) -> str:
        return validar_rango_fecha(v)


class TransaccionUpdate(TransaccionBase):
    """Editar transacción: el rango de la fecha (INV-063) lo comprueba la ruta SOLO si la fecha cambia respecto a la guardada"""


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
    cuenta_id: Optional[str] = None


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
    # Opcional (CHG-025, CT-006 v1.1): cuenta de dinero de origen; null/ausente = sin cuenta (como antes)
    cuenta_id: Optional[str] = Field(None, max_length=64)

    @field_validator("cuenta_id")
    @classmethod
    def _cuenta_uuid(cls, v: Optional[str]) -> Optional[str]:
        return _cuenta_uuid_o_error(v)


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
    # Opcional (CHG-025, CT-008 v1.1): cuenta de dinero del usuario. Al editar: no enviar = conservar, null = quitar
    cuenta_id: Optional[str] = Field(None, max_length=64)
    frecuencia: Frecuencia
    # Primera fecha (al crear) o próxima fecha (al editar); define el día ancla
    proxima_fecha: str = Field(..., pattern=FECHA_EXACTA)
    activa: bool = True

    @field_validator("cuenta_id")
    @classmethod
    def _cuenta_uuid(cls, v: Optional[str]) -> Optional[str]:
        return _cuenta_uuid_o_error(v)


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
    cuenta_id: Optional[str] = None
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
    # Opcional (CHG-025, CT-008 v1.1): reemplaza la cuenta de la plantilla. No enviar = usar la de la plantilla; null = sin cuenta
    cuenta_id: Optional[str] = Field(None, max_length=64)

    @field_validator("cuenta_id")
    @classmethod
    def _cuenta_uuid(cls, v: Optional[str]) -> Optional[str]:
        return _cuenta_uuid_o_error(v)


class ConfirmacionResponse(BaseModel):
    """Transacción creada y recurrente con su nueva próxima fecha"""
    transaccion: TransaccionResponse
    recurrente: RecurrenteResponse
