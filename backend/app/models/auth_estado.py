"""
Estado de autenticación persistente (CHG-020, ADR-010, INV-037 a INV-041).

Bloqueos de login, códigos de verificación/restablecimiento y ventanas de límites viven en PostgreSQL, en las tablas y
funciones de `backend/sql/2026-11-24_auth_persistente.sql` (todas con el reloj `now()` de la BD; este módulo NUNCA envía
la hora, el parámetro `p_ahora` es solo de las pruebas SQL).

Reglas que este módulo hace cumplir:
- Privacidad (INV-040): el correo y la IP llegan a la BD solo como huella HMAC-SHA256 con una clave derivada de
  `SECRET_KEY`; los códigos, solo como HMAC. Nada de eso se imprime jamás (ni correos, ni IP, ni códigos, ni el mensaje
  del servidor): los avisos llevan solo el nombre de la operación y el tipo de error.
- Fail-closed (INV-039): cualquier fallo, plazo vencido, respuesta inesperada o ejecutor lleno lanza
  `EstadoNoDisponible`, que las rutas convierten en 503. Nunca se «deja pasar» ni se cae a memoria con Supabase.
- Plazo real (I-10): cliente de Supabase DEDICADO con plazo de 4 s en el cliente HTTP (`postgrest_client_timeout`, sin
  reintentos), presupuesto de 5 s por petición y ejecutor propio de 8 hilos (503 sin encolar si no hay hilo libre).
- Modo demo (INV-041): sin Supabase y fuera de producción se usa un almacén en memoria con la MISMA semántica que las
  funciones SQL; en producción sin Supabase, `EstadoNoDisponible`.
"""
import asyncio
import contextvars
import hashlib
import hmac
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from app.core.config import settings

MENSAJE_503 = "Servicio no disponible. Intenta de nuevo en unos minutos."

# ── Números (INV-007, INV-010; no cambian) ────────────────────────────────────
MAX_FALLOS_LOGIN = 5
VENTANA_LOGIN_SEG = 86400          # la serie caduca a las 24 h del primer fallo
BLOQUEO_LOGIN_SEG = 900            # 15 min desde el 5.º fallo
MAX_INTENTOS_CODIGO = 5
VIGENCIA_CODIGO_SEG = 600          # 10 min
ESPACIO_CODIGO_SEG = 60
LIMITE_DESTINATARIO = 10           # correos/día por destinatario
LIMITE_GLOBAL = 250                # correos/día en total
VENTANA_ENVIO_SEG = 86400
TOPE_FILAS_EVENTOS = 500_000       # filas VIGENTES (dentro de la retención de 2 días); las vencidas no cuentan (B-1).
                                   # Con el 90 % (450 000) auth_limite_registrar libera un lote de 5 000 vencidas
LOTE_PURGA_LIMITE = 5_000
LOTE_PURGA = 10_000                # filas por tabla y por llamada a auth_purgar (por lotes, I-4)
RESERVA_CADUCA_SEG = 10            # una reserva sin resolver tras 10 s ya no está «en vuelo» (I-1; la petición dura ≤ 5 s)
INTERVALO_INTENTO_PURGA_SEG = 3600 # cada proceso intenta la purga en segundo plano como mucho una vez por hora
RETENCION_EVENTOS_SEG = 2 * 86400
RETENCION_ESTADO_SEG = 30 * 86400
INTERVALO_PURGA_SEG = 86400

PROPOSITOS = ("verify", "reset")

# ── Plazos (I-10) ─────────────────────────────────────────────────────────────
PLAZO_LLAMADA_SEG = 4.0            # por llamada, impuesto en el cliente HTTP
PRESUPUESTO_PETICION_SEG = 5.0     # total por petición
MAX_HILOS = 8


class EstadoNoDisponible(Exception):
    """La BD de estado de autenticación no puede responder a tiempo o correctamente (503, fail-closed).
    Su texto nunca lleva datos personales."""


# ── Huellas HMAC (INV-040) ────────────────────────────────────────────────────

def _clave_hmac() -> bytes:
    return hashlib.sha256(("finanzy-auth-estado:" + settings.SECRET_KEY).encode("utf-8")).digest()


