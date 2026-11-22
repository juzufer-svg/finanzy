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
    MES_PATTERN,
)
from app.models.plataapp import TransaccionDB, CategoriaDB, PresupuestoDB, MetaDB
from app.core.security import decode_token
from typing import Optional

router = APIRouter()


def get_user_id(authorization: str) -> str:
    """Extrae el usuario_id del token Bearer."""
    try:
        scheme, token = authorization.split(" ", 1)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Token inválido")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Token inválido")
    payload = decode_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Token inválido")
    return payload["sub"]


def _ensure_owner(registro: Optional[dict], usuario_id: str, detalle: str) -> dict:
    """404 si el registro no existe o es de otro usuario."""
    if not registro or str(registro.get("usuario_id")) != str(usuario_id):
        raise HTTPException(status_code=404, detail=detalle)
    return registro


async def _ensure_categoria_propia(categoria_id: Optional[str], usuario_id: str) -> None:
    """Valida que la categoría (si se envía) pertenezca al usuario."""
    if not categoria_id:
        return
    categoria = await CategoriaDB.obtener_por_id(categoria_id)
    _ensure_owner(categoria, usuario_id, "Categoría no encontrada")


def _porcentaje(meta: dict) -> float:
    objetivo = float(meta["monto_objetivo"])
    return float(meta["monto_actual"]) / objetivo * 100 if objetivo > 0 else 0


# ==================== TRANSACCIONES ====================

