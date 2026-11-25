"""
Acceso a datos de las cuentas de dinero (CHG-019 fase a, ADR-009, INV-046 a INV-051).

- Toda consulta filtra por el usuario de la sesión (INV-001, INV-046); el saldo NUNCA se guarda: sale de la función SQL
  `cuentas_con_saldo` (INV-047), UNA consulta agregada por listado (REQ-N-022).
- Plazo real y fail-closed: las llamadas a Supabase corren en el ejecutor propio y acotado de `auth_estado` (cliente de 4 s,
  presupuesto de 5 s por petición, 503 sin encolar). Cualquier fallo o respuesta inesperada = `EstadoNoDisponible` (503).
  Solo los errores propios de la regla de negocio (SQLSTATE FZ001, FZ002, FZ003, 23505, 23503, 23514) se convierten en
  `ErrorBD`, que las rutas traducen a 409/404/422 sin exponer texto de la BD.
- Privacidad: ningún aviso lleva el texto de la excepción (solo el nombre de la operación y el tipo).
- Modo demo (solo sin Supabase y fuera de producción): `DemoCuentaDB`, con las mismas reglas. En producción sin Supabase,
  `EstadoNoDisponible`.
"""
import uuid
from decimal import Decimal
from typing import Any, Optional

from app.models import auth_estado
from app.models.auth_estado import EstadoNoDisponible
from app.models.demo_db import DemoCuentaDB, ErrorBD

# Únicas columnas reales de `cuentas` (backend/sql/2026-11-25_cuentas.sql)
COLUMNAS = "id,usuario_id,nombre,tipo,saldo_inicial,archivada,created_at"
CODIGOS_NEGOCIO = ("FZ001", "FZ002", "FZ003", "23505", "23503", "23514")


def _modo() -> str:
    return auth_estado._modo()


async def _llamar(operacion: str, fn):
    """Corre `fn` (bloqueante) en el ejecutor acotado. Un error de la regla de negocio vuelve como valor y se relanza aquí
    como `ErrorBD`; cualquier otro fallo es 503."""
    def corre():
        try:
            return ("ok", fn())
        except Exception as e:
            codigo = str(getattr(e, "code", "") or "")
            if codigo in CODIGOS_NEGOCIO:
                return ("bd", codigo)
            raise
    estado, valor = await auth_estado.ejecutar(operacion, corre)
    if estado == "bd":
        raise ErrorBD(valor)
    return valor


def _numero(valor: Any) -> float:
    if isinstance(valor, bool) or valor is None:
        raise EstadoNoDisponible("número inesperado")
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise EstadoNoDisponible("número inesperado")


def _fila(f: Any) -> dict:
    """Una cuenta con la lista blanca de CT-012 (nada más sale de la BD)."""
    if not isinstance(f, dict) or not all(k in f for k in ("id", "usuario_id", "nombre", "tipo", "saldo_inicial", "archivada")):
        raise EstadoNoDisponible("fila inesperada")
    saldo = f.get("saldo", f["saldo_inicial"])   # recién creada: el saldo es el inicial
    return {
        "id": str(f["id"]), "usuario_id": str(f["usuario_id"]), "nombre": str(f["nombre"]), "tipo": str(f["tipo"]),
        "saldo_inicial": _numero(f["saldo_inicial"]), "saldo": _numero(saldo), "archivada": bool(f["archivada"]),
        "created_at": f.get("created_at"),
    }


def _decimal_texto(valor: Decimal) -> str:
    return format(valor.quantize(Decimal("0.01")), "f")   # exacto, sin pasar por float


