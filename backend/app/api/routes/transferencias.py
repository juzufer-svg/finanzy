"""
Transferencias entre cuentas de dinero `/api/v1/transferencias` (CHG-024, CT-012, UC-016, INV-046, INV-048 a INV-051).

- El usuario sale SIEMPRE de la sesión; las dos cuentas y la transferencia se verifican contra él (404 igual que si no existen,
  sin decir cuál de las dos cuentas falló).
- Las reglas críticas (saldo, archivada, atomicidad) viven en la BD; aquí solo se traducen sus errores (409/422) sin texto crudo
  y cualquier otro fallo de la BD es 503 genérico.
- Altas limitadas a 30 por minuto por usuario (429). No hay edición: se elimina y se crea otra.
- No tocan `transacciones`: no cuentan como ingreso ni gasto (INV-049).
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.api.cuentas_errores import MSG_NO_ENCONTRADA, relanzar_o_503
from app.api.sesion import usuario_de_sesion
from app.core.rate_limit import SlidingWindow
from app.models import auth_estado
from app.models.cuentas import CuentaDB
from app.models.transferencias import TransferenciaDB
from app.schemas.plataapp import MES_PATTERN, es_uuid
from app.schemas.transferencias import TransferenciaCreate, TransferenciaResponse

router = APIRouter()

LIMITE_ALTAS_POR_MINUTO = 30
_altas = SlidingWindow(LIMITE_ALTAS_POR_MINUTO, 60)   # por usuario

_MSG_429 = "Demasiadas transferencias en poco tiempo. Espera un momento e intenta de nuevo."
MSG_DISTINTAS = "Elige dos cuentas distintas"
MSG_TRANSFERENCIA_NO_ENCONTRADA = "Transferencia no encontrada"


async def _sesion(authorization: str) -> str:
    auth_estado.iniciar_presupuesto()   # presupuesto de 5 s por petición para las llamadas a la BD
    return await usuario_de_sesion(authorization)


async def _cuenta_propia(cuenta_id: str, usuario_id: str) -> bool:
    cuenta = await CuentaDB.obtener_por_id(cuenta_id, usuario_id) if es_uuid(cuenta_id) else None
    return cuenta is not None and str(cuenta.get("usuario_id")) == str(usuario_id)


@router.post("/transferencias", response_model=TransferenciaResponse)
async def crear_transferencia(datos: TransferenciaCreate, authorization: str = Header(...)):
    usuario_id = await _sesion(authorization)
    if not _altas.hit(usuario_id):
        raise HTTPException(status_code=429, detail=_MSG_429)
    if datos.cuenta_origen_id.lower() == datos.cuenta_destino_id.lower():
        raise HTTPException(status_code=422, detail=MSG_DISTINTAS)
    propia_origen = await _cuenta_propia(datos.cuenta_origen_id, usuario_id)
    propia_destino = await _cuenta_propia(datos.cuenta_destino_id, usuario_id)
    if not (propia_origen and propia_destino):   # un solo mensaje: no se dice cuál de las dos falló (INV-046)
        raise HTTPException(status_code=404, detail=MSG_NO_ENCONTRADA)
    try:
        return await TransferenciaDB.crear(usuario_id, datos.cuenta_origen_id, datos.cuenta_destino_id, datos.monto,
                                           datos.fecha, datos.descripcion)
    except Exception as e:
        relanzar_o_503(e, "transferencias")


@router.get("/transferencias", response_model=list[TransferenciaResponse])
async def listar_transferencias(mes: Optional[str] = None, authorization: str = Header(...)):
    usuario_id = await _sesion(authorization)
    if mes is not None and (not MES_PATTERN.match(mes) or not 1 <= int(mes[:4]) <= 9998):
        raise HTTPException(status_code=422, detail="Formato de mes inválido (YYYY-MM)")
    return await TransferenciaDB.listar(usuario_id, mes)


@router.delete("/transferencias/{transferencia_id}")
async def eliminar_transferencia(transferencia_id: str, authorization: str = Header(...)):
    usuario_id = await _sesion(authorization)
    actual = await TransferenciaDB.obtener_por_id(transferencia_id, usuario_id) if es_uuid(transferencia_id) else None
    if actual is None or str(actual.get("usuario_id")) != str(usuario_id):
        raise HTTPException(status_code=404, detail=MSG_TRANSFERENCIA_NO_ENCONTRADA)
    try:
        eliminada = await TransferenciaDB.eliminar(transferencia_id, usuario_id)
    except Exception as e:
        relanzar_o_503(e, "transferencias")
    if not eliminada:
        raise HTTPException(status_code=404, detail=MSG_TRANSFERENCIA_NO_ENCONTRADA)
    return {"message": "Transferencia eliminada"}