def _hmac_hex(mensaje: str) -> str:
    return hmac.new(_clave_hmac(), mensaje.encode("utf-8"), hashlib.sha256).hexdigest()


def normalizar_correo(correo: str) -> str:
    return (correo or "").strip().lower()


def huella(tipo: str, valor: str) -> str:
    """HMAC-SHA256(k, tipo + ":" + valor) en hexadecimal (64 caracteres). El valor ya viene normalizado."""
    return _hmac_hex(f"{tipo}:{valor}")


def huella_correo(correo: str) -> str:
    return huella("correo", normalizar_correo(correo))


def huella_ip(ip: str) -> str:
    return huella("ip", ip)


def hmac_codigo(proposito: str, correo: str, codigo: str) -> str:
    """HMAC del código: nunca se guarda ni se registra el código en claro."""
    return _hmac_hex(f"codigo:{proposito}:{huella_correo(correo)}:{codigo}")


# ── Reloj del modo demo (la BD usa su propio now()) ───────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# ── Selección de modo ─────────────────────────────────────────────────────────

def _supabase_ok() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_KEY)


def _modo() -> str:
    """'bd' con Supabase configurado; 'memoria' solo sin Supabase y fuera de producción; si no, 503 (INV-041)."""
    if _supabase_ok():
        return "bd"
    if settings.es_produccion:
        raise EstadoNoDisponible("sin Supabase en producción")
    return "memoria"


# ── Cliente dedicado, presupuesto y ejecutor propio ───────────────────────────
_cliente_estado = None
_cliente_lock = threading.Lock()


def _crear_cliente():
    """Cliente de Supabase solo para el estado de autenticación, con plazo REAL de 4 s en el cliente HTTP y sin
    reintentos (con reintentos el plazo se multiplicaría)."""
    from supabase import create_client, ClientOptions
    opciones = ClientOptions(
        postgrest_client_timeout=PLAZO_LLAMADA_SEG,
        postgrest_client_retry=False,
        auto_refresh_token=False,
        persist_session=False,
    )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY, opciones)


def _cliente():
    global _cliente_estado
    if _cliente_estado is None:
        with _cliente_lock:
            if _cliente_estado is None:
                _cliente_estado = _crear_cliente()
    return _cliente_estado


_ranuras = threading.BoundedSemaphore(MAX_HILOS)   # una por hilo; se libera cuando el HILO termina, no al vencer el plazo
_ejecutor = ThreadPoolExecutor(max_workers=MAX_HILOS, thread_name_prefix="auth-estado")
_fin_peticion: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar("auth_estado_fin", default=None)


def iniciar_presupuesto(segundos: float = PRESUPUESTO_PETICION_SEG) -> None:
    """Fija el presupuesto total (reloj monotónico) de la petición en curso. Las rutas lo llaman al empezar."""
    _fin_peticion.set(time.monotonic() + segundos)


def _restante() -> float:
    fin = _fin_peticion.get()
    if fin is None:
        return PRESUPUESTO_PETICION_SEG
    return fin - time.monotonic()


async def _ejecutar(operacion: str, fn: Callable[[], Any]) -> Any:
    """Corre `fn` (bloqueante) en el ejecutor propio. Sin hilo libre o sin presupuesto: EstadoNoDisponible sin encolar."""
    restante = _restante()
    if restante <= 0:
        raise EstadoNoDisponible("presupuesto agotado")
    if not _ranuras.acquire(blocking=False):
        print(f"[auth_estado] Aviso: ejecutor lleno ({operacion})")
        raise EstadoNoDisponible("ejecutor lleno")
    try:
        futuro = _ejecutor.submit(fn)
    except Exception:
        _ranuras.release()
        raise EstadoNoDisponible("no se pudo ejecutar")
    futuro.add_done_callback(lambda _f: _ranuras.release())
    try:
        return await asyncio.wait_for(asyncio.wrap_future(futuro), timeout=min(PLAZO_LLAMADA_SEG, restante))
    except asyncio.TimeoutError:
        print(f"[auth_estado] Aviso: plazo vencido ({operacion})")
        raise EstadoNoDisponible("plazo vencido")
    except EstadoNoDisponible:
        raise
    except Exception as e:   # el mensaje del servidor puede traer datos: solo el tipo
        print(f"[auth_estado] Aviso: falló {operacion} ({type(e).__name__})")
        raise EstadoNoDisponible("falló la BD de estado")


