"""
Acceso a datos de las transferencias entre cuentas de dinero (CHG-024, ADR-009, INV-046 a INV-051).

Mismo patrón que `models/cuentas.py` y MISMO ejecutor propio y acotado (4 hilos, 503 inmediato sin encolar, plazo real):
reutiliza `_llamar`, así que un error de la regla de negocio (FZ001, FZ002, 22003, 23503, 23514) vuelve como `ErrorBD` y
cualquier otro fallo es `EstadoNoDisponible`. Toda consulta filtra por el usuario de la sesión. Los dos saldos se mueven en
UNA fila de `transferencias` (atómica; el disparador `fz001_saldo_transferencias` valida bajo bloqueo). Nada del texto de la
BD sale en respuestas ni registros. Modo demo: `DemoTransferenciaDB` con las mismas reglas.
"""
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from app.models import auth_estado
from app.models.auth_estado import EstadoNoDisponible
from app.models.cuentas import _decimal_texto, _llamar, _modo, _numero
from app.models.demo_db import DemoTransferenciaDB

# Únicas columnas reales de `transferencias` (backend/sql/2026-11-25_transferencias.sql)
COLUMNAS = "id,usuario_id,cuenta_origen_id,cuenta_destino_id,monto,fecha,descripcion,created_at"
TOPE_LISTA = 1000   # la lista nunca crece sin límite


def _fila(f: Any) -> dict:
    """Una transferencia con la lista blanca de CT-012 (nada más sale de la BD)."""
    if not isinstance(f, dict) or not all(k in f for k in ("id", "usuario_id", "cuenta_origen_id", "cuenta_destino_id", "monto", "fecha")):
        raise EstadoNoDisponible("fila inesperada")
    descripcion = f.get("descripcion")
    return {
        "id": str(f["id"]), "usuario_id": str(f["usuario_id"]), "cuenta_origen_id": str(f["cuenta_origen_id"]),
        "cuenta_destino_id": str(f["cuenta_destino_id"]), "monto": _numero(f["monto"]), "fecha": str(f["fecha"])[:10],
        "descripcion": None if descripcion is None else str(descripcion), "created_at": f.get("created_at"),
    }


def _siguiente_mes(mes: str) -> str:
    anio, m = int(mes[:4]), int(mes[5:7])
    return date(anio + (m == 12), 1 if m == 12 else m + 1, 1).isoformat()


class TransferenciaDB:

    @staticmethod
    async def crear(usuario_id: str, origen_id: str, destino_id: str, monto: Decimal, fecha: str,
                    descripcion: Optional[str]) -> dict:
        if _modo() == "memoria":
            return await DemoTransferenciaDB.crear(usuario_id, origen_id, destino_id, monto, fecha, descripcion)
        fila = {"id": str(uuid.uuid4()), "usuario_id": usuario_id, "cuenta_origen_id": origen_id,
                "cuenta_destino_id": destino_id, "monto": _decimal_texto(monto), "fecha": fecha, "descripcion": descripcion}
        datos = await _llamar("transferencias_crear", lambda: auth_estado.cliente_estado().table("transferencias")
                              .insert(fila).execute().data)
        if not isinstance(datos, list) or len(datos) != 1:
            raise EstadoNoDisponible("respuesta inesperada")
        return _fila(datos[0])

    @staticmethod
    async def listar(usuario_id: str, mes: Optional[str] = None) -> list:
        """Las del usuario, más recientes primero (fecha desc, id desc). `mes` = YYYY-MM ya validado."""
        if _modo() == "memoria":
            return await DemoTransferenciaDB.listar(usuario_id, mes)

        def consulta():
            q = auth_estado.cliente_estado().table("transferencias").select(COLUMNAS).eq("usuario_id", usuario_id)
            if mes:
                q = q.gte("fecha", f"{mes}-01").lt("fecha", _siguiente_mes(mes))
            return q.order("fecha", desc=True).order("id", desc=True).limit(TOPE_LISTA).execute().data
        datos = await _llamar("transferencias_listar", consulta)
        if not isinstance(datos, list):
            raise EstadoNoDisponible("lista inesperada")
        filas = [_fila(f) for f in datos]
        if any(t["usuario_id"] != str(usuario_id) for t in filas):   # defensa en profundidad (INV-046)
            raise EstadoNoDisponible("transferencia ajena en la lista")
        return filas

    @staticmethod
    async def obtener_por_id(transferencia_id: str, usuario_id: str) -> Optional[dict]:
        if _modo() == "memoria":
            return await DemoTransferenciaDB.obtener_por_id(transferencia_id, usuario_id)
        datos = await _llamar("transferencias_obtener", lambda: auth_estado.cliente_estado().table("transferencias")
                              .select(COLUMNAS).eq("id", transferencia_id).eq("usuario_id", usuario_id).limit(1).execute().data)
        if not isinstance(datos, list):
            raise EstadoNoDisponible("lista inesperada")
        return _fila(datos[0]) if datos else None

    @staticmethod
    async def eliminar(transferencia_id: str, usuario_id: str) -> bool:
        """True si se eliminó. La BD rechaza (FZ001/FZ002 → ErrorBD) si dejaría el destino en negativo o hay una cuenta archivada."""
        if _modo() == "memoria":
            return await DemoTransferenciaDB.eliminar(transferencia_id, usuario_id)
        datos = await _llamar("transferencias_eliminar", lambda: auth_estado.cliente_estado().table("transferencias").delete()
                              .eq("id", transferencia_id).eq("usuario_id", usuario_id).execute().data)
        if not isinstance(datos, list):
            raise EstadoNoDisponible("respuesta inesperada")
        return bool(datos)