class CuentaDB:

    @staticmethod
    async def listar(usuario_id: str, incluir_archivadas: bool = False) -> list:
        """Cuentas del usuario con su saldo, por nombre. UNA consulta agregada (`cuentas_con_saldo`)."""
        if _modo() == "memoria":
            todas = await DemoCuentaDB.listar(usuario_id)
        else:
            datos = await _llamar("cuentas_listar", lambda: auth_estado.cliente_estado()
                                  .rpc("cuentas_con_saldo", {"p_usuario_id": usuario_id}).execute().data)
            if not isinstance(datos, list):
                raise EstadoNoDisponible("lista inesperada")
            todas = [_fila(f) for f in datos]
            if any(c["usuario_id"] != str(usuario_id) for c in todas):   # defensa en profundidad (INV-046)
                raise EstadoNoDisponible("cuenta ajena en la lista")
        return [c for c in todas if incluir_archivadas or not c["archivada"]]

    @staticmethod
    async def obtener_con_saldo(cuenta_id: str, usuario_id: str) -> Optional[dict]:
        """La cuenta con su saldo, o None si no existe o es de otro usuario (a lo sumo 20 cuentas por usuario)."""
        return next((c for c in await CuentaDB.listar(usuario_id, True) if c["id"] == str(cuenta_id)), None)

    @staticmethod
    async def obtener_por_id(cuenta_id: str, usuario_id: str) -> Optional[dict]:
        """Lectura ligera (sin saldo) para verificar al dueño; solo columnas reales y siempre filtrada por usuario."""
        if _modo() == "memoria":
            return await DemoCuentaDB.obtener_por_id(cuenta_id, usuario_id)
        datos = await _llamar("cuentas_obtener", lambda: auth_estado.cliente_estado().table("cuentas").select(COLUMNAS)
                              .eq("id", cuenta_id).eq("usuario_id", usuario_id).limit(1).execute().data)
        if not isinstance(datos, list):
            raise EstadoNoDisponible("lista inesperada")
        return datos[0] if datos else None

    @staticmethod
    async def crear(usuario_id: str, nombre: str, tipo: str, saldo_inicial: Decimal) -> dict:
        if _modo() == "memoria":
            return await DemoCuentaDB.crear(usuario_id, nombre, tipo, saldo_inicial)
        fila = {"id": str(uuid.uuid4()), "usuario_id": usuario_id, "nombre": nombre, "tipo": tipo,
                "saldo_inicial": _decimal_texto(saldo_inicial)}
        datos = await _llamar("cuentas_crear", lambda: auth_estado.cliente_estado().table("cuentas").insert(fila).execute().data)
        if not isinstance(datos, list) or len(datos) != 1:
            raise EstadoNoDisponible("respuesta inesperada")
        return _fila(datos[0])

    @staticmethod
    async def actualizar(cuenta_id: str, usuario_id: str, cambios: dict) -> Optional[dict]:
        """Edita nombre, saldo inicial y/o archivada (nunca el tipo). None si no existe o es de otro usuario."""
        if _modo() == "memoria":
            return await DemoCuentaDB.actualizar(cuenta_id, usuario_id, cambios)
        valores = {k: (_decimal_texto(v) if k == "saldo_inicial" else v)
                   for k, v in cambios.items() if k in ("nombre", "saldo_inicial", "archivada")}
        if valores:
            datos = await _llamar("cuentas_actualizar", lambda: auth_estado.cliente_estado().table("cuentas")
                                  .update(valores).eq("id", cuenta_id).eq("usuario_id", usuario_id).execute().data)
            if not isinstance(datos, list):
                raise EstadoNoDisponible("respuesta inesperada")
            if not datos:
                return None
        return await CuentaDB.obtener_con_saldo(cuenta_id, usuario_id)

    @staticmethod
    async def eliminar(cuenta_id: str, usuario_id: str) -> bool:
        """True si se eliminó. Con movimientos la BD rechaza (23503 → ErrorBD): se archiva (INV-050)."""
        if _modo() == "memoria":
            return await DemoCuentaDB.eliminar(cuenta_id, usuario_id)
        datos = await _llamar("cuentas_eliminar", lambda: auth_estado.cliente_estado().table("cuentas").delete()
                              .eq("id", cuenta_id).eq("usuario_id", usuario_id).execute().data)
        if not isinstance(datos, list):
            raise EstadoNoDisponible("respuesta inesperada")
        return bool(datos)