async def ejecutar(operacion: str, fn: Callable[[], Any]) -> Any:
    """Para otras lecturas de las rutas de autenticación (p. ej. la tabla de usuarios, I-3): mismo ejecutor propio,
    mismo presupuesto de 5 s por petición y mismo 503 (`EstadoNoDisponible`) sin bloquear el event loop."""
    return await _ejecutar(operacion, fn)


def cliente_estado():
    """Cliente DEDICADO (plazo real de 4 s, sin reintentos) para usar dentro de `ejecutar`."""
    return _cliente()


def _rpc(nombre: str, args: dict) -> Any:
    """Llamada RPC bloqueante (se ejecuta en un hilo del ejecutor propio). Nunca envía `p_ahora`."""
    assert "p_ahora" not in args
    return _cliente().rpc(nombre, args).execute().data


def _texto(dato: Any, validos: tuple[str, ...]) -> str:
    if isinstance(dato, list) and len(dato) == 1:
        dato = dato[0]
    if not isinstance(dato, str) or dato not in validos:
        raise EstadoNoDisponible("respuesta inesperada")
    return dato


def _fecha(valor: Any) -> Optional[datetime]:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor
    try:
        f = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        raise EstadoNoDisponible("respuesta inesperada")
    return f if f.tzinfo else f.replace(tzinfo=timezone.utc)


# ── Almacén del modo demo (misma semántica que las funciones SQL) ─────────────

_intento_purga: dict[str, Optional[datetime]] = {"ultimo": None}   # último intento de purga en segundo plano (este proceso)


class _Memoria:
    """Solo existe sin Supabase y fuera de producción (INV-041). Se vacía en las pruebas."""
    lock = threading.RLock()
    intentos: dict[str, dict] = {}
    codigos: dict[tuple[str, str], dict] = {}
    eventos: dict[tuple[str, str], list[datetime]] = {}
    ultima_purga: Optional[datetime] = None

    @classmethod
    def limpiar(cls) -> None:
        with cls.lock:
            cls.intentos.clear()
            cls.codigos.clear()
            cls.eventos.clear()
            cls.ultima_purga = None
        _intento_purga["ultimo"] = None

    @classmethod
    def total_eventos(cls) -> int:
        return sum(len(v) for v in cls.eventos.values())


def _mem_borrar_eventos_vencidos(corte: datetime, tope: Optional[int]) -> int:
    """Borra eventos anteriores a `corte` (hasta `tope` filas, o todos si es None). Devuelve cuántos borró."""
    m, borrados = _Memoria, 0
    for k in list(m.eventos):
        if tope is not None and borrados >= tope:
            break
        vivos, quedan = [], (None if tope is None else tope - borrados)
        for t in m.eventos[k]:
            if t < corte and (quedan is None or quedan > 0):
                borrados += 1
                if quedan is not None:
                    quedan -= 1
            else:
                vivos.append(t)
        if vivos:
            m.eventos[k] = vivos
        else:
            del m.eventos[k]
    return borrados


def _mem_purgar(ahora: datetime, lote: Optional[int] = None) -> int:
    """Igual que `auth_purgar`: por lotes de `lote` filas por tabla; con trabajo pendiente la marca no se renueva."""
    m = _Memoria
    if m.ultima_purga is not None and m.ultima_purga > ahora - timedelta(seconds=INTERVALO_PURGA_SEG):
        return -1
    total, pendiente = 0, False
    n = _mem_borrar_eventos_vencidos(ahora - timedelta(seconds=RETENCION_EVENTOS_SEG), lote)
    total += n
    pendiente = pendiente or (lote is not None and n >= lote)
    corte = ahora - timedelta(seconds=RETENCION_ESTADO_SEG)
    vencidos = [k for k, f in m.intentos.items() if f["actualizado_en"] < corte][:lote]
    for k in vencidos:
        del m.intentos[k]
    total += len(vencidos)
    pendiente = pendiente or (lote is not None and len(vencidos) >= lote)
    vencidos = [k for k, c in m.codigos.items() if c["emitido_en"] < corte][:lote]
    for k in vencidos:
        del m.codigos[k]
    total += len(vencidos)
    pendiente = pendiente or (lote is not None and len(vencidos) >= lote)
    if not pendiente:
        m.ultima_purga = ahora
    return total