@router.post("/transacciones", response_model=TransaccionResponse)
async def crear_transaccion(transaccion: TransaccionCreate, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    await _ensure_categoria_propia(transaccion.categoria_id, usuario_id)
    return await TransaccionDB.crear(
        usuario_id=usuario_id,
        categoria_id=transaccion.categoria_id,
        monto=transaccion.monto,
        descripcion=transaccion.descripcion,
        fecha=transaccion.fecha,
        tipo=transaccion.tipo
    )


@router.get("/transacciones", response_model=list[TransaccionResponse])
async def obtener_transacciones(authorization: str = Header(...), mes: Optional[str] = None):
    usuario_id = get_user_id(authorization)
    if mes is not None and not MES_PATTERN.match(mes):
        raise HTTPException(status_code=422, detail="Formato de mes inválido (YYYY-MM)")
    return await TransaccionDB.obtener_por_usuario(usuario_id, mes)


@router.get("/transacciones/resumen/{mes}")
async def obtener_resumen(mes: str = Path(..., pattern=MES_PATTERN.pattern), authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    return await TransaccionDB.obtener_resumen(usuario_id, mes)


@router.get("/transacciones/{transaccion_id}", response_model=TransaccionResponse)
async def obtener_transaccion(transaccion_id: str, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    transaccion = await TransaccionDB.obtener_por_id(transaccion_id)
    return _ensure_owner(transaccion, usuario_id, "Transacción no encontrada")


@router.put("/transacciones/{transaccion_id}", response_model=TransaccionResponse)
async def actualizar_transaccion(transaccion_id: str, transaccion: TransaccionCreate, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    _ensure_owner(await TransaccionDB.obtener_por_id(transaccion_id), usuario_id, "Transacción no encontrada")
    await _ensure_categoria_propia(transaccion.categoria_id, usuario_id)
    actualizada = await TransaccionDB.actualizar(transaccion_id, **transaccion.model_dump())
    if not actualizada:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    return actualizada


@router.delete("/transacciones/{transaccion_id}")
async def eliminar_transaccion(transaccion_id: str, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    _ensure_owner(await TransaccionDB.obtener_por_id(transaccion_id), usuario_id, "Transacción no encontrada")
    await TransaccionDB.eliminar(transaccion_id)
    return {"message": "Transacción eliminada"}


# ==================== CATEGORÍAS ====================

@router.post("/categorias", response_model=CategoriaResponse)
async def crear_categoria(categoria: CategoriaCreate, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    return await CategoriaDB.crear(
        usuario_id=usuario_id,
        nombre=categoria.nombre,
        icono=categoria.icono,
        tipo=categoria.tipo
    )


@router.get("/categorias", response_model=list[CategoriaResponse])
async def obtener_categorias(authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    return await CategoriaDB.obtener_por_usuario(usuario_id)


@router.put("/categorias/{categoria_id}", response_model=CategoriaResponse)
async def actualizar_categoria(categoria_id: str, datos: CategoriaUpdate, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    _ensure_owner(await CategoriaDB.obtener_por_id(categoria_id), usuario_id, "Categoría no encontrada")
    actualizada = await CategoriaDB.actualizar(categoria_id, datos.nombre, datos.icono, datos.tipo)
    if not actualizada:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return actualizada


@router.delete("/categorias/{categoria_id}")
async def eliminar_categoria(categoria_id: str, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    _ensure_owner(await CategoriaDB.obtener_por_id(categoria_id), usuario_id, "Categoría no encontrada")
    try:
        await CategoriaDB.eliminar(categoria_id)
    except Exception:
        raise HTTPException(
            status_code=409,
            detail="No se pudo eliminar. Puede tener transacciones asociadas.",
        )
    return {"message": "Categoría eliminada"}


# ==================== PRESUPUESTOS ====================

@router.post("/presupuestos", response_model=PresupuestoResponse)
async def crear_presupuesto(presupuesto: PresupuestoCreate, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    await _ensure_categoria_propia(presupuesto.categoria_id, usuario_id)
    return await PresupuestoDB.crear(
        usuario_id=usuario_id,
        categoria_id=presupuesto.categoria_id,
        limite_mensual=presupuesto.limite_mensual,
        mes_ano=presupuesto.mes_ano
    )


@router.get("/presupuestos/{mes_ano}", response_model=list[PresupuestoResponse])
async def obtener_presupuestos(mes_ano: str = Path(..., pattern=MES_PATTERN.pattern), authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    return await PresupuestoDB.obtener_por_usuario_mes(usuario_id, mes_ano)


@router.put("/presupuestos/{presupuesto_id}", response_model=PresupuestoResponse)
async def actualizar_presupuesto(presupuesto_id: str, datos: PresupuestoUpdate, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    _ensure_owner(await PresupuestoDB.obtener_por_id(presupuesto_id), usuario_id, "Presupuesto no encontrado")
    actualizado = await PresupuestoDB.actualizar(presupuesto_id, datos.limite_mensual)
    if not actualizado:
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
    return actualizado


@router.delete("/presupuestos/{presupuesto_id}")
async def eliminar_presupuesto(presupuesto_id: str, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    _ensure_owner(await PresupuestoDB.obtener_por_id(presupuesto_id), usuario_id, "Presupuesto no encontrado")
    await PresupuestoDB.eliminar(presupuesto_id)
    return {"message": "Presupuesto eliminado"}


# ==================== METAS ====================

@router.post("/metas", response_model=MetaResponse)
async def crear_meta(meta: MetaCreate, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    nueva = await MetaDB.crear(
        usuario_id=usuario_id,
        nombre=meta.nombre,
        monto_objetivo=meta.monto_objetivo,
        fecha_objetivo=meta.fecha_objetivo
    )
    return {**nueva, "porcentaje_completado": 0}


@router.get("/metas", response_model=list[MetaResponse])
async def obtener_metas(authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    metas = await MetaDB.obtener_por_usuario(usuario_id)
    for meta in metas:
        meta["porcentaje_completado"] = _porcentaje(meta)
    return metas


@router.put("/metas/{meta_id}", response_model=MetaResponse)
async def actualizar_meta(meta_id: str, actualizacion: ActualizarMeta, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    _ensure_owner(await MetaDB.obtener_por_id(meta_id), usuario_id, "Meta no encontrada")
    updates = {k: v for k, v in actualizacion.model_dump().items() if v is not None}
    meta = await MetaDB.actualizar_progreso(meta_id, updates)
    if not meta:
        raise HTTPException(status_code=404, detail="Meta no encontrada")
    return {**meta, "porcentaje_completado": _porcentaje(meta)}


@router.delete("/metas/{meta_id}")
async def eliminar_meta(meta_id: str, authorization: str = Header(...)):
    usuario_id = get_user_id(authorization)
    _ensure_owner(await MetaDB.obtener_por_id(meta_id), usuario_id, "Meta no encontrada")
    await MetaDB.eliminar(meta_id)
    return {"message": "Meta eliminada"}


@router.post("/metas/{meta_id}/abonar", response_model=MetaResponse)
async def abonar_meta(meta_id: str, datos: AbonarMeta, authorization: str = Header(...)):
    """Registra un aporte a una meta: crea transacción de gasto y aumenta monto_actual."""
    usuario_id = get_user_id(authorization)

    # Validar la meta ANTES de registrar el gasto (evita transacciones huérfanas)
    meta = _ensure_owner(await MetaDB.obtener_por_id(meta_id), usuario_id, "Meta no encontrada")

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
        meta_actualizada = await MetaDB.actualizar_progreso(meta_id, {"monto_actual": nuevo_monto})
        if not meta_actualizada:
            raise RuntimeError("No se pudo actualizar la meta")
    except Exception:
        await TransaccionDB.eliminar(transaccion["id"])
        raise HTTPException(status_code=500, detail="No se pudo registrar el abono")

    return {**meta_actualizada, "porcentaje_completado": _porcentaje(meta_actualizada)}
