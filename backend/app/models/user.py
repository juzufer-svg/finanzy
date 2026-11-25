"""
User model and database operations - Supabase
Tabla: users(id, email, hashed_password, full_name, currency, is_active, session_version, created_at, updated_at,
suspendida, ultimo_acceso)
"""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
import uuid
from app.core import security
from app.core.supabase import SupabaseDB
from app.models import auth_estado


PLAZO_REGISTRAR_ACCESO_SEG = 2.0   # plazo propio del último acceso (INV-061)
MAX_ESCRITURAS_ACCESO = 2          # límite PROPIO e independiente de los 8 hilos de auth_estado (INV-061, ADR-012)

_huecos_acceso = threading.BoundedSemaphore(MAX_ESCRITURAS_ACCESO)
_ejecutor_acceso = ThreadPoolExecutor(max_workers=MAX_ESCRITURAS_ACCESO, thread_name_prefix="auth-acceso")
_omitidos_acceso = 0


def _avisar_omision_acceso() -> None:
    """Cuenta las escrituras de último acceso omitidas por falta de hueco; avisa solo la 1.ª y luego cada 100 (sin datos)."""
    global _omitidos_acceso
    _omitidos_acceso += 1
    if _omitidos_acceso == 1 or _omitidos_acceso % 100 == 0:
        print(f"[user] Aviso: último acceso omitido por límite de escrituras simultáneas ({_omitidos_acceso} hasta ahora)")


def _map_user(row: dict) -> dict:
    return {
        "id": row["id"],
        "email": row.get("email", ""),
        "full_name": row.get("full_name") or "",
        "hashed_password": row.get("hashed_password", ""),
        "currency": row.get("currency", "USD"),
        "is_active": row.get("is_active", False),
        "suspendida": bool(row.get("suspendida", False)),   # CHG-023, INV-056: la cuenta suspendida no inicia ni conserva sesión
        "session_version": int(row.get("session_version") or 0),
    }


async def _hash_fuera_del_loop(password: str) -> str:
    """bcrypt (~0,3 s) en el ejecutor PROPIO y acotado de bcrypt (I-B, M-A): no bloquea el event loop; con los 8 hilos
    ocupados o sin presupuesto lanza `EstadoNoDisponible` (503) sin encolar. Busca `get_password_hash` al llamar."""
    return await auth_estado.ejecutar_bcrypt("hash_contrasena", lambda: security.get_password_hash(password))