def _reserva_caducada(f: dict, ahora: datetime) -> bool:
    """I-1: la última reserva fue hace más de 10 s (o no consta): nada de lo que contó `en_vuelo` se resolverá ya."""
    ultima = f.get("ultima_reserva")
    return ultima is None or ultima < ahora - timedelta(seconds=RESERVA_CADUCA_SEG)


def _mem_reservar(clave: str) -> tuple[bool, Optional[datetime]]:
    m, ahora = _Memoria, _ahora()
    with m.lock:
        f = m.intentos.setdefault(clave, {"fallos": 0, "en_vuelo": 0, "ventana_inicio": ahora, "ultima_reserva": None,
                                          "bloqueado_hasta": None, "actualizado_en": ahora})
        if f["bloqueado_hasta"] is not None and f["bloqueado_hasta"] > ahora:
            return False, f["bloqueado_hasta"]
        if (f["bloqueado_hasta"] is not None or f["fallos"] == 0
                or f["ventana_inicio"] + timedelta(seconds=VENTANA_LOGIN_SEG) <= ahora):
            f.update(fallos=0, en_vuelo=0, ventana_inicio=ahora, bloqueado_hasta=None)
        if _reserva_caducada(f, ahora):
            f["en_vuelo"] = 0      # I-1: las reservas que nunca se resolvieron ya no están en vuelo
        f["fallos"] += 1
        f["en_vuelo"] += 1
        if f["fallos"] >= MAX_FALLOS_LOGIN:
            f["bloqueado_hasta"] = ahora + timedelta(seconds=BLOQUEO_LOGIN_SEG)
        f["actualizado_en"] = ahora
        f["ultima_reserva"] = ahora
        return True, f["bloqueado_hasta"]


def _mem_resolver(clave: str, acierto: bool) -> None:
    m = _Memoria
    with m.lock:
        f = m.intentos.get(clave)
        if f is None:
            return
        if _reserva_caducada(f, _ahora()):
            f["en_vuelo"] = 0
        f["en_vuelo"] = max(f["en_vuelo"] - 1, 0)
        if acierto:
            f["fallos"] = max(f["fallos"] - 1, 0)
            if f["fallos"] < MAX_FALLOS_LOGIN:
                f["bloqueado_hasta"] = None
            if f["en_vuelo"] == 0:
                del m.intentos[clave]
                return
        f["actualizado_en"] = _ahora()


def _mem_emitir(clave: str, proposito: str, codigo_hmac: str, espacio_seg: int, limite_destinatario: int,
                limite_global: int) -> str:
    m, ahora = _Memoria, _ahora()
    with m.lock:     # sin purgar: la purga es una llamada aparte (I-4)
        ev_correo = m.eventos.get((clave, "correo"), [])
        if espacio_seg > 0 and any(t > ahora - timedelta(seconds=espacio_seg) for t in ev_correo):
            return "reciente"
        corte = ahora - timedelta(seconds=VENTANA_ENVIO_SEG)
        if sum(1 for t in ev_correo if t > corte) >= limite_destinatario:
            return "limitado"
        if sum(1 for t in m.eventos.get(("global", "global"), []) if t > corte) >= limite_global:
            return "limitado"
        m.eventos.setdefault((clave, "correo"), []).append(ahora)
        m.eventos.setdefault(("global", "global"), []).append(ahora)
        m.codigos[(clave, proposito)] = {"codigo_hmac": codigo_hmac, "emitido_en": ahora,
                                         "expira_en": ahora + timedelta(seconds=VIGENCIA_CODIGO_SEG), "intentos": 0}
        return "enviado"


