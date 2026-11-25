"""
Acceso a datos del panel de administración de usuarios (CHG-023, ADR-012, INV-055 a INV-060, INV-062).

Todo pasa por las funciones SQL de `backend/sql/2026-11-25_admin_usuarios.sql` (RPC), que arman el `jsonb` con claves
explícitas y hacen cada acción con su auditoría en UNA transacción. Este módulo solo las llama:
- Plazo real: ejecutor propio y acotado del estado de autenticación (`auth_estado.ejecutar`), cliente de 4 s y presupuesto de
  5 s por petición; sin hilo libre o sin presupuesto, `EstadoNoDisponible` (503 sin encolar). Fail-closed: cualquier fallo
  o respuesta inesperada también.
- Privacidad: ningún aviso lleva correos, ids ni el texto de la excepción (solo el nombre de la operación y el tipo).
- Modo demo (solo sin Supabase y fuera de producción): almacén en memoria con la MISMA semántica que las funciones SQL.
  En producción sin Supabase, `EstadoNoDisponible`.
"""
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.models import auth_estado
from app.models.auth_estado import EstadoNoDisponible

POR_PAGINA = 25
RETENCION_DIAS = 365
TOPE_AUDITORIA = 10_000
ACCIONES = ("suspender", "reactivar", "cerrar_sesiones", "eliminar")

RESULTADOS_ACCION = ("ok", "no_existe", "ya", "pendiente", "no_suspendida", "correo_distinto")


def _rpc(nombre: str, args: dict) -> Any:
    """Llamada RPC bloqueante: se ejecuta SIEMPRE en un hilo del ejecutor propio (`auth_estado.ejecutar`)."""
    return auth_estado.cliente_estado().rpc(nombre, args).execute().data


def _modo() -> str:
    return auth_estado._modo()


async def _llamar(operacion: str, nombre: str, args: dict) -> Any:
    return await auth_estado.ejecutar(operacion, lambda: _rpc(nombre, args))


def _objeto(dato: Any) -> dict:
    if isinstance(dato, list) and len(dato) == 1:
        dato = dato[0]
    if not isinstance(dato, dict):
        raise EstadoNoDisponible("respuesta inesperada")
    return dato


def _resultado(dato: Any) -> str:
    if isinstance(dato, list) and len(dato) == 1:
        dato = dato[0]
    if not isinstance(dato, str) or dato not in RESULTADOS_ACCION:
        raise EstadoNoDisponible("respuesta inesperada")
    return dato


# ── Modo demo: misma semántica que las funciones SQL ──────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class _Memoria:
    """Solo existe sin Supabase y fuera de producción. `usuarios` es el almacén de usuarios del modo demo (por correo)."""
    lock = threading.RLock()
    usuarios: dict[str, dict] = {}
    auditoria: list[dict] = []
    siguiente_id = 1

    @classmethod
    def limpiar(cls) -> None:
        with cls.lock:
            cls.usuarios = {}
            cls.auditoria = []
            cls.siguiente_id = 1


def _mem_usuario(usuario_id: str) -> Optional[dict]:
    return next((u for u in _Memoria.usuarios.values() if u.get("id") == usuario_id), None)


def _mem_estado(u: dict) -> str:
    if u.get("suspendida"):
        return "suspendida"
    return "activa" if u.get("is_active") else "pendiente"


def _mem_contar(usuario_id: str, coleccion: dict) -> int:
    return sum(1 for fila in coleccion.values() if fila.get("usuario_id") == usuario_id)


def _mem_colecciones() -> dict[str, dict]:
    from app.models import demo_db
    return {
        "transacciones": demo_db.DemoTransaccionDB._transacciones,
        "categorias": demo_db.DemoCategoriaDB._categorias,
        "presupuestos": demo_db.DemoPresupuestoDB._presupuestos,
        "metas": demo_db.DemoMetaDB._metas,
        "recurrentes": demo_db.DemoRecurrenteDB._recurrentes,
        "cuentas": demo_db.DemoCuentaDB._cuentas,   # CHG-019: borrar al usuario borra sus cuentas de dinero (INV-050)
    }


