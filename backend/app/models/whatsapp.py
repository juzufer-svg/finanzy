"""
Datos de WhatsApp (CHG-014): número enlazado, mensajes ya procesados y transacciones creadas por WhatsApp.

Con Supabase usa las tablas de `backend/sql/2026-11-23_whatsapp.sql`; sin Supabase (desarrollo y
pruebas) guarda en memoria. Los errores de Supabase se propagan (INV-013): nunca se guarda en memoria
en producción.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.supabase import SupabaseDB
from app.core.config import settings


def _supabase_ok() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _es_duplicado(error: Exception) -> bool:
    codigo = getattr(error, "code", None)
    return str(codigo) == "23505" if codigo is not None else False


class _Memoria:
    """Almacén del modo demo (se vacía en las pruebas)."""
    enlaces: dict[str, str] = {}        # usuario_id → teléfono
    mensajes: set[str] = set()          # wamid procesados
    registros: list[dict] = []          # {transaccion_id, usuario_id, lote, creado_en}

    @classmethod
    def limpiar(cls) -> None:
        cls.enlaces.clear()
        cls.mensajes.clear()
        cls.registros.clear()


class WhatsappDB:

    # ── Enlace número ↔ cuenta ──
    @staticmethod
    async def usuario_de_telefono(telefono: str) -> Optional[str]:
        if not _supabase_ok():
            return next((u for u, t in _Memoria.enlaces.items() if t == telefono), None)
        client = SupabaseDB.get_client()
        r = client.table("whatsapp_enlaces").select("usuario_id").eq("telefono", telefono).limit(1).execute()
        return str(r.data[0]["usuario_id"]) if r.data else None

    @staticmethod
    async def telefono_de_usuario(usuario_id: str) -> Optional[str]:
        if not _supabase_ok():
            return _Memoria.enlaces.get(usuario_id)
        client = SupabaseDB.get_client()
        r = client.table("whatsapp_enlaces").select("telefono").eq("usuario_id", usuario_id).limit(1).execute()
        return r.data[0]["telefono"] if r.data else None

    @staticmethod
    async def enlazar(usuario_id: str, telefono: str) -> None:
        """Enlaza el número a la cuenta. Quita antes cualquier enlace previo del número o de la cuenta."""
        if not _supabase_ok():
            for u in [u for u, t in _Memoria.enlaces.items() if t == telefono]:
                del _Memoria.enlaces[u]
            _Memoria.enlaces[usuario_id] = telefono
            return
        client = SupabaseDB.get_client()
        client.table("whatsapp_enlaces").delete().eq("telefono", telefono).execute()
        client.table("whatsapp_enlaces").delete().eq("usuario_id", usuario_id).execute()
        client.table("whatsapp_enlaces").insert({"usuario_id": usuario_id, "telefono": telefono}).execute()

    @staticmethod
    async def desenlazar(usuario_id: str) -> None:
        if not _supabase_ok():
            _Memoria.enlaces.pop(usuario_id, None)
            return
        SupabaseDB.get_client().table("whatsapp_enlaces").delete().eq("usuario_id", usuario_id).execute()

    # ── Mensajes procesados (idempotencia) ──
    @staticmethod
    async def marcar_procesado(wamid: str, usuario_id: Optional[str]) -> bool:
        """True si es la primera vez que se ve el mensaje; False si ya se había procesado."""
        if not _supabase_ok():
            if wamid in _Memoria.mensajes:
                return False
            _Memoria.mensajes.add(wamid)
            return True
        try:
            fila = {"id": wamid[:200], "usuario_id": usuario_id}
            SupabaseDB.get_client().table("whatsapp_mensajes").insert(fila).execute()
            return True
        except Exception as e:
            if _es_duplicado(e):
                return False
            raise

    @staticmethod
    async def limpiar_mensajes_antiguos(dias: int = 7) -> None:
        """Borra los ids de mensajes procesados de más de `dias` (Meta solo reintenta durante unos días)."""
        if not _supabase_ok():
            return
        limite = (_ahora() - timedelta(days=dias)).isoformat()
        SupabaseDB.get_client().table("whatsapp_mensajes").delete().lt("recibido_en", limite).execute()

    # ── Transacciones creadas por WhatsApp ──
    @staticmethod
    async def guardar_registro(transaccion_id: str, usuario_id: str, lote: str) -> None:
        if not _supabase_ok():
            _Memoria.registros.append({"transaccion_id": transaccion_id, "usuario_id": usuario_id,
                                       "lote": lote, "creado_en": _ahora()})
            return
        SupabaseDB.get_client().table("whatsapp_registros").insert(
            {"transaccion_id": transaccion_id, "usuario_id": usuario_id, "lote": lote[:200]}
        ).execute()

    @staticmethod
    async def ultimo_lote(usuario_id: str, horas: int = 24) -> list[str]:
        """Ids de las transacciones del último mensaje que registró algo (de las últimas `horas`),
        en el orden en que se crearon (para «corrige el segundo»)."""
        desde = _ahora() - timedelta(hours=horas)
        if not _supabase_ok():
            propias = [r for r in _Memoria.registros if r["usuario_id"] == usuario_id and r["creado_en"] >= desde]
            if not propias:
                return []
            lote = max(propias, key=lambda r: r["creado_en"])["lote"]
            return [r["transaccion_id"] for r in propias if r["lote"] == lote]
        client = SupabaseDB.get_client()
        r = (client.table("whatsapp_registros").select("lote").eq("usuario_id", usuario_id)
             .gte("creado_en", desde.isoformat()).order("creado_en", desc=True).limit(1).execute())
        if not r.data:
            return []
        lote = r.data[0]["lote"]
        filas = (client.table("whatsapp_registros").select("transaccion_id")
                 .eq("usuario_id", usuario_id).eq("lote", lote).order("creado_en").execute())
        return [str(f["transaccion_id"]) for f in filas.data]

    @staticmethod
    async def quitar_registro(transaccion_id: str, usuario_id: str) -> None:
        if not _supabase_ok():
            _Memoria.registros[:] = [r for r in _Memoria.registros
                                     if not (r["transaccion_id"] == transaccion_id and r["usuario_id"] == usuario_id)]
            return
        (SupabaseDB.get_client().table("whatsapp_registros").delete()
         .eq("transaccion_id", transaccion_id).eq("usuario_id", usuario_id).execute())