def _mem_verificar(clave: str, proposito: str, codigo_hmac: str) -> str:
    m, ahora = _Memoria, _ahora()
    with m.lock:
        c = m.codigos.get((clave, proposito))
        if c is None:
            return "invalido"
        if c["expira_en"] <= ahora:
            del m.codigos[(clave, proposito)]
            return "invalido"
        if c["intentos"] >= MAX_INTENTOS_CODIGO:
            return "invalido"
        if hmac.compare_digest(c["codigo_hmac"], codigo_hmac):
            del m.codigos[(clave, proposito)]
            return "ok"
        c["intentos"] += 1
        return "incorrecto"


def _mem_limite(clave: str, tipo: str, limite: int, ventana_seg: int) -> str:
    """Igual que `auth_limite_registrar`: el tope cuenta solo filas VIGENTES (dentro de 2 días, B-1) y cerca del tope
    se libera un lote de las vencidas."""
    m, ahora = _Memoria, _ahora()
    with m.lock:
        eventos = m.eventos.get((clave, tipo), [])
        if sum(1 for t in eventos if t > ahora - timedelta(seconds=ventana_seg)) >= limite:
            return "limitado"
        corte = ahora - timedelta(seconds=RETENCION_EVENTOS_SEG)
        vigentes = sum(1 for lista in m.eventos.values() for t in lista if t >= corte)
        if vigentes >= int(TOPE_FILAS_EVENTOS * 0.9):
            _mem_borrar_eventos_vencidos(corte, LOTE_PURGA_LIMITE)
        if vigentes > TOPE_FILAS_EVENTOS:
            return "lleno"
        m.eventos.setdefault((clave, tipo), []).append(ahora)
        return "ok"


def _mem_borrar(clave: str) -> int:
    m = _Memoria
    with m.lock:
        total = 1 if m.intentos.pop(clave, None) is not None else 0
        for k in [k for k in m.codigos if k[0] == clave]:
            del m.codigos[k]
            total += 1
        return total


# ── API pública (asíncrona; nunca bloquea el event loop con la red) ───────────

async def login_reservar(correo: str) -> tuple[bool, Optional[datetime]]:
    """Cuenta el intento ANTES de comprobar la contraseña (INV-038). Devuelve (permitido, bloqueado_hasta)."""
    clave = huella_correo(correo)
    if _modo() == "memoria":
        return _mem_reservar(clave)
    dato = await _ejecutar("login_reservar", lambda: _rpc("auth_login_reservar", {
        "p_clave": clave, "p_max": MAX_FALLOS_LOGIN,
        "p_ventana_seg": VENTANA_LOGIN_SEG, "p_bloqueo_seg": BLOQUEO_LOGIN_SEG}))
    fila = dato[0] if isinstance(dato, list) and len(dato) == 1 else dato
    if not isinstance(fila, dict) or not isinstance(fila.get("permitido"), bool):
        raise EstadoNoDisponible("respuesta inesperada")
    return fila["permitido"], _fecha(fila.get("bloqueado_hasta"))


async def login_resolver(correo: str, acierto: bool) -> None:
    """Cierra la reserva: si acertó devuelve el intento y borra la serie solo sin reservas en vuelo."""
    clave = huella_correo(correo)
    if _modo() == "memoria":
        _mem_resolver(clave, bool(acierto))
        return
    await _ejecutar("login_resolver", lambda: _rpc("auth_login_resolver", {
        "p_clave": clave, "p_acierto": bool(acierto), "p_max": MAX_FALLOS_LOGIN}))


async def login_reiniciar(correo: str) -> None:
    """Borra la serie sin condiciones (restablecimiento y cambio de contraseña con éxito)."""
    clave = huella_correo(correo)
    if _modo() == "memoria":
        with _Memoria.lock:
            _Memoria.intentos.pop(clave, None)
        return
    await _ejecutar("login_reiniciar", lambda: _rpc("auth_login_reiniciar", {"p_clave": clave}))