def _mem_fila(u: dict, completo: bool) -> dict:
    from app.models import whatsapp as whatsapp_db
    cols = _mem_colecciones()
    uso: dict[str, Any] = {"transacciones": _mem_contar(u["id"], cols["transacciones"])}
    if completo:
        for nombre in ("categorias", "presupuestos", "metas", "recurrentes"):
            uso[nombre] = _mem_contar(u["id"], cols[nombre])
        uso["whatsapp_conectado"] = u["id"] in whatsapp_db._Memoria.enlaces
    fecha = u.get("ultimo_acceso")
    return {
        "id": u["id"], "correo": u.get("email", ""), "nombre": u.get("full_name") or None, "estado": _mem_estado(u),
        "moneda": u.get("currency"), "registrado_en": u.get("created_at"),
        "ultimo_acceso": fecha.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(fecha, datetime) else fecha,
        "uso": uso,
    }


def _mem_auditar(accion: str, usuario_id: str) -> None:
    ahora = _ahora()
    _Memoria.auditoria.append({"id": _Memoria.siguiente_id, "creado_en": ahora, "accion": accion, "usuario_id": usuario_id})
    _Memoria.siguiente_id += 1
    corte = ahora - timedelta(days=RETENCION_DIAS)
    _Memoria.auditoria[:] = [r for r in _Memoria.auditoria if r["creado_en"] >= corte]
    del _Memoria.auditoria[:-TOPE_AUDITORIA]


def _mem_desenlazar(usuario_id: str) -> None:
    from app.models import whatsapp as whatsapp_db
    whatsapp_db._Memoria.enlaces.pop(usuario_id, None)


def _mem_listar(q: Optional[str], desplazamiento: int) -> dict:
    with _Memoria.lock:
        patron = q.lower() if q else None
        todos = [u for u in _Memoria.usuarios.values()
                 if patron is None or patron in (u.get("email") or "").lower() or patron in (u.get("full_name") or "").lower()]
        todos.sort(key=lambda u: str(u.get("id")))
        todos.sort(key=lambda u: str(u.get("created_at") or ""), reverse=True)
        pagina = todos[max(desplazamiento, 0):max(desplazamiento, 0) + POR_PAGINA]
        return {"total": len(todos), "usuarios": [_mem_fila(u, False) for u in pagina]}


def _mem_detalle(usuario_id: str) -> Optional[dict]:
    with _Memoria.lock:
        u = _mem_usuario(usuario_id)
        return _mem_fila(u, True) if u else None


def _mem_suspender(usuario_id: str) -> str:
    with _Memoria.lock:
        u = _mem_usuario(usuario_id)
        if u is None:
            return "no_existe"
        if u.get("suspendida"):
            return "ya"
        if not u.get("is_active"):
            return "pendiente"
        u["suspendida"] = True
        u["session_version"] = int(u.get("session_version") or 0) + 1
        _mem_desenlazar(usuario_id)
        _mem_auditar("suspender", usuario_id)
        return "ok"


def _mem_reactivar(usuario_id: str) -> str:
    with _Memoria.lock:
        u = _mem_usuario(usuario_id)
        if u is None:
            return "no_existe"
        if not u.get("suspendida"):
            return "no_suspendida"
        u["suspendida"] = False
        _mem_auditar("reactivar", usuario_id)
        return "ok"


def _mem_cerrar_sesiones(usuario_id: str) -> str:
    with _Memoria.lock:
        u = _mem_usuario(usuario_id)
        if u is None:
            return "no_existe"
        u["session_version"] = int(u.get("session_version") or 0) + 1
        _mem_desenlazar(usuario_id)
        _mem_auditar("cerrar_sesiones", usuario_id)
        return "ok"


