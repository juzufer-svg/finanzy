"""
Finanzy routes - Transacciones, Categorías, Presupuestos, Metas

Toda operación sobre un registro por ID verifica primero que el registro
pertenezca al usuario del token; si no, responde 404 (no se revela si existe).
"""
from fastapi import APIRouter, HTTPException, Header, Path
from app.schemas.plataapp import (
    TransaccionCreate, TransaccionResponse, ResumenTransacciones,
    CategoriaCreate, CategoriaUpdate, CategoriaResponse,
    PresupuestoCreate, PresupuestoResponse, PresupuestoUpdate,
    MetaCreate, MetaResponse, ActualizarMeta, AbonarMeta,
    CopiarPresupuestos, CopiaPresupuestosResponse,
    RecurrenteCreate, RecurrenteUpdate, RecurrenteResponse, OcurrenciaRecurrente, ConfirmarRecurrente, ConfirmacionResponse,
    MES_PATTERN, MSG_MONTO_CON_CUENTA, monto_valido_con_cuenta,
)
from app.models.plataapp import (
    TransaccionDB, CategoriaDB, PresupuestoDB, MetaDB, RecurrenteDB, AbonoAtomicoNoDisponible,
)
from app.models.cuentas import CuentaDB
from app.api.cuentas_errores import (
    relanzar_o_503 as relanzar_error_cuenta, traducir as traducir_error_cuenta, codigo_de, MSG_NO_ENCONTRADA, MSG_ARCHIVADA,
)
from app.models.auth_estado import EstadoNoDisponible
from app.utils.recurrencia import siguiente_fecha
from datetime import date, datetime, timezone
from app.api.sesion import usuario_de_sesion
from typing import Optional

router = APIRouter()


async def get_user_id(authorization: str) -> str:
    """Extrae el usuario_id del token Bearer y verifica que la sesión siga vigente."""
    return await usuario_de_sesion(authorization)


def _ensure_owner(registro: Optional[dict], usuario_id: str, detalle: str) -> dict:
    """404 si el registro no existe o es de otro usuario."""
    if not registro or str(registro.get("usuario_id")) != str(usuario_id):
        raise HTTPException(status_code=404, detail=detalle)
    return registro


async def _ensure_categoria_propia(categoria_id: Optional[str], usuario_id: str) -> None:
    """Valida que la categoría (si se envía) pertenezca al usuario."""
    if not categoria_id:
        return
    categoria = await CategoriaDB.obtener_por_id(categoria_id, usuario_id)
    _ensure_owner(categoria, usuario_id, "Categoría no encontrada")


async def _ensure_cuenta_propia(cuenta_id: Optional[str], usuario_id: str) -> None:
    """404 «Cuenta no encontrada» si la cuenta de dinero (si se envía) no existe o es de otro usuario (INV-046)."""
    if not cuenta_id:
        return
    _ensure_owner(await CuentaDB.obtener_por_id(cuenta_id, usuario_id), usuario_id, MSG_NO_ENCONTRADA)


def _ensure_monto_con_cuenta(monto) -> None:
    """422 si el monto de una transacción CON cuenta de dinero pasa del tope o tiene más de 2 decimales (INV-051)."""
    if not monto_valido_con_cuenta(monto):
        raise HTTPException(status_code=422, detail=MSG_MONTO_CON_CUENTA)


def _es_duplicado(error: Exception) -> bool:
    """¿La base de datos rechazó la escritura por una restricción UNIQUE (INV-028)?

    Supabase (postgrest) entrega el código de PostgreSQL en `error.code`: solo 23505 cuenta. El texto
    se mira únicamente en el modo demo, que lanza ValueError con "(23505)".
    """
    codigo = getattr(error, "code", None)
    if codigo is not None:
        return str(codigo) == "23505"
    return isinstance(error, ValueError) and "(23505)" in str(error)


_CATEGORIA_REPETIDA = "Ya tienes una categoría con ese nombre y tipo."
_PRESUPUESTO_REPETIDO = "Ya hay un presupuesto para esa categoría en este mes. Edítalo en lugar de crear otro."