async def codigo_emitir(correo: str, proposito: str, codigo: str, *, espacio_seg: int = ESPACIO_CODIGO_SEG,
                        limite_destinatario: int = LIMITE_DESTINATARIO, limite_global: int = LIMITE_GLOBAL) -> str:
    """Una sola operación atómica: 60 s, topes y guardado del HMAC del código. 'enviado' | 'reciente' | 'limitado'.
    Para un señuelo, `codigo` es `security.codigo_senuelo()`."""
    if proposito not in PROPOSITOS:
        raise ValueError("propósito inválido")
    clave, h = huella_correo(correo), hmac_codigo(proposito, correo, codigo)
    if _modo() == "memoria":
        return _mem_emitir(clave, proposito, h, espacio_seg, limite_destinatario, limite_global)
    dato = await _ejecutar("codigo_emitir", lambda: _rpc("auth_codigo_emitir", {
        "p_clave_correo": clave, "p_proposito": proposito, "p_codigo_hmac": h,
        "p_espacio_seg": espacio_seg, "p_limite_destinatario": limite_destinatario,
        "p_limite_global": limite_global, "p_ventana_seg": VENTANA_ENVIO_SEG,
        "p_vigencia_seg": VIGENCIA_CODIGO_SEG}))
    return _texto(dato, ("enviado", "reciente", "limitado"))


async def codigo_verificar(correo: str, proposito: str, codigo: str) -> str:
    """'ok' (lo consume: un solo uso) | 'incorrecto' | 'invalido' (no existe, venció o agotó los 5 intentos)."""
    if proposito not in PROPOSITOS:
        raise ValueError("propósito inválido")
    clave, h = huella_correo(correo), hmac_codigo(proposito, correo, codigo)
    if _modo() == "memoria":
        return _mem_verificar(clave, proposito, h)
    dato = await _ejecutar("codigo_verificar", lambda: _rpc("auth_codigo_verificar", {
        "p_clave_correo": clave, "p_proposito": proposito, "p_codigo_hmac": h, "p_max": MAX_INTENTOS_CODIGO}))
    return _texto(dato, ("ok", "incorrecto", "invalido"))


async def limite_registrar(ip: str, tipo: str, limite: int, ventana_seg: int) -> str:
    """Ventana deslizante por IP (huella). 'ok' | 'limitado' | 'lleno' (tope de filas contra IP falsificadas)."""
    clave = huella_ip(ip)
    if _modo() == "memoria":
        return _mem_limite(clave, tipo, limite, ventana_seg)
    dato = await _ejecutar("limite_registrar", lambda: _rpc("auth_limite_registrar", {
        "p_clave": clave, "p_tipo": tipo, "p_limite": limite, "p_ventana_seg": ventana_seg}))
    return _texto(dato, ("ok", "limitado", "lleno"))


async def borrar_de_cuenta(correo: str) -> int:
    """Baja de cuenta: borra intentos y códigos del correo (no los eventos de límites). Devuelve filas borradas."""
    clave = huella_correo(correo)
    if _modo() == "memoria":
        return _mem_borrar(clave)
    dato = await _ejecutar("borrar_de_cuenta", lambda: _rpc("auth_borrar_de_cuenta", {"p_clave_correo": clave}))
    if type(dato) is not int:
        raise EstadoNoDisponible("respuesta inesperada")
    return dato


async def purgar() -> int:
    """Purga oportunista (como mucho una vez al día). Devuelve filas borradas o -1 si no tocaba."""
    if _modo() == "memoria":
        with _Memoria.lock:
            return _mem_purgar(_ahora())
    dato = await _ejecutar("purgar", lambda: _rpc("auth_purgar", {}))
    if type(dato) is not int:
        raise EstadoNoDisponible("respuesta inesperada")
    return dato


async def purgar_en_segundo_plano() -> None:
    """Purga oportunista FUERA de la emisión de códigos (I-4). Se programa como tarea de fondo tras responder: tiene su
    propio presupuesto, nunca lanza (un fallo solo deja un aviso sin datos) y cada proceso lo intenta como mucho una vez
    por hora (la BD además la limita a una vez al día entre todas las instancias)."""
    ahora = _ahora()
    ultimo = _intento_purga["ultimo"]
    if ultimo is not None and ultimo > ahora - timedelta(seconds=INTERVALO_INTENTO_PURGA_SEG):
        return
    _intento_purga["ultimo"] = ahora
    iniciar_presupuesto()
    try:
        await purgar()
    except EstadoNoDisponible:
        print("[auth_estado] Aviso: no se pudo purgar el estado de autenticación (se reintentará)")
    except Exception as e:
        print(f"[auth_estado] Aviso: falló la purga ({type(e).__name__})")
