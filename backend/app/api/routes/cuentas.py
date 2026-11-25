"""
Cuentas de dinero `/api/v1/cuentas` (CHG-019 fase a, CT-012, UC-016, INV-046 a INV-051).

- El usuario sale SIEMPRE de la sesión; toda operación por id verifica al dueño (404 igual que si no existe, INV-046).
- El saldo lo calcula la BD en cada consulta (INV-047); el tipo no se puede cambiar; archivar se puede con o sin movimientos.
- Las reglas críticas (saldo, archivada, tope de 20) viven en la BD; aquí solo se traducen sus errores a 409 sin texto crudo.
- Altas limitadas a 30 por minuto por usuario (429).
"""
from fastapi import APIRouter, Header, HTTPException

from app.api.cuentas_errores import MSG_NO_ENCONTRADA, relanzar
from app.api.sesion import usuario_de_sesion
from app.core.rate_limit import SlidingWindow
from app.models import auth_estado
from app.models.cuentas import CuentaDB
from app.schemas.plataapp import CuentaCreate, CuentaResponse, CuentaUpdate, es_uuid

router = APIRouter()

LIMITE_ALTAS_POR_MINUTO = 30
_altas = SlidingWindow(LIMITE_ALTAS_POR_MINUTO, 60)   # por usuario

_MSG_429 = "Demasiadas cuentas creadas en poco tiempo. Espera un momento e intenta de nuevo."


async def _sesion(authorization: str) -> str:
    auth_estado.iniciar_presupuesto()   # presupuesto de 5 s por petición para las llamadas a la BD
    return await usuario_de_sesion(authorization)


def _no_encontrada() -> HTTPException:
    return HTTPException(status_code=404, detail=MSG_NO_ENCONTRADA)


@router.post("/cuentas", response_model=CuentaResponse)
async def crear_cuenta(cuenta: CuentaCreate, authorization: str = Header(...)):
    usuario_id = await _sesion(authorization)
    if not _altas.hit(usuario_id):
        raise HTTPException(status_code=429, detail=_MSG_429)
    try:
        return await CuentaDB.crear(usuario_id, cuenta.nombre, cuenta.tipo, cuenta.saldo_inicial)
    except Exception as e:
        relanzar(e)


@router.get("/cuentas", response_model=list[CuentaResponse])
async def listar_cuentas(incluir_archivadas: bool = False, authorization: str = Header(...)):
    usuario_id = await _sesion(authorization)
    return await CuentaDB.listar(usuario_id, incluir_archivadas)


@router.get("/cuentas/{cuenta_id}", response_model=CuentaResponse)
async def obtener_cuenta(cuenta_id: str, authorization: str = Header(...)):
    usuario_id = await _sesion(authorization)
    cuenta = await CuentaDB.obtener_con_saldo(cuenta_id, usuario_id) if es_uuid(cuenta_id) else None
    if cuenta is None or cuenta["usuario_id"] != str(usuario_id):
        raise _no_encontrada()
    return cuenta


@router.put("/cuentas/{cuenta_id}", response_model=CuentaResponse)
async def actualizar_cuenta(cuenta_id: str, datos: CuentaUpdate, authorization: str = Header(...)):
    usuario_id = await _sesion(authorization)
    actual = await CuentaDB.obtener_por_id(cuenta_id, usuario_id) if es_uuid(cuenta_id) else None
    if actual is None or str(actual.get("usuario_id")) != str(usuario_id):
        raise _no_encontrada()
    cambios = datos.model_dump(exclude_unset=True)
    cambios = {k: v for k, v in cambios.items() if v is not None}   # null no «quita» nada en una cuenta
    if "saldo_inicial" in cambios and cambios["saldo_inicial"] < 0 and actual.get("tipo") != "tarjeta_credito":
        raise HTTPException(status_code=422, detail="Solo la tarjeta de crédito puede tener saldo inicial negativo")
    if not cambios:
        cuenta = await CuentaDB.obtener_con_saldo(cuenta_id, usuario_id)
    else:
        try:
            cuenta = await CuentaDB.actualizar(cuenta_id, usuario_id, cambios)
        except Exception as e:
            relanzar(e)
    if cuenta is None:
        raise _no_encontrada()
    return cuenta


@router.delete("/cuentas/{cuenta_id}")
async def eliminar_cuenta(cuenta_id: str, authorization: str = Header(...)):
    usuario_id = await _sesion(authorization)
    actual = await CuentaDB.obtener_por_id(cuenta_id, usuario_id) if es_uuid(cuenta_id) else None
    if actual is None or str(actual.get("usuario_id")) != str(usuario_id):
        raise _no_encontrada()
    try:
        eliminada = await CuentaDB.eliminar(cuenta_id, usuario_id)
    except Exception as e:
        relanzar(e, al_eliminar_cuenta=True)
    if not eliminada:
        raise _no_encontrada()
    return {"message": "Cuenta eliminada"}
