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
    MES_PATTERN,
)
from app.models.plataapp import (
    TransaccionDB, CategoriaDB, PresupuestoDB, MetaDB, RecurrenteDB, AbonoAtomicoNoDisponible,
)
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


def _porcentaje(meta: dict) -> float:
    objetivo = float(meta["monto_objetivo"])
    return float(meta["monto_actual"]) / objetivo * 100 if objetivo > 0 else 0


# ==================== TRANSACCIONES ====================

@router.post("/transacciones", response_model=TransaccionResponse)
async def crear_transaccion(transaccion: TransaccionCreate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    await _ensure_categoria_propia(transaccion.categoria_id, usuario_id)
    return await TransaccionDB.crear(
        usuario_id=usuario_id,
        categoria_id=transaccion.categoria_id,
        monto=transaccion.monto,
        descripcion=transaccion.descripcion,
        fecha=transaccion.fecha,
        tipo=transaccion.tipo,
        medio_pago=transaccion.medio_pago,
    )


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
    _ensure_owner(await TransaccionDB.obtener_por_id(transaccion_id, usuario_id), usuario_id, "Transacción no encontrada")
    await _ensure_categoria_propia(transaccion.categoria_id, usuario_id)
    datos = transaccion.model_dump()
    # Si el cliente no envía medio_pago, se conserva el que tenía (null explícito = quitarlo)
    if "medio_pago" not in transaccion.model_fields_set:
        datos.pop("medio_pago")
    actualizada = await TransaccionDB.actualizar(transaccion_id, usuario_id, **datos)
    if not actualizada:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    return actualizada


@router.delete("/transacciones/{transaccion_id}")
async def eliminar_transaccion(transaccion_id: str, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    _ensure_owner(await TransaccionDB.obtener_por_id(transaccion_id, usuario_id), usuario_id, "Transacción no encontrada")
    await TransaccionDB.eliminar(transaccion_id, usuario_id)
    return {"message": "Transacción eliminada"}


# ==================== CATEGORÍAS ====================

@router.post("/categorias", response_model=CategoriaResponse)
async def crear_categoria(categoria: CategoriaCreate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    return await CategoriaDB.crear(
        usuario_id=usuario_id,
        nombre=categoria.nombre,
        icono=categoria.icono,
        tipo=categoria.tipo
    )


@router.get("/categorias", response_model=list[CategoriaResponse])
async def obtener_categorias(authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    return await CategoriaDB.obtener_por_usuario(usuario_id)


@router.put("/categorias/{categoria_id}", response_model=CategoriaResponse)
async def actualizar_categoria(categoria_id: str, datos: CategoriaUpdate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    _ensure_owner(await CategoriaDB.obtener_por_id(categoria_id, usuario_id), usuario_id, "Categoría no encontrada")
    actualizada = await CategoriaDB.actualizar(categoria_id, usuario_id, datos.nombre, datos.icono, datos.tipo)
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
    return await PresupuestoDB.crear(
        usuario_id=usuario_id,
        categoria_id=presupuesto.categoria_id,
        limite_mensual=presupuesto.limite_mensual,
        mes_ano=presupuesto.mes_ano
    )


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
        await PresupuestoDB.crear(
            usuario_id=usuario_id,
            categoria_id=categoria_id,
            limite_mensual=float(presupuesto["limite_mensual"]),
            mes_ano=datos.hacia,
        )
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
    """Registra un aporte a una meta: crea transacción de gasto y aumenta monto_actual."""
    usuario_id = await get_user_id(authorization)

    # 1) Camino atómico: una sola transacción en PostgreSQL (CHG-004)
    try:
        meta_actualizada = await MetaDB.abonar(meta_id, usuario_id, datos.monto, datos.fecha, datos.descripcion)
    except AbonoAtomicoNoDisponible:
        return await _abonar_sin_transaccion(meta_id, usuario_id, datos)
    except Exception:
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
    primera = _fecha(datos.proxima_fecha)
    return await RecurrenteDB.crear(usuario_id, {**datos.model_dump(), "dia_ancla": primera.day})


@router.put("/recurrentes/{recurrente_id}", response_model=RecurrenteResponse)
async def actualizar_recurrente(recurrente_id: str, datos: RecurrenteUpdate, authorization: str = Header(...)):
    usuario_id = await get_user_id(authorization)
    actual = _ensure_owner(await RecurrenteDB.obtener_por_id(recurrente_id, usuario_id), usuario_id,
                           "Recurrente no encontrada")
    await _ensure_categoria_propia(datos.categoria_id, usuario_id)
    cambios = datos.model_dump(exclude={"proxima_fecha", "proxima_fecha_vista"})
    if datos.proxima_fecha is not None and datos.proxima_fecha != actual["proxima_fecha"]:
        nueva = _fecha(datos.proxima_fecha)
        # Cambiar la fecha exige que la persona haya visto la actual (INV-026): si entretanto se
        # confirmó u omitió una ocurrencia (otra pestaña, el panel de pendientes), 409 y nada cambia.
        if datos.proxima_fecha_vista != actual["proxima_fecha"]:
            raise HTTPException(status_code=409, detail=_FECHA_CAMBIADA)
        if not await RecurrenteDB.avanzar(recurrente_id, usuario_id, actual["proxima_fecha"], nueva.isoformat()):
            raise HTTPException(status_code=409, detail=_FECHA_CAMBIADA)
        # El día ancla solo cambia si la persona eligió otra próxima fecha: editar el monto de una
        # recurrente del 31 que hoy cae el 28 de febrero no debe volverla "del 28" para siempre.
        cambios["dia_ancla"] = nueva.day
    actualizada = await RecurrenteDB.actualizar(recurrente_id, usuario_id, cambios)
    if not actualizada:
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
    """Registra la ocurrencia pendiente como transacción (con monto y fecha ajustables) y avanza la serie."""
    usuario_id = await get_user_id(authorization)
    recurrente = _ensure_owner(await RecurrenteDB.obtener_por_id(recurrente_id, usuario_id), usuario_id,
                               "Recurrente no encontrada")
    if datos.fecha is not None:
        _fecha(datos.fecha)
    avanzada, siguiente = await _avanzar(recurrente, usuario_id, datos.ocurrencia)
    try:
        transaccion = await TransaccionDB.crear(
            usuario_id=usuario_id,
            categoria_id=recurrente.get("categoria_id") or "",
            monto=datos.monto if datos.monto is not None else float(recurrente["monto"]),
            descripcion=recurrente.get("descripcion") or "",
            fecha=datos.fecha or datos.ocurrencia,
            tipo=recurrente["tipo"],
            medio_pago=recurrente.get("medio_pago"),
        )
    except Exception:
        # Sin transacción la ocurrencia vuelve a quedar pendiente (no se pierde)
        try:
            revertida = await RecurrenteDB.avanzar(recurrente_id, usuario_id, siguiente, datos.ocurrencia)
        except Exception as e:
            revertida = None
            print(f"[recurrentes.confirmar] no se pudo revertir ({type(e).__name__})")
        if not revertida:
            print(f"[recurrentes.confirmar] la ocurrencia {datos.ocurrencia} de {recurrente_id} quedó saltada sin transacción")
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo registrar la transacción y la fecha {datos.ocurrencia} quedó omitida. "
                       "Regístrala a mano en Transacciones.",
            )
        raise HTTPException(status_code=500, detail="No se pudo registrar la transacción")
    return {"transaccion": transaccion, "recurrente": avanzada}


@router.post("/recurrentes/{recurrente_id}/omitir", response_model=RecurrenteResponse)
async def omitir_recurrente(recurrente_id: str, datos: OcurrenciaRecurrente, authorization: str = Header(...)):
    """Salta la ocurrencia pendiente sin registrar nada (p. ej. un mes sin pagar el gimnasio)."""
    usuario_id = await get_user_id(authorization)
    recurrente = _ensure_owner(await RecurrenteDB.obtener_por_id(recurrente_id, usuario_id), usuario_id,
                               "Recurrente no encontrada")
    avanzada, _ = await _avanzar(recurrente, usuario_id, datos.ocurrencia)
    return avanzada