def _mem_eliminar(usuario_id: str, correo: str) -> str:
    with _Memoria.lock:
        u = _mem_usuario(usuario_id)
        if u is None:
            return "no_existe"
        if (correo or "").strip().lower() != (u.get("email") or "").strip().lower():
            return "correo_distinto"
        _mem_auditar("eliminar", usuario_id)
        _mem_desenlazar(usuario_id)
        for coleccion in _mem_colecciones().values():
            for clave in [k for k, f in coleccion.items() if f.get("usuario_id") == usuario_id]:
                del coleccion[clave]
        for clave in [k for k, v in _Memoria.usuarios.items() if v is u]:
            del _Memoria.usuarios[clave]
        return "ok"


def _mem_auditoria(desplazamiento: int) -> dict:
    with _Memoria.lock:
        filas = sorted(_Memoria.auditoria, key=lambda r: (r["creado_en"], r["id"]), reverse=True)
        desde = max(desplazamiento, 0)
        registros = []
        for r in filas[desde:desde + POR_PAGINA]:
            u = _mem_usuario(r["usuario_id"])
            registros.append({"id": r["id"], "fecha": r["creado_en"].strftime("%Y-%m-%dT%H:%M:%SZ"), "accion": r["accion"],
                              "usuario_id": r["usuario_id"], "usuario_correo": u.get("email") if u else None})
        return {"total": len(filas), "registros": registros}


# ── API pública (asíncrona; nunca bloquea el event loop con la red) ───────────

async def listar(q: Optional[str], pagina: int) -> dict:
    """`{total, usuarios:[...]}`: UNA llamada a la BD (INV-060). `q` se pasa como parámetro de la función SQL."""
    desplazamiento = (pagina - 1) * POR_PAGINA
    if _modo() == "memoria":
        return _mem_listar(q, desplazamiento)
    return _objeto(await _llamar("admin_listar", "admin_listar_usuarios",
                                 {"p_q": q, "p_limite": POR_PAGINA, "p_desplazamiento": desplazamiento}))


async def detalle(usuario_id: str) -> Optional[dict]:
    """El usuario con sus conteos de uso, o None si no existe."""
    if _modo() == "memoria":
        return _mem_detalle(usuario_id)
    dato = await _llamar("admin_detalle", "admin_detalle_usuario", {"p_id": usuario_id})
    if isinstance(dato, list) and len(dato) == 1:
        dato = dato[0]
    return None if dato is None else _objeto(dato)


async def suspender(usuario_id: str) -> str:
    if _modo() == "memoria":
        return _mem_suspender(usuario_id)
    return _resultado(await _llamar("admin_suspender", "admin_suspender_usuario", {"p_id": usuario_id}))


async def reactivar(usuario_id: str) -> str:
    if _modo() == "memoria":
        return _mem_reactivar(usuario_id)
    return _resultado(await _llamar("admin_reactivar", "admin_reactivar_usuario", {"p_id": usuario_id}))


async def cerrar_sesiones(usuario_id: str) -> str:
    if _modo() == "memoria":
        return _mem_cerrar_sesiones(usuario_id)
    return _resultado(await _llamar("admin_cerrar_sesiones", "admin_cerrar_sesiones_usuario", {"p_id": usuario_id}))


async def eliminar(usuario_id: str, correo: str) -> str:
    """Auditoría + borrado con cascada en UNA función atómica (INV-058)."""
    if _modo() == "memoria":
        return _mem_eliminar(usuario_id, correo)
    return _resultado(await _llamar("admin_eliminar", "admin_eliminar_usuario", {"p_id": usuario_id, "p_correo": correo}))


async def auditoria(pagina: int) -> dict:
    """`{total, registros:[...]}` paginado (INV-059)."""
    desplazamiento = (pagina - 1) * POR_PAGINA
    if _modo() == "memoria":
        return _mem_auditoria(desplazamiento)
    return _objeto(await _llamar("admin_auditoria", "admin_auditoria",
                                 {"p_limite": POR_PAGINA, "p_desplazamiento": desplazamiento}))