def _clave_categoria(nombre: str) -> str:
    return " ".join(str(nombre).split()).casefold()


async def _ensure_categoria_no_repetida(usuario_id: str, nombre: str, tipo: str, excepto: Optional[str] = None) -> None:
    """409 si la persona ya tiene una categoría con ese nombre (sin distinguir mayúsculas ni espacios) y tipo."""
    clave = _clave_categoria(nombre)
    for c in await CategoriaDB.obtener_por_usuario(usuario_id):
        if c["id"] != excepto and c.get("tipo") == tipo and " ".join(str(c.get("nombre", "")).split()).casefold() == clave:
            raise HTTPException(status_code=409, detail=_CATEGORIA_REPETIDA)


def _porcentaje(meta: dict) -> float:
    objetivo = float(meta["monto_objetivo"])
    return float(meta["monto_actual"]) / objetivo * 100 if objetivo > 0 else 0


# ==================== TRANSACCIONES ====================

@router.post("/transacciones", response_model=TransaccionResponse)
async def crear_transaccion(transaccion: TransaccionCreate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    await _ensure_categoria_propia(transaccion.categoria_id, usuario_id)
    if transaccion.cuenta_id:
        _ensure_monto_con_cuenta(transaccion.monto)           # INV-051
        await _ensure_cuenta_propia(transaccion.cuenta_id, usuario_id)   # INV-046
    try:
        return await TransaccionDB.crear(
            usuario_id=usuario_id,
            categoria_id=transaccion.categoria_id,
            monto=float(transaccion.monto),
            descripcion=transaccion.descripcion,
            fecha=transaccion.fecha,
            tipo=transaccion.tipo,
            medio_pago=transaccion.medio_pago,
            cuenta_id=transaccion.cuenta_id,
        )
    except Exception as e:
        relanzar_error_cuenta(e)   # FZ001/FZ002 → 409, 23503 → 404; cualquier otro error sigue su camino


@router.get("/transacciones", response_model=list[TransaccionResponse])
async def obtener_transacciones(authorization: str = Header(...), mes: Optional[str] = None):
    usuario_id = await get_user_id(authorization)
    if mes is not None and not MES_PATTERN.match(mes):
        raise HTTPException(status_code=422, detail="Formato de mes inválido (YYYY-MM)")
    return await TransaccionDB.obtener_por_usuario(usuario_id, mes)


@router.get("/transacciones/resumen/{mes}", response_model=ResumenTransacciones)
async def obtener_resumen(mes: str = Path(..., pattern=MES_PATTERN.pattern), authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    return await TransaccionDB.obtener_resumen(usuario_id, mes)


@router.get("/transacciones/{transaccion_id}", response_model=TransaccionResponse)
async def obtener_transaccion(transaccion_id: str, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    transaccion = await TransaccionDB.obtener_por_id(transaccion_id, usuario_id)
    return _ensure_owner(transaccion, usuario_id, "Transacción no encontrada")


@router.put("/transacciones/{transaccion_id}", response_model=TransaccionResponse)
async def actualizar_transaccion(transaccion_id: str, transaccion: TransaccionCreate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    actual = _ensure_owner(await TransaccionDB.obtener_por_id(transaccion_id, usuario_id), usuario_id, "Transacción no encontrada")
    await _ensure_categoria_propia(transaccion.categoria_id, usuario_id)
    datos = transaccion.model_dump()
    datos["monto"] = float(transaccion.monto)
    # Si el cliente no envía medio_pago, se conserva el que tenía (null explícito = quitarlo)
    if "medio_pago" not in transaccion.model_fields_set:
        datos.pop("medio_pago")
    # cuenta_id igual que medio_pago: no enviar = conservar, null = quitar, valor = reemplazar (CT-003 v1.2)
    if "cuenta_id" in transaccion.model_fields_set:
        cuenta_efectiva = transaccion.cuenta_id
    else:
        datos.pop("cuenta_id")
        cuenta_efectiva = actual.get("cuenta_id")
    if cuenta_efectiva:
        # INV-051: con cuenta de dinero el monto debe cumplir el tope y los 2 decimales. Un PUT que solo cambia
        # `cuenta_id` reenvía el monto ya guardado: se valida (leído con Decimal) ANTES de escribir.
        _ensure_monto_con_cuenta(transaccion.monto)
        if transaccion.cuenta_id:
            await _ensure_cuenta_propia(transaccion.cuenta_id, usuario_id)   # INV-046
    try:
        actualizada = await TransaccionDB.actualizar(transaccion_id, usuario_id, **datos)
    except Exception as e:
        relanzar_error_cuenta(e)
    if not actualizada:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    return actualizada


@router.delete("/transacciones/{transaccion_id}")
async def eliminar_transaccion(transaccion_id: str, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    _ensure_owner(await TransaccionDB.obtener_por_id(transaccion_id, usuario_id), usuario_id, "Transacción no encontrada")
    try:
        await TransaccionDB.eliminar(transaccion_id, usuario_id)
    except Exception as e:
        relanzar_error_cuenta(e)   # FZ001 (quitar un ingreso ya gastado) / FZ002 (cuenta archivada) → 409
    return {"message": "Transacción eliminada"}


# ==================== CATEGORÍAS ====================

@router.post("/categorias", response_model=CategoriaResponse)
async def crear_categoria(categoria: CategoriaCreate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    nombre = " ".join(categoria.nombre.split())
    if not nombre:
        raise HTTPException(status_code=422, detail="El nombre no puede estar vacío")
    await _ensure_categoria_no_repetida(usuario_id, nombre, categoria.tipo)  # INV-028
    try:
        return await CategoriaDB.crear(usuario_id=usuario_id, nombre=nombre, icono=categoria.icono, tipo=categoria.tipo)
    except Exception as e:
        if _es_duplicado(e):  # otra petición la creó al mismo tiempo
            raise HTTPException(status_code=409, detail=_CATEGORIA_REPETIDA)
        raise


@router.get("/categorias", response_model=list[CategoriaResponse])
async def obtener_categorias(authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    return await CategoriaDB.obtener_por_usuario(usuario_id)


@router.put("/categorias/{categoria_id}", response_model=CategoriaResponse)
async def actualizar_categoria(categoria_id: str, datos: CategoriaUpdate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    actual = _ensure_owner(await CategoriaDB.obtener_por_id(categoria_id, usuario_id), usuario_id, "Categoría no encontrada")
    nombre = " ".join(datos.nombre.split())
    if not nombre:
        raise HTTPException(status_code=422, detail="El nombre no puede estar vacío")
    # Solo se comprueba si cambia el nombre o el tipo: así se pueden editar (p. ej. el ícono) categorías
    # heredadas como «Comida» y «comida», que la base acepta por ser distintas al pie de la letra.
    if _clave_categoria(nombre) != _clave_categoria(actual.get("nombre", "")) or datos.tipo != actual.get("tipo"):
        await _ensure_categoria_no_repetida(usuario_id, nombre, datos.tipo, excepto=categoria_id)  # INV-028
    try:
        actualizada = await CategoriaDB.actualizar(categoria_id, usuario_id, nombre, datos.icono, datos.tipo)
    except Exception as e:
        if _es_duplicado(e):
            raise HTTPException(status_code=409, detail=_CATEGORIA_REPETIDA)
        raise
    if not actualizada:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return actualizada


@router.delete("/categorias/{categoria_id}")
async def eliminar_categoria(categoria_id: str, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    _ensure_owner(await CategoriaDB.obtener_por_id(categoria_id, usuario_id), usuario_id, "Categoría no encontrada")
    try:
        await CategoriaDB.eliminar(categoria_id, usuario_id)
    except Exception:
        raise HTTPException(
            status_code=409,
            detail="No se pudo eliminar. Puede tener transacciones asociadas.",
        )
    return {"message": "Categoría eliminada"}


# ==================== PRESUPUESTOS ====================

@router.post("/presupuestos", response_model=PresupuestoResponse)
async def crear_presupuesto(presupuesto: PresupuestoCreate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    await _ensure_categoria_propia(presupuesto.categoria_id, usuario_id)
    del_mes = await PresupuestoDB.obtener_por_usuario_mes(usuario_id, presupuesto.mes_ano)
    if any(str(p["categoria_id"]) == presupuesto.categoria_id for p in del_mes):  # INV-028
        raise HTTPException(status_code=409, detail=_PRESUPUESTO_REPETIDO)
    try:
        return await PresupuestoDB.crear(
            usuario_id=usuario_id,
            categoria_id=presupuesto.categoria_id,
            limite_mensual=presupuesto.limite_mensual,
            mes_ano=presupuesto.mes_ano
        )
    except Exception as e:
        if _es_duplicado(e):  # otra petición lo creó al mismo tiempo
            raise HTTPException(status_code=409, detail=_PRESUPUESTO_REPETIDO)
        raise


@router.post("/presupuestos/copiar", response_model=CopiaPresupuestosResponse)
async def copiar_presupuestos(datos: CopiarPresupuestos, authorization: str = Header(...)):
    """Copia los presupuestos de un mes a otro (CHG-012). No toca los que ya existen en el destino."""
    usuario_id = await get_user_id(authorization)
    if datos.desde == datos.hacia:
        raise HTTPException(status_code=422, detail="El mes de origen y el de destino deben ser distintos")
    origen = await PresupuestoDB.obtener_por_usuario_mes(usuario_id, datos.desde)
    destino = await PresupuestoDB.obtener_por_usuario_mes(usuario_id, datos.hacia)
    con_presupuesto = {str(p["categoria_id"]) for p in destino}
    copiados = 0
    for presupuesto in origen:
        categoria_id = str(presupuesto["categoria_id"])
        if categoria_id in con_presupuesto:
            continue  # ya tiene límite en el mes destino: se respeta el que eligió la persona
        await _ensure_categoria_propia(categoria_id, usuario_id)  # INV-002
        try:
            await PresupuestoDB.crear(
                usuario_id=usuario_id,
                categoria_id=categoria_id,
                limite_mensual=float(presupuesto["limite_mensual"]),
                mes_ano=datos.hacia,
            )
        except Exception as e:
            if not _es_duplicado(e):
                raise
            # Otra copia simultánea ya lo creó: la restricción UNIQUE evita el duplicado (INV-028)
            con_presupuesto.add(categoria_id)
            continue
        con_presupuesto.add(categoria_id)
        copiados += 1
    return {
        "copiados": copiados,
        "omitidos": len(origen) - copiados,
        "presupuestos": await PresupuestoDB.obtener_por_usuario_mes(usuario_id, datos.hacia),
    }


@router.get("/presupuestos/{mes_ano}", response_model=list[PresupuestoResponse])
async def obtener_presupuestos(mes_ano: str = Path(..., pattern=MES_PATTERN.pattern), authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    return await PresupuestoDB.obtener_por_usuario_mes(usuario_id, mes_ano)


@router.put("/presupuestos/{presupuesto_id}", response_model=PresupuestoResponse)
async def actualizar_presupuesto(presupuesto_id: str, datos: PresupuestoUpdate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    _ensure_owner(await PresupuestoDB.obtener_por_id(presupuesto_id, usuario_id), usuario_id, "Presupuesto no encontrado")
    actualizado = await PresupuestoDB.actualizar(presupuesto_id, usuario_id, datos.limite_mensual)
    if not actualizado:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    return actualizado


@router.delete("/presupuestos/{presupuesto_id}")
async def eliminar_presupuesto(presupuesto_id: str, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    _ensure_owner(await PresupuestoDB.obtener_por_id(presupuesto_id, usuario_id), usuario_id, "Presupuesto no encontrado")
    await PresupuestoDB.eliminar(presupuesto_id, usuario_id)
    return {"message": "Presupuesto eliminado"}


# ==================== METAS ====================

@router.post("/metas", response_model=MetaResponse)
async def crear_meta(meta: MetaCreate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    nueva = await MetaDB.crear(
        usuario_id=usuario_id,
        nombre=meta.nombre,
        monto_objetivo=meta.monto_objetivo,
        fecha_objetivo=meta.fecha_objetivo
    )
    return {**nueva, "porcentaje_completado": 0}


@router.get("/metas", response_model=list[MetaResponse])
async def obtener_metas(authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    metas = await MetaDB.obtener_por_usuario(usuario_id)
    for meta in metas:
        meta["porcentaje_completado"] = _porcentaje(meta)
    return metas


@router.put("/metas/{meta_id}", response_model=MetaResponse)
async def actualizar_meta(meta_id: str, actualizacion: ActualizarMeta, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    _ensure_owner(await MetaDB.obtener_por_id(meta_id, usuario_id), usuario_id, "Meta no encontrada")
    updates = {k: v for k, v in actualizacion.model_dump().items() if v is not None}
    meta = await MetaDB.actualizar_progreso(meta_id, usuario_id, updates)
    if not meta:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    return {**meta, "porcentaje_completado": _porcentaje(meta)}


@router.delete("/metas/{meta_id}")
async def eliminar_meta(meta_id: str, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    _ensure_owner(await MetaDB.obtener_por_id(meta_id, usuario_id), usuario_id, "Meta no encontrada")
    await MetaDB.eliminar(meta_id, usuario_id)
    return {"message": "Meta eliminada"}


@router.post("/metas/{meta_id}/abonar", response_model=MetaResponse)
async def abonar_meta(meta_id: str, datos: AbonarMeta, authorization: str = Header(...)):
    """Registra un aporte a una meta: crea transacción de gasto y aumenta monto_actual.

    Con `cuenta_id` (CHG-025, INV-052) el gasto descuenta esa cuenta de dinero en la MISMA transacción SQL que suma a la meta:
    404 si la cuenta no es suya, 409 por saldo o cuenta archivada (no cambia nada), 503 sin la función SQL actualizada
    (nunca el método anterior, que no es atómico)."""
    usuario_id = await get_user_id(authorization)
    if datos.cuenta_id:
        _ensure_monto_con_cuenta(datos.monto)                            # INV-051
        await _ensure_cuenta_propia(datos.cuenta_id, usuario_id)         # INV-046

    # 1) Camino atómico: una sola transacción en PostgreSQL (CHG-004)
    try:
        if datos.cuenta_id:
            meta_actualizada = await MetaDB.abonar(meta_id, usuario_id, datos.monto, datos.fecha, datos.descripcion,
                                                   cuenta_id=datos.cuenta_id)
        else:
            meta_actualizada = await MetaDB.abonar(meta_id, usuario_id, datos.monto, datos.fecha, datos.descripcion)
    except AbonoAtomicoNoDisponible:
        return await _abonar_sin_transaccion(meta_id, usuario_id, datos)   # solo sin cuenta: con cuenta nunca se lanza
    except (HTTPException, EstadoNoDisponible):
        raise
    except Exception as e:
        if datos.cuenta_id:
            relanzar_error_cuenta(e, "metas")   # FZ001/FZ002 → 409, 23503 → 404, lo demás → 503 genérico
        # La función revierte todo si falla: no quedó nada a medias
        raise HTTPException(status_code=500, detail="No se pudo registrar el abono")
    meta_actualizada = _ensure_owner(meta_actualizada, usuario_id, "Meta no encontrada")
    return {**meta_actualizada, "porcentaje_completado": _porcentaje(meta_actualizada)}


async def _abonar_sin_transaccion(meta_id: str, usuario_id: str, datos: AbonarMeta) -> dict:
    """Método anterior (modo demo o si la función SQL aún no está instalada)."""
    # Validar la meta ANTES de registrar el gasto (evita transacciones huérfanas)
    meta = _ensure_owner(await MetaDB.obtener_por_id(meta_id, usuario_id), usuario_id, "Meta no encontrada")

    # Buscar o crear la categoría especial "Ahorro"
    categorias = await CategoriaDB.obtener_por_usuario(usuario_id)
    cat_ahorro = next((c for c in categorias if c["nombre"] == "Ahorro"), None)
    if not cat_ahorro:
        cat_ahorro = await CategoriaDB.crear(usuario_id, "Ahorro", "🐷", "gasto")

    # Registrar la transacción como gasto
    transaccion = await TransaccionDB.crear(
        usuario_id=usuario_id,
        categoria_id=cat_ahorro["id"],
        monto=datos.monto,
        descripcion=datos.descripcion,
        fecha=datos.fecha,
        tipo="gasto"
    )

    # Incrementar el monto_actual de la meta; si falla, revertir la transacción
    nuevo_monto = float(meta["monto_actual"]) + datos.monto
    try:
        meta_actualizada = await MetaDB.actualizar_progreso(meta_id, usuario_id, {"monto_actual": nuevo_monto})
        if not meta_actualizada:
            raise RuntimeError("No se pudo actualizar la meta")
    except Exception:
        await TransaccionDB.eliminar(transaccion["id"], usuario_id)
        raise HTTPException(status_code=500, detail="No se pudo registrar el abono")

    return {**meta_actualizada, "porcentaje_completado": _porcentaje(meta_actualizada)}


# ==================== RECURRENTES (CHG-012) ====================
# Plantillas de movimientos fijos. Nunca se registran solas: cuando llega su próxima
# fecha aparecen como pendientes y la persona las confirma u omite (INV-025).

def _fecha(valor: str) -> date:
    """Convierte YYYY-MM-DD en fecha; 422 si no existe (p. ej. 2026-02-31)."""
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise HTTPException(status_code=422, detail="Fecha inválida (YYYY-MM-DD)")


async def _ensure_cuenta_de_recurrente(cuenta_id: Optional[str], usuario_id: str) -> None:
    """Al crear o editar una recurrente con cuenta de dinero: 404 si no es del usuario (INV-046) y 409 si está archivada."""
    if not cuenta_id:
        return
    cuenta = _ensure_owner(await CuentaDB.obtener_por_id(cuenta_id, usuario_id), usuario_id, MSG_NO_ENCONTRADA)
    if cuenta.get("archivada"):
        raise HTTPException(status_code=409, detail=MSG_ARCHIVADA)


_OCURRENCIA_CAMBIADA = "Esta fecha ya se registró u omitió. Actualiza la lista de pendientes."
_FECHA_CAMBIADA = "La próxima fecha cambió mientras editabas (se registró u omitió una). Recarga e intenta de nuevo."


@router.get("/recurrentes", response_model=list[RecurrenteResponse])
async def obtener_recurrentes(authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    return await RecurrenteDB.obtener_por_usuario(usuario_id)


@router.get("/recurrentes/pendientes", response_model=list[RecurrenteResponse])
async def obtener_pendientes(authorization: str = Header(...), hasta: Optional[str] = None):
    """Recurrentes activas cuya próxima fecha ya llegó (hasta = hoy del navegador; por defecto, hoy UTC)."""
    usuario_id = await get_user_id(authorization)
    limite = _fecha(hasta) if hasta is not None else datetime.now(timezone.utc).date()
    recurrentes = await RecurrenteDB.obtener_por_usuario(usuario_id)
    pendientes = [r for r in recurrentes if r.get("activa") and _fecha(r["proxima_fecha"]) <= limite]
    return sorted(pendientes, key=lambda r: r["proxima_fecha"])


@router.post("/recurrentes", response_model=RecurrenteResponse)
async def crear_recurrente(datos: RecurrenteCreate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    await _ensure_categoria_propia(datos.categoria_id, usuario_id)  # INV-002
    await _ensure_cuenta_de_recurrente(datos.cuenta_id, usuario_id)  # INV-046 (404 si es ajena, 409 si está archivada)
    primera = _fecha(datos.proxima_fecha)
    fila = {**datos.model_dump(), "dia_ancla": primera.day}
    if fila.get("cuenta_id") is None:
        fila.pop("cuenta_id", None)   # sin cuenta no se envía la columna (funciona aunque falte la migración)
    return await RecurrenteDB.crear(usuario_id, fila)


@router.put("/recurrentes/{recurrente_id}", response_model=RecurrenteResponse)
async def actualizar_recurrente(recurrente_id: str, datos: RecurrenteUpdate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    actual = _ensure_owner(await RecurrenteDB.obtener_por_id(recurrente_id, usuario_id), usuario_id,
                           "Recurrente no encontrada")
    await _ensure_categoria_propia(datos.categoria_id, usuario_id)
    cambios = datos.model_dump(exclude={"proxima_fecha", "proxima_fecha_vista"})
    # cuenta_id igual que en las transacciones (CT-003 v1.2): no enviar = conservar, null = quitar, valor = reemplazar
    if "cuenta_id" not in datos.model_fields_set:
        cambios.pop("cuenta_id")
    elif datos.cuenta_id != actual.get("cuenta_id"):   # re-enviar la misma cuenta (aunque esté archivada) no bloquea editar
        await _ensure_cuenta_de_recurrente(datos.cuenta_id, usuario_id)
    esperada = None
    if datos.proxima_fecha is not None and datos.proxima_fecha != actual["proxima_fecha"]:
        nueva = _fecha(datos.proxima_fecha)
        # Cambiar la fecha exige que la persona haya visto la actual (INV-026): si entretanto se
        # confirmó u omitió una ocurrencia (otra pestaña, el panel de pendientes), 409 y nada cambia.
        if datos.proxima_fecha_vista != actual["proxima_fecha"]:
            raise HTTPException(status_code=409, detail=_FECHA_CAMBIADA)
        cambios["proxima_fecha"] = nueva.isoformat()
        esperada = actual["proxima_fecha"]  # fecha, ancla y demás campos en una sola escritura condicional
        # El día ancla solo cambia si la persona eligió otra próxima fecha: editar el monto de una
        # recurrente del 31 que hoy cae el 28 de febrero no debe volverla "del 28" para siempre.
        cambios["dia_ancla"] = nueva.day
    actualizada = await RecurrenteDB.actualizar(recurrente_id, usuario_id, cambios, esperada=esperada)
    if not actualizada:
        if esperada is not None:  # otra petición movió la fecha entre la lectura y la escritura
            raise HTTPException(status_code=409, detail=_FECHA_CAMBIADA)
        raise HTTPException(status_code=404, detail="Recurrente no encontrada")
    return actualizada


@router.delete("/recurrentes/{recurrente_id}")
async def eliminar_recurrente(recurrente_id: str, authorization: str = Header(...)):
    """Borra la plantilla; las transacciones ya registradas con ella se conservan."""
    usuario_id = await get_user_id(authorization)
    _ensure_owner(await RecurrenteDB.obtener_por_id(recurrente_id, usuario_id), usuario_id, "Recurrente no encontrada")
    await RecurrenteDB.eliminar(recurrente_id, usuario_id)
    return {"message": "Recurrente eliminada"}


async def _avanzar(recurrente: dict, usuario_id: str, ocurrencia: str) -> tuple[dict, str]:
    """Mueve la próxima fecha a la siguiente de la serie, solo si la ocurrencia sigue pendiente (INV-026)."""
    if not recurrente.get("activa"):
        raise HTTPException(status_code=409, detail="La recurrente está pausada")
    if ocurrencia != recurrente["proxima_fecha"]:
        raise HTTPException(status_code=409, detail=_OCURRENCIA_CAMBIADA)
    siguiente = siguiente_fecha(_fecha(ocurrencia), recurrente["frecuencia"], int(recurrente["dia_ancla"]))
    avanzada = await RecurrenteDB.avanzar(recurrente["id"], usuario_id, ocurrencia, siguiente.isoformat())
    if not avanzada:  # otra petición (doble toque, otra pestaña) ya la movió
        raise HTTPException(status_code=409, detail=_OCURRENCIA_CAMBIADA)
    return avanzada, siguiente.isoformat()


@router.post("/recurrentes/{recurrente_id}/confirmar", response_model=ConfirmacionResponse)
async def confirmar_recurrente(recurrente_id: str, datos: ConfirmarRecurrente, authorization: str = Header(...)):
    """Registra la ocurrencia pendiente como transacción (con monto, fecha y cuenta ajustables) y avanza la serie.

    Es UNA función SQL atómica (CHG-025, INV-052, ADR-009 punto 13): bloquea la recurrente, compara la fecha, crea la transacción
    y avanza `proxima_fecha` en la misma transacción. Si falla (saldo, cuenta archivada, error de la BD) la fecha NO avanza.
    Sin la función SQL → 503: nunca el flujo anterior de avanzar, crear y revertir."""
    usuario_id = await get_user_id(authorization)
    recurrente = _ensure_owner(await RecurrenteDB.obtener_por_id(recurrente_id, usuario_id), usuario_id,
                               "Recurrente no encontrada")
    if datos.fecha is not None:
        _fecha(datos.fecha)
    # Lectura previa solo para dar el mensaje correcto; la comprobación que manda es la de la función SQL (bajo bloqueo)
    if not recurrente.get("activa"):
        raise HTTPException(status_code=409, detail="La recurrente está pausada")
    if datos.ocurrencia != recurrente["proxima_fecha"]:
        raise HTTPException(status_code=409, detail=_OCURRENCIA_CAMBIADA)
    # `cuenta_id` enviado (también null = sin cuenta) reemplaza la de la plantilla; no enviado = la de la plantilla
    cuenta_indicada = "cuenta_id" in datos.model_fields_set
    cuenta_id = datos.cuenta_id if cuenta_indicada else None
    await _ensure_cuenta_propia(cuenta_id, usuario_id)   # INV-046: 404 y la fecha no avanza
    if (cuenta_id if cuenta_indicada else recurrente.get("cuenta_id")):
        _ensure_monto_con_cuenta(datos.monto if datos.monto is not None else recurrente["monto"])   # INV-051
    siguiente = siguiente_fecha(_fecha(datos.ocurrencia), recurrente["frecuencia"], int(recurrente["dia_ancla"])).isoformat()
    try:
        transaccion = await RecurrenteDB.confirmar(usuario_id, recurrente_id, datos.ocurrencia, siguiente, datos.monto,
                                                   datos.fecha, cuenta_id, cuenta_indicada)
    except (HTTPException, EstadoNoDisponible):
        raise
    except Exception as e:
        if codigo_de(e) == "OCURRENCIA_CAMBIADA":   # otra petición (doble toque, otra pestaña) la movió o la pausó
            raise HTTPException(status_code=409, detail=_OCURRENCIA_CAMBIADA) from None
        http = traducir_error_cuenta(e)   # FZ001/FZ002 → 409, 23503 → 404, 22003/23514 → 422
        if http is not None:
            raise http from None
        print(f"[recurrentes.confirmar] No se pudo registrar ({type(e).__name__})")   # sin el texto de la BD
        raise HTTPException(status_code=500, detail="No se pudo registrar la transacción") from None
    if transaccion is None:
        raise HTTPException(status_code=404, detail="Recurrente no encontrada")
    return {"transaccion": transaccion, "recurrente": {**recurrente, "proxima_fecha": siguiente}}


@router.post("/recurrentes/{recurrente_id}/omitir", response_model=RecurrenteResponse)
async def omitir_recurrente(recurrente_id: str, datos: OcurrenciaRecurrente, authorization: str = Header(...)):
    """Salta la ocurrencia pendiente sin registrar nada (p. ej. un mes sin pagar el gimnasio)."""
    usuario_id = await get_user_id(authorization)
    recurrente = _ensure_owner(await RecurrenteDB.obtener_por_id(recurrente_id, usuario_id), usuario_id,
                               "Recurrente no encontrada")
    avanzada, _ = await _avanzar(recurrente, usuario_id, datos.ocurrencia)
    return avanzada