class UserDB:
    TABLE_NAME = "users"

    @staticmethod
    def _is_supabase_available() -> bool:
        from app.core.config import settings
        return bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)

    @staticmethod
    async def get_by_email_estricto(email: str) -> Optional[dict]:
        """Lee un usuario por correo; los errores de la BD se PROPAGAN (CHG-020, INV-039): un fallo de lectura no se
        confunde con «la cuenta no existe». Devuelve None solo si de verdad no hay usuario (o no hay Supabase, modo
        demo). Las rutas de autenticación lo usan para responder 503 en vez de 401/200 ante un fallo.

        I-3: la consulta (síncrona) corre en el ejecutor propio del estado de autenticación y con su cliente DEDICADO
        (plazo real de 4 s, sin reintentos), dentro del presupuesto de 5 s de la petición: una tabla de usuarios lenta
        da `EstadoNoDisponible` (503) a tiempo y no bloquea el event loop. Cualquier fallo se convierte en
        `EstadoNoDisponible` (sin datos personales en el mensaje)."""
        if not UserDB._is_supabase_available():
            return None
        correo = email.lower()

        def leer() -> Optional[dict]:
            result = auth_estado.cliente_estado().table(UserDB.TABLE_NAME)\
                .select("*")\
                .eq("email", correo)\
                .limit(1)\
                .execute()
            return _map_user(result.data[0]) if result.data else None

        return await auth_estado.ejecutar("leer_usuario", leer)

    @staticmethod
    async def get_by_id(user_id: str) -> Optional[dict]:
        if not UserDB._is_supabase_available():
            return None
        try:
            client = SupabaseDB.get_client()
            result = client.table(UserDB.TABLE_NAME)\
                .select("*")\
                .eq("id", user_id)\
                .limit(1)\
                .execute()
            return _map_user(result.data[0]) if result.data else None
        except Exception as e:
            print(f"[UserDB.get_by_id] {e}")
            return None

    @staticmethod
    async def create(email: str, password: str, full_name: str = "", is_active: bool = False, currency: str = "USD") -> dict:
        if not UserDB._is_supabase_available():
            raise RuntimeError("Supabase not configured")
        client = SupabaseDB.get_client()
        row = {
            "id": str(uuid.uuid4()),
            "email": email.lower(),
            "full_name": full_name,
            "hashed_password": await _hash_fuera_del_loop(password),
            "currency": currency,
            "is_active": is_active,
        }
        result = client.table(UserDB.TABLE_NAME).insert(row).execute()
        return _map_user(result.data[0])

    @staticmethod
    async def activate(email: str) -> bool:
        if not UserDB._is_supabase_available():
            return False
        try:
            client = SupabaseDB.get_client()
            client.table(UserDB.TABLE_NAME)\
                .update({"is_active": True})\
                .eq("email", email.lower())\
                .execute()
            return True
        except Exception as e:
            print(f"[UserDB.activate] {e}")
            return False

    @staticmethod
    async def update_password(email: str, new_password: str) -> int:
        """Actualiza la contraseña (y activa la cuenta: el código prueba que el correo es suyo).

        También sube la versión de sesión del usuario: así todos los tokens emitidos
        antes del cambio dejan de servir (INV-016). Devuelve la versión nueva (0 si el correo
        no existe o no hay Supabase). Los errores de Supabase se propagan.
        """
        if not UserDB._is_supabase_available():
            return 0
        client = SupabaseDB.get_client()
        nuevo_hash = await _hash_fuera_del_loop(new_password)
        # Actualización condicional (compare-and-set): solo escribe si la versión sigue
        # siendo la que se leyó. Si otro cambio se adelantó, se vuelve a leer y reintenta;
        # así cada restablecimiento sube la versión al menos una vez.
        for _ in range(5):
            actual = (
                client.table(UserDB.TABLE_NAME)
                .select("session_version")
                .eq("email", email.lower())
                .limit(1)
                .execute()
            )
            if not actual.data:
                return 0
            version = int(actual.data[0].get("session_version") or 0)
            result = (
                client.table(UserDB.TABLE_NAME)
                .update({
                    "hashed_password": nuevo_hash,
                    "is_active": True,
                    "session_version": version + 1,
                })
                .eq("email", email.lower())
                .eq("session_version", version)
                .execute()
            )
            if result.data:
                return version + 1  # versión de sesión nueva (≥ 1, verdadera para quien solo pregunta si cambió)
        raise RuntimeError("No se pudo actualizar la contraseña: la versión de sesión cambió varias veces seguidas")

    @staticmethod
    async def get_session_version(user_id: str) -> Optional[int]:
        """Versión de sesión vigente del usuario (INV-016).

        Devuelve None si el usuario ya no existe, si su cuenta no está activa (INV-017) o si está suspendida (INV-056,
        CHG-023; la columna `suspendida` se lee en la MISMA consulta): un token de una cuenta desactivada deja de servir. Sin Supabase (modo demo local)
        devuelve 0. Los errores de Supabase se propagan: quien llama decide
        responder 503 en vez de cerrar la sesión por un fallo pasajero.
        """
        if not UserDB._is_supabase_available():
            return 0
        client = SupabaseDB.get_client()
        result = (
            client.table(UserDB.TABLE_NAME)
            .select("session_version,is_active,suspendida")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        if not result.data or not result.data[0].get("is_active") or result.data[0].get("suspendida"):
            return None
        return int(result.data[0].get("session_version") or 0)

    @staticmethod
    async def registrar_acceso(user_id: str) -> bool:
        """Último inicio de sesión (INV-061, CHG-023). MEJOR ESFUERZO y NUNCA lanza: se programa con `BackgroundTasks`, así
        que corre tras responder el login. Una sola sentencia condicional de la BD (`registrar_acceso`, como mucho una
        escritura por hora y usuario, con el reloj de la BD), fuera del event loop, con plazo PROPIO de 2 s. Un fallo, un
        plazo vencido o una respuesta rara solo dejan un aviso sin datos personales. Devuelve si escribió."""
        if not UserDB._is_supabase_available():
            return False
        # Límite PROPIO (ADR-012): sin hueco se OMITE el guardado, sin esperar ni afectar al login ni a los 8 hilos de auth.
        if not _huecos_acceso.acquire(blocking=False):
            _avisar_omision_acceso()
            return False
        try:
            futuro = _ejecutor_acceso.submit(
                lambda: auth_estado.cliente_estado().rpc("registrar_acceso", {"p_id": user_id}).execute().data)
        except BaseException:
            _huecos_acceso.release()
            return False
        futuro.add_done_callback(lambda _f: _huecos_acceso.release())   # se libera al terminar el HILO (aunque venza el plazo)
        try:
            dato = await asyncio.wait_for(asyncio.wrap_future(futuro), timeout=PLAZO_REGISTRAR_ACCESO_SEG)
            return dato is True
        except Exception as e:   # el mensaje puede traer datos: solo el tipo (cancelación no se captura: se propaga)
            print(f"[user] Aviso: no se pudo registrar el último acceso ({type(e).__name__})")
            return False

    @staticmethod
    async def delete_by_id(user_id: str) -> bool:
        if not UserDB._is_supabase_available():
            return False
        try:
            client = SupabaseDB.get_client()
            client.table(UserDB.TABLE_NAME)\
                .delete()\
                .eq("id", user_id)\
                .execute()
            return True
        except Exception as e:
            print(f"[UserDB.delete_by_id] {e}")
            return False

    @staticmethod
    async def update_currency(user_id: str, currency: str) -> bool:
        """Update user currency preference"""
        if not UserDB._is_supabase_available():
            return False
        try:
            client = SupabaseDB.get_client()
            result = client.table(UserDB.TABLE_NAME)\
                .update({"currency": currency})\
                .eq("id", user_id)\
                .execute()
            # Sin filas actualizadas no hubo cambio: no se informa un éxito falso
            return bool(result.data)
        except Exception as e:
            # Los errores de Supabase se propagan; la ruta responde 503
            print(f"[UserDB.update_currency] {e}")
            raise

    @staticmethod
    async def update_full_name(user_id: str, full_name: str) -> bool:
        """Cambia el nombre visible. Los errores de Supabase se propagan (la ruta responde 503)."""
        if not UserDB._is_supabase_available():
            return False
        client = SupabaseDB.get_client()
        result = client.table(UserDB.TABLE_NAME)\
            .update({"full_name": full_name})\
            .eq("id", user_id)\
            .execute()
        return bool(result.data)

    @staticmethod
    async def delete_unverified_expired() -> int:
        """Delete inactive users whose registration is older than 1 hour.
        Returns the number of deleted records."""
        if not UserDB._is_supabase_available():
            return 0
        try:
            from datetime import datetime, timezone, timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            client = SupabaseDB.get_client()
            result = client.table(UserDB.TABLE_NAME)\
                .delete()\
                .eq("is_active", False)\
                .lt("created_at", cutoff)\
                .execute()
            deleted = len(result.data) if result.data else 0
            if deleted:
                print(f"🧹 [cleanup] Eliminados {deleted} usuario(s) sin verificar (>1 hora)")
            return deleted
        except Exception as e:
            print(f"[UserDB.delete_unverified_expired] {e}")
            return 0
