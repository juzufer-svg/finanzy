"""CHG-020 (T3) · INV-037 a INV-041 y BDD-AUTH-PERSISTENTE: las RUTAS de autenticación con el estado persistente.

Un Supabase simulado PERSISTENTE (`BDFalsa`) hace de PostgreSQL: guarda bloqueos, códigos y eventos fuera del proceso
del backend, de modo que «reiniciar» el backend (`bd.reiniciar()`) no los borra, igual que un despliegue real. Sus
funciones imitan las funciones SQL `auth_*` reutilizando la semántica del almacén demo de `models/auth_estado.py`
(que T2 ya probó) y el reloj de la «BD» es el fixture `reloj`. La atomicidad REAL solo se prueba contra PostgreSQL:
`backend/sql/pruebas/07_comprobar_auth_persistente.sql` y el bloque de concurrencia de `probar.sh` (T1).

Para no pagar bcrypt (~0,3 s por comprobación) en cientos de intentos, estas pruebas sustituyen `verify_password` y
`get_password_hash` por versiones rápidas que CUENTAN las llamadas; el costo real del hash señuelo lo prueba
`test_auth_estado.py::test_inv009_hash_senuelo_tiene_el_mismo_costo_que_un_hash_real`.
"""
import asyncio
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.api.routes import auth as auth_routes
from app.core import security
from app.core.config import settings
from app.main import app
from app.models import auth_estado as ae
from app.models.user import UserDB
from app.models.whatsapp import WhatsappDB
from conftest import ip

ANA = "ana@example.com"
CLAVE = "Clave12345"
MSG_BLOQUEO = "Demasiados intentos fallidos. Intenta de nuevo en 15 minutos."
MSG_IP = "Demasiadas solicitudes. Espera unos minutos e intenta de nuevo."
MSG_TOPE = "Ya enviamos varios códigos a este correo hoy. Revisa tu bandeja (y spam) o intenta mañana."


# ───────────────────────── Supabase simulado persistente ─────────────────────────

_SWAP = threading.Lock()


def _nuevo_almacen():
    """Un almacén independiente de `ae._Memoria` (que debe seguir VACÍO con Supabase configurado, INV-041)."""
    return type("AlmacenBD", (ae._Memoria,), {"lock": threading.RLock(), "intentos": {}, "codigos": {},
                                              "eventos": {}, "ultima_purga": None})


class _Ejecucion:
    def __init__(self, bd, nombre, args):
        self.bd, self.nombre, self.args = bd, nombre, args

    def execute(self):
        return type("R", (), {"data": self.bd.ejecutar(self.nombre, self.args)})()


class BDFalsa:
    """Imita las funciones SQL `auth_*`; guarda lo que reciben para comprobar qué viaja a la BD."""

    def __init__(self):
        self.almacen = _nuevo_almacen()
        self.llamadas: list[tuple[str, dict]] = []
        self.falla: Exception | None = None            # falla todas las llamadas
        self.falla_en: dict[str, Exception] = {}       # falla solo algunas funciones
        self.espera = 0.0
        self.espera_usuarios = 0.0                     # lentitud de la tabla de usuarios (I-3)
        self.filas_usuarios: list[dict] = []
        self.hilos_usuarios: list[str] = []

    def table(self, _nombre):
        """Tabla de usuarios del cliente dedicado (`UserDB.get_by_email_estricto`, I-3): encadenable y con lentitud."""
        bd = self

        class Consulta:
            def __getattr__(self, _):
                return lambda *a, **k: self

            def execute(self):
                bd.hilos_usuarios.append(threading.current_thread().name)
                time.sleep(bd.espera_usuarios)
                return type("R", (), {"data": bd.filas_usuarios})()
        return Consulta()

    @property
    def nombres(self) -> list[str]:
        return [n for n, _ in self.llamadas]

    def rpc(self, nombre, args):
        return _Ejecucion(self, nombre, args)

    def reiniciar(self):
        """Simula un despliegue/reinicio del backend: nueva instancia, SIN memoria del proceso; la BD persiste."""
        ae._Memoria.limpiar()
        ae._cliente_estado = None

    def ejecutar(self, nombre, a):
        self.llamadas.append((nombre, dict(a)))
        if self.espera:
            time.sleep(self.espera)
        if self.falla is not None:
            raise self.falla
        if nombre in self.falla_en:
            raise self.falla_en[nombre]
        with _SWAP:    # las funciones `_mem_*` usan el almacén global: se les presta el de la «BD» solo durante la llamada
            original, ae._Memoria = ae._Memoria, self.almacen
            try:
                return self._despachar(nombre, a)
            finally:
                ae._Memoria = original

    @staticmethod
    def _despachar(n, a):
        if n == "auth_login_reservar":
            permitido, hasta = ae._mem_reservar(a["p_clave"])
            return [{"permitido": permitido, "bloqueado_hasta": hasta.isoformat() if hasta else None}]
        if n == "auth_login_resolver":
            return ae._mem_resolver(a["p_clave"], a["p_acierto"])
        if n == "auth_login_reiniciar":
            ae._Memoria.intentos.pop(a["p_clave"], None)
            return None
        if n == "auth_codigo_emitir":
            return ae._mem_emitir(a["p_clave_correo"], a["p_proposito"], a["p_codigo_hmac"], a["p_espacio_seg"],
                                  a["p_limite_destinatario"], a["p_limite_global"])
        if n == "auth_codigo_verificar":
            return ae._mem_verificar(a["p_clave_correo"], a["p_proposito"], a["p_codigo_hmac"])
        if n == "auth_limite_registrar":
            return ae._mem_limite(a["p_clave"], a["p_tipo"], a["p_limite"], a["p_ventana_seg"])
        if n == "auth_borrar_de_cuenta":
            return ae._mem_borrar(a["p_clave_correo"])
        if n == "auth_purgar":
            return ae._mem_purgar(ae._ahora())
        if n == "registrar_acceso":   # CHG-023, INV-061: el último acceso se escribe en segundo plano tras responder el login
            return True
        raise AssertionError(f"función SQL desconocida: {n}")


@pytest.fixture
def bd(monkeypatch, reloj):
    """Configura Supabase y le conecta la BD simulada persistente. El WhatsApp real no se toca."""
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "k")
    falsa = BDFalsa()
    monkeypatch.setattr(ae, "_cliente", lambda: falsa)
    # La purga en segundo plano (I-4) se prueba aparte: aquí se da por «ya intentada» para que no aparezca entre las
    # llamadas a la BD que cuentan las demás pruebas (y que deben ser idénticas exista o no la cuenta)
    ae._intento_purga["ultimo"] = reloj.t

    async def desenlazar(_user_id):
        return True
    monkeypatch.setattr(WhatsappDB, "desenlazar", staticmethod(desenlazar))
    return falsa


@pytest.fixture(autouse=True)
def bcrypt_contado(monkeypatch):
    """verify_password rápido y contado: la lista tiene el hash contra el que se comprobó en cada llamada."""
    comprobados: list[str] = []

    def verify(plain, hashed):
        comprobados.append(hashed)
        return bool(hashed) and hashed == "hash:" + plain
    for modulo in (security, auth_routes):      # users.py comprueba vía auth_routes.comprobar_contrasena (I-6)
        monkeypatch.setattr(modulo, "verify_password", verify)
    monkeypatch.setattr(security, "get_password_hash", lambda p: "hash:" + p)
    return comprobados


@pytest.fixture
def ejecutor_amplio(monkeypatch):
    """Para las pruebas de paralelismo: el ejecutor real de 8 hilos respondería 503 a ráfagas de 50 (INV-039); aquí se
    quiere probar la atomicidad del estado, no el ejecutor (que tiene sus propias pruebas)."""
    pool = ThreadPoolExecutor(max_workers=64)
    monkeypatch.setattr(ae, "_ranuras", threading.BoundedSemaphore(64))
    monkeypatch.setattr(ae, "_ejecutor", pool)
    yield
    pool.shutdown(wait=True)


# ───────────────────────── Ayudas ─────────────────────────

def _alta(users, correo=ANA, clave=CLAVE, activa=True):
    users[correo] = {"id": f"id-{correo}", "email": correo, "full_name": "Ana", "hashed_password": "hash:" + clave,
                     "is_active": activa, "currency": "USD", "session_version": 0}
    return users[correo]


def _login(client, correo=ANA, clave=CLAVE, n=1):
    return client.post("/api/v1/auth/login", json={"email": correo, "password": clave}, headers=ip(n))


def _post(client, ruta, cuerpo, n=1):
    return client.post(f"/api/v1/auth/{ruta}", json=cuerpo, headers=ip(n))


def _en_paralelo(peticiones):
    """Lanza las peticiones [(ruta, json, headers)] a la vez en UN event loop y devuelve las respuestas."""
    async def principal():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba") as c:
            return await asyncio.gather(*[c.post(r, json=j, headers=h) for r, j, h in peticiones])
    return asyncio.run(principal())


def _eventos(bd, clave, tipo, cantidad, ahora, hace=timedelta(hours=1)):
    bd.almacen.eventos[(clave, tipo)] = [ahora - hace] * cantidad


def _sesion(user_id):
    return {"Authorization": "Bearer " + security.create_access_token({"sub": user_id, "sv": 0})}


def _huella_en_bd(bd, correo=ANA):
    return bd.almacen.intentos.get(ae.huella_correo(correo))


# ───────────────────────── INV-037: sobrevive a reinicios ─────────────────────────

def test_inv037_bloqueo_de_login_sobrevive_a_un_reinicio(client, users, bd, reloj):
    _alta(users)
    assert [_login(client, clave="mala", n=i).status_code for i in range(1, 6)] == [401] * 5
    r = _login(client, n=9)
    assert r.status_code == 429 and r.json()["detail"] == MSG_BLOQUEO
    bd.reiniciar()                                           # despliegue: se pierde todo lo que había en memoria
    r = _login(client, n=10)                                 # con la contraseña CORRECTA
    assert r.status_code == 429 and r.json()["detail"] == MSG_BLOQUEO
    reloj.avanzar(minutes=14, seconds=59)
    assert _login(client, n=11).status_code == 429
    reloj.avanzar(seconds=2)                                 # pasaron los 15 minutos desde el 5.º fallo
    assert _login(client, n=12).status_code == 200


def test_inv037_codigo_vigente_sobrevive_a_un_reinicio(client, users, bd, sent_emails, reloj):
    assert client.post("/api/v1/auth/register", json={"email": ANA, "full_name": "Ana", "password": CLAVE},
                       headers=ip(1)).status_code == 201
    codigo = sent_emails[0][1]
    reloj.avanzar(minutes=2)
    bd.reiniciar()
    r = _post(client, "verify-email", {"email": ANA, "code": codigo}, 2)
    assert r.status_code == 200 and "access_token" in r.json() and users[ANA]["is_active"] is True
    assert _post(client, "verify-email", {"email": ANA, "code": codigo}, 3).status_code == 400   # ya usado


def test_inv037_ventanas_de_envio_sobreviven_a_un_reinicio(client, users, bd, sent_emails, reloj):
    # 10 pedidos de código por IP/hora
    assert [_post(client, "forgot-password", {"email": f"x{i}@example.com"}, 50).status_code for i in range(10)] == [200] * 10
    bd.reiniciar()
    assert _post(client, "forgot-password", {"email": "x11@example.com"}, 50).status_code == 429
    # 30 intentos por IP / 10 min
    assert [_login(client, f"u{i}@example.com", "x", 51).status_code for i in range(30)] == [401] * 30
    bd.reiniciar()
    r = _login(client, "u31@example.com", "x", 51)
    assert r.status_code == 429 and r.json()["detail"] == MSG_IP
    # 10 correos/día por destinatario
    _alta(users, "victima@example.com", activa=False)
    _eventos(bd, ae.huella_correo("victima@example.com"), "correo", 10, reloj.t)
    bd.reiniciar()
    r = _post(client, "resend-code", {"email": "victima@example.com"}, 52)
    assert r.status_code == 429 and r.json()["detail"] == MSG_TOPE
    # 250 correos/día en total
    _alta(users, "otra@example.com", activa=False)
    _eventos(bd, "global", "global", 250, reloj.t)
    bd.reiniciar()
    assert _post(client, "resend-code", {"email": "otra@example.com"}, 53).status_code == 429
    assert sent_emails == []


def test_inv037_las_ventanas_siguen_siendo_deslizantes_con_los_mismos_numeros(client, users, bd, sent_emails, reloj):
    # 5 fallos → 429 al sexto
    _alta(users)
    assert [_login(client, clave="mala", n=i).status_code for i in range(1, 7)] == [401] * 5 + [429]
    # 60 s entre códigos al mismo correo
    cuerpo = {"email": "nuevo@example.com", "full_name": "Nuevo", "password": CLAVE}
    assert client.post("/api/v1/auth/register", json=cuerpo, headers=ip(20)).status_code == 201
    reloj.avanzar(seconds=59)
    client.post("/api/v1/auth/register", json=cuerpo, headers=ip(21))
    assert len(sent_emails) == 1
    reloj.avanzar(seconds=2)
    client.post("/api/v1/auth/register", json=cuerpo, headers=ip(22))
    assert len(sent_emails) == 2
    # 10 correos/día por destinatario (el 11.º es 429) y la ventana se desliza: 24 h después vuelve a haber cupo
    _alta(users, "victima@example.com", activa=False)
    estados = []
    for i in range(11):
        reloj.avanzar(seconds=61)
        estados.append(_post(client, "resend-code", {"email": "victima@example.com"}, 30 + i).status_code)
    assert estados == [200] * 10 + [429]
    reloj.avanzar(hours=24)
    assert _post(client, "resend-code", {"email": "victima@example.com"}, 45).status_code == 200
    # 10 pedidos de código por IP/hora (deslizante)
    assert [_post(client, "forgot-password", {"email": f"p{i}@example.com"}, 60).status_code for i in range(11)] == [200] * 10 + [429]
    reloj.avanzar(hours=1, seconds=1)
    assert _post(client, "forgot-password", {"email": "p99@example.com"}, 60).status_code == 200
    # 250 correos/día en total: la emisión 250 pasa y la 251 no
    bd.almacen.eventos.clear()
    _eventos(bd, "global", "global", 249, reloj.t)
    _alta(users, "g1@example.com", activa=False)
    _alta(users, "g2@example.com", activa=False)
    assert _post(client, "resend-code", {"email": "g1@example.com"}, 70).status_code == 200
    assert _post(client, "resend-code", {"email": "g2@example.com"}, 71).status_code == 429
    # 30 intentos por IP / 10 min (deslizante)
    assert [_login(client, f"q{i}@example.com", "x", 80).status_code for i in range(31)] == [401] * 30 + [429]
    reloj.avanzar(minutes=10, seconds=1)
    assert _login(client, "q99@example.com", "x", 80).status_code == 401


def test_inv037_cinco_fallos_repartidos_en_menos_de_24_horas_bloquean(client, users, bd, reloj):
    _alta(users)
    reloj.t = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)
    for hora, n in ((8, 1), (12, 2), (16, 3), (20, 4)):
        reloj.t = reloj.t.replace(hour=hora)
        assert _login(client, clave="mala", n=n).status_code == 401
    reloj.t = reloj.t.replace(hour=23)
    assert _login(client, clave="mala", n=5).status_code == 401           # el quinto: bloquea desde ahora
    assert _login(client, n=6).status_code == 429
    reloj.avanzar(minutes=14)
    assert _login(client, n=7).status_code == 429
    reloj.avanzar(minutes=2)                                               # 15 min contados desde el 5.º intento
    assert _login(client, n=8).status_code == 200


def test_inv037_fallos_de_mas_de_24_horas_no_acumulan_con_uno_nuevo(client, users, bd, reloj):
    _alta(users)
    for n in range(1, 5):
        assert _login(client, clave="mala", n=n).status_code == 401
    reloj.avanzar(hours=24, minutes=1)
    assert _login(client, clave="mala", n=5).status_code == 401           # el «quinto» de hoy: no hay bloqueo
    assert _huella_en_bd(bd)["fallos"] == 1 and _huella_en_bd(bd)["bloqueado_hasta"] is None   # la serie empieza en 1
    assert _login(client, n=6).status_code == 200


# ───────────────────────── INV-038: atomicidad y concurrencia ─────────────────────────

def test_inv038_login_paralelo_no_comprueba_mas_de_5_contrasenas(users, bd, reloj, ejecutor_amplio, bcrypt_contado):
    _alta(users)
    respuestas = _en_paralelo([("/api/v1/auth/login", {"email": ANA, "password": "mala"}, ip(i + 1)) for i in range(50)])
    estados = sorted(r.status_code for r in respuestas)
    assert estados == [401] * 5 + [429] * 45                     # 50 IP distintas: ningún 429 puede venir del límite por IP
    assert {r.json()["detail"] for r in respuestas if r.status_code == 429} == {MSG_BLOQUEO}
    assert len(bcrypt_contado) == 5                              # como mucho 5 contraseñas comprobadas
    fila = _huella_en_bd(bd)
    assert fila["fallos"] == 5 and fila["en_vuelo"] == 0 and fila["bloqueado_hasta"] == reloj.t + timedelta(minutes=15)


def test_inv038_login_paralelo_desde_una_ip_distingue_el_429_por_ip_y_por_correo(users, bd, ejecutor_amplio):
    _alta(users)
    respuestas = _en_paralelo([("/api/v1/auth/login", {"email": ANA, "password": "mala"}, ip(9)) for _ in range(50)])
    cuenta = {}
    for r in respuestas:
        clave = (r.status_code, r.json()["detail"])
        cuenta[clave] = cuenta.get(clave, 0) + 1
    assert cuenta == {(401, "Credenciales inválidas"): 5, (429, MSG_BLOQUEO): 25, (429, MSG_IP): 20}


def test_inv038_la_quinta_reserva_que_acierta_inicia_sesion_y_no_deja_bloqueado(client, users, bd):
    _alta(users)
    for n in range(1, 5):
        assert _login(client, clave="mala", n=n).status_code == 401
    r = _login(client, n=5)                                      # la 5.ª reserva fija el bloqueo, acierta y lo levanta
    assert r.status_code == 200 and "access_token" in r.json()
    # sin reservas en vuelo la serie se borra: desbloqueo visible, la serie empieza de cero
    assert _huella_en_bd(bd) is None
    assert _login(client, n=6).status_code == 200
    # con otras reservas en vuelo (modelo): 4 fallos, SIN bloqueo, serie conservada
    bd.almacen.intentos.clear()

    async def escenario():
        for _ in range(3):
            await ae.login_reservar(ANA); await ae.login_resolver(ANA, False)
        assert (await ae.login_reservar(ANA))[0] is True         # 4.ª: sigue comprobándose
        permitido, hasta = await ae.login_reservar(ANA)          # 5.ª: fija el bloqueo
        assert permitido is True and hasta is not None
        await ae.login_resolver(ANA, True)                       # la 5.ª acierta
    asyncio.run(escenario())
    fila = _huella_en_bd(bd)
    assert fila["fallos"] == 4 and fila["bloqueado_hasta"] is None and fila["en_vuelo"] == 1


def test_inv038_devolver_el_intento_no_borra_los_fallos_en_vuelo(bd):
    async def escenario():
        for _ in range(3):
            assert (await ae.login_reservar(ANA))[0]             # 3 con contraseña incorrecta, todavía comprobándose
        assert (await ae.login_reservar(ANA))[0]                 # la cuarta, con la contraseña correcta
        await ae.login_resolver(ANA, True)
    asyncio.run(escenario())
    fila = _huella_en_bd(bd)
    assert fila is not None and fila["fallos"] == 3 and fila["en_vuelo"] == 3   # solo se le devolvió SU intento


def test_inv038_login_correcto_sin_reservas_en_vuelo_borra_la_serie(client, users, bd):
    _alta(users)
    for n in range(1, 4):
        assert _login(client, clave="mala", n=n).status_code == 401
    assert _huella_en_bd(bd)["fallos"] == 3 and _huella_en_bd(bd)["en_vuelo"] == 0
    assert _login(client, n=4).status_code == 200
    assert _huella_en_bd(bd) is None                             # el contador vuelve a 0


def test_inv038_codigo_paralelo_se_consume_una_sola_vez(client, users, bd, sent_emails, ejecutor_amplio):
    client.post("/api/v1/auth/register", json={"email": ANA, "full_name": "Ana", "password": CLAVE}, headers=ip(1))
    codigo = sent_emails[0][1]
    respuestas = _en_paralelo([("/api/v1/auth/verify-email", {"email": ANA, "code": codigo}, ip(i + 10)) for i in range(2)])
    assert sorted(r.status_code for r in respuestas) == [200, 400]
    assert [r.json()["detail"] for r in respuestas if r.status_code == 400] == ["Código inválido o expirado"]


def test_inv038_intentos_de_codigo_paralelos_no_pasan_de_5(client, users, bd, ejecutor_amplio):
    _alta(users, activa=False)
    asyncio.run(ae.codigo_emitir(ANA, "verify", "482913"))
    respuestas = _en_paralelo([("/api/v1/auth/verify-email", {"email": ANA, "code": f"{100000 + i}"}, ip(i + 1)) for i in range(40)])
    assert {r.status_code for r in respuestas} == {400}
    (fila,) = bd.almacen.codigos.values()
    assert fila["intentos"] == 5                                  # se evaluaron 5 y el resto se rechazó sin evaluar
    assert _en_paralelo([("/api/v1/auth/verify-email", {"email": ANA, "code": "482913"}, ip(100))])[0].status_code == 400
    assert users[ANA]["is_active"] is False                       # ni el valor correcto lo activa después (INV-007)


def test_inv038_limite_de_correos_paralelo_no_pasa_del_tope(users, bd, sent_emails, reloj, ejecutor_amplio):
    _alta(users, activa=False)
    _eventos(bd, ae.huella_correo(ANA), "correo", 9, reloj.t, hace=timedelta(hours=2))   # 9 hoy, hace más de 60 s
    respuestas = _en_paralelo([("/api/v1/auth/resend-code", {"email": ANA}, ip(i + 1)) for i in range(5)])
    assert len(sent_emails) == 1                                  # solo 1 se envía (el 10.º del día)
    assert {r.status_code for r in respuestas} <= {200, 429}
    assert sum(1 for r in bd.almacen.eventos[(ae.huella_correo(ANA), "correo")] if r == reloj.t) == 1


def test_inv038_emitir_codigo_es_una_sola_operacion_atomica_y_respeta_los_60s_en_paralelo(users, bd, sent_emails, ejecutor_amplio):
    _alta(users, activa=False)
    respuestas = _en_paralelo([("/api/v1/auth/resend-code", {"email": ANA}, ip(i + 1)) for i in range(10)])
    assert {r.status_code for r in respuestas} == {200}
    assert len(sent_emails) == 1                                  # exactamente 1 enviado; los otros 9 «reciente»
    assert bd.nombres.count("auth_codigo_emitir") == 10           # UNA llamada por pedido
    assert set(bd.nombres) == {"auth_limite_registrar", "auth_codigo_emitir"}   # no «comprobar» y luego «guardar»


def test_inv038_las_ventanas_usan_el_reloj_de_la_bd_y_el_backend_nunca_envia_la_hora(client, users, bd, sent_emails, reloj):
    _alta(users)
    _alta(users, "pend@example.com", activa=False)
    _login(client, clave="mala", n=1)
    _login(client, n=2)
    _post(client, "forgot-password", {"email": ANA}, 3)
    _post(client, "resend-code", {"email": "pend@example.com"}, 4)
    _post(client, "verify-email", {"email": ANA, "code": "000000"}, 5)
    _post(client, "reset-password", {"email": ANA, "code": "000000", "new_password": "NuevaClave1"}, 6)
    assert bd.llamadas
    marca = re.compile(r"\d{4}-\d{2}-\d{2}")
    for nombre, args in bd.llamadas:
        assert not any("ahora" in k or "hora" in k or "now" in k for k in args), (nombre, args)
        assert not any(isinstance(v, datetime) or (isinstance(v, str) and marca.search(v)) for v in args.values()), (nombre, args)
    # las ventanas siguen el reloj de la BD, no el del backend: moverlo mueve todo
    assert _huella_en_bd(bd) is None or _huella_en_bd(bd)["ventana_inicio"] <= reloj.t


# ───────────────────────── INV-039: fail-closed ─────────────────────────

def test_inv039_bd_caida_responde_503_en_todas_las_rutas_de_autenticacion(client, users, bd):
    _alta(users)
    bd.falla = RuntimeError(f"conexión rechazada para {ANA}")
    peticiones = [
        ("post", "/api/v1/auth/register", {"email": "nuevo@example.com", "full_name": "Nuevo", "password": CLAVE}),
        ("post", "/api/v1/auth/verify-email", {"email": ANA, "code": "123456"}),
        ("post", "/api/v1/auth/resend-code", {"email": ANA}),
        ("post", "/api/v1/auth/login", {"email": ANA, "password": CLAVE}),
        ("post", "/api/v1/auth/forgot-password", {"email": ANA}),
        ("post", "/api/v1/auth/reset-password", {"email": ANA, "code": "123456", "new_password": "NuevaClave1"}),
        ("post", "/api/v1/users/me/password", {"actual": CLAVE, "nueva": "NuevaClave1"}),
    ]
    for _metodo, ruta, cuerpo in peticiones:
        r = client.post(ruta, json=cuerpo, headers={**ip(1), **_sesion(f"id-{ANA}")})
        assert r.status_code == 503, ruta
        assert r.json() == {"detail": ae.MENSAJE_503}, ruta
        assert ANA not in r.text and "access_token" not in r.text
    assert "nuevo@example.com" not in users
    assert users[ANA]["hashed_password"] == "hash:" + CLAVE


def test_inv039_fallo_del_limite_por_ip_responde_503_no_deja_pasar(client, users, bd):
    _alta(users)
    bd.falla_en["auth_limite_registrar"] = RuntimeError("tabla de eventos no disponible")
    r = _login(client)                                            # credenciales CORRECTAS
    assert r.status_code == 503 and r.json() == {"detail": ae.MENSAJE_503} and "access_token" not in r.text
    assert bd.nombres == ["auth_limite_registrar"]                # no llegó a reservar ni a comprobar nada


def test_inv039_falla_solo_la_tabla_de_usuarios_responde_503(client, users, bd, sent_emails, monkeypatch):
    _alta(users)                                                  # activa: reset-password
    _alta(users, "bea@example.com", activa=False)                 # pendiente: verify-email
    assert _post(client, "forgot-password", {"email": ANA}, 1).status_code == 200
    assert _post(client, "resend-code", {"email": "bea@example.com"}, 2).status_code == 200
    reset = next(c for to, c, p in sent_emails if to == ANA and p == "reset")
    verificar = next(c for to, c, p in sent_emails if to == "bea@example.com")
    original = UserDB.get_by_email_estricto

    async def falla(email):
        raise RuntimeError(f"detalle interno de la tabla con {email}")
    monkeypatch.setattr(UserDB, "get_by_email_estricto", staticmethod(falla))
    llamadas = [
        ("login", {"email": ANA, "password": CLAVE}),
        ("forgot-password", {"email": ANA}),
        ("resend-code", {"email": "bea@example.com"}),
        ("register", {"email": "nuevo@example.com", "full_name": "Nuevo", "password": CLAVE}),
        ("verify-email", {"email": "bea@example.com", "code": verificar}),
        ("reset-password", {"email": ANA, "code": reset, "new_password": "NuevaClave1"}),
    ]
    for ruta, cuerpo in llamadas:
        r = _post(client, ruta, cuerpo, 3)
        assert r.status_code == 503 and r.json() == {"detail": ae.MENSAJE_503}, ruta   # nunca 401, 200 ni 404
        assert "detalle interno" not in r.text and "access_token" not in r.text
    assert "nuevo@example.com" not in users                       # no se crea ninguna cuenta
    assert _huella_en_bd(bd)["en_vuelo"] == 0                     # la reserva del login se cerró (como fallo)
    # los códigos correctos NO se consumieron: con la lectura recuperada siguen sirviendo
    monkeypatch.setattr(UserDB, "get_by_email_estricto", original)
    assert _post(client, "verify-email", {"email": "bea@example.com", "code": verificar}, 4).status_code == 200
    r = _post(client, "reset-password", {"email": ANA, "code": reset, "new_password": "NuevaClave1"}, 5)
    assert r.status_code == 200


def test_inv039_operacion_de_estado_lenta_responde_503_en_5s(client, users, bd):
    _alta(users)
    bd.espera = 4.4                                               # más que el plazo de 4 s por llamada
    t0 = time.monotonic()
    r = _login(client)
    assert r.status_code == 503 and r.json() == {"detail": ae.MENSAJE_503} and "access_token" not in r.text
    assert time.monotonic() - t0 < 6
    for _ in range(100):                                          # el hilo colgado termina y libera su ranura
        if ae._ranuras._value == ae.MAX_HILOS:
            break
        time.sleep(0.05)
    assert ae._ranuras._value == ae.MAX_HILOS


def test_inv039_el_plazo_se_impone_en_cada_llamada_al_cliente_de_la_bd(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "eyJhbGciOiJIUzI1NiJ9.e30.x")
    cliente = ae._crear_cliente()                                 # el que usan las rutas (`ae._cliente()`)
    assert cliente.postgrest.session.timeout.read <= 4 and cliente.postgrest.session.timeout.connect <= 4
    assert cliente.postgrest.retry_enabled is False
    assert ae.PLAZO_LLAMADA_SEG <= 4 and ae.PRESUPUESTO_PETICION_SEG == 5 and ae.MAX_HILOS == 8


def test_inv039_ejecutor_de_estado_agotado_responde_503_sin_encolar(client, users, bd, monkeypatch):
    _alta(users)
    ocupadas = threading.BoundedSemaphore(ae.MAX_HILOS)
    for _ in range(ae.MAX_HILOS):                                 # los 8 hilos ocupados con llamadas lentas
        ocupadas.acquire()
    monkeypatch.setattr(ae, "_ranuras", ocupadas)
    t0 = time.monotonic()
    r = _login(client)
    assert r.status_code == 503 and r.json() == {"detail": ae.MENSAJE_503}
    assert time.monotonic() - t0 < 1 and bd.llamadas == []        # inmediato, sin esperar en cola ni llegar a la BD


def test_inv039_el_503_no_depende_de_si_la_cuenta_existe(client, users, bd):
    _alta(users)
    _alta(users, "pend@example.com", activa=False)
    bd.falla = RuntimeError("caída")
    vistos = set()
    for ruta in ("forgot-password", "resend-code"):
        for correo in (ANA, "pend@example.com", "nadie@example.com"):
            r = _post(client, ruta, {"email": correo}, 1)
            vistos.add((ruta, r.status_code, r.text))
    assert {(ruta, c) for ruta, c, _ in vistos} == {("forgot-password", 503), ("resend-code", 503)}
    assert len(vistos) == 2                                       # una sola respuesta distinta por ruta: idéntica con y sin cuenta


# ───────────────────────── INV-009: sin enumeración ─────────────────────────

def test_inv009_forgot_password_hace_las_mismas_llamadas_a_la_bd_exista_o_no(client, users, bd, sent_emails):
    _alta(users)
    resultados = []
    for correo in (ANA, "nadie@example.com"):
        bd.llamadas.clear()
        r = _post(client, "forgot-password", {"email": correo}, 1)
        resultados.append((r.status_code, r.json(), [(n, sorted(a)) for n, a in bd.llamadas]))
    assert resultados[0] == resultados[1] and resultados[0][0] == 200
    assert resultados[0][2] == [("auth_limite_registrar", ["p_clave", "p_limite", "p_tipo", "p_ventana_seg"]),
                                ("auth_codigo_emitir", sorted(bd.llamadas[1][1]))]
    assert [(to, p) for to, _c, p in sent_emails] == [(ANA, "reset")]      # el código de la inexistente es un señuelo: no se envía


def test_inv009_resend_code_responde_y_cuenta_igual_en_pendiente_activa_e_inexistente(client, users, bd, sent_emails, reloj):
    _alta(users, "pend@example.com", activa=False)
    _alta(users, "activa@example.com")
    correos = ["pend@example.com", "activa@example.com", "nadie@example.com"]
    vistos = []
    for i, correo in enumerate(correos):
        bd.llamadas.clear()
        r = _post(client, "resend-code", {"email": correo}, i + 1)
        vistos.append((r.status_code, r.json(), [(n, sorted(a)) for n, a in bd.llamadas]))
    assert vistos[0] == vistos[1] == vistos[2] and vistos[0][0] == 200
    assert [to for to, _c, _p in sent_emails] == ["pend@example.com"]      # solo la pendiente recibe correo
    for correo in correos:                                                  # el señuelo también consumió el espacio de 60 s
        assert ae.huella_correo(correo) in {c for c, t in bd.almacen.eventos if t == "correo"}
    # antes del tope de 10/día: el mismo 429 «Ya enviamos varios códigos…» para las tres
    for correo in correos:
        _eventos(bd, ae.huella_correo(correo), "correo", 10, reloj.t)
    topes = [_post(client, "resend-code", {"email": c}, 10 + i) for i, c in enumerate(correos)]
    assert {(r.status_code, r.json()["detail"]) for r in topes} == {(429, MSG_TOPE)}
    # y con el tope global de 250
    for correo in correos:
        bd.almacen.eventos.pop((ae.huella_correo(correo), "correo"))
    _eventos(bd, "global", "global", 250, reloj.t)
    topes = [_post(client, "resend-code", {"email": c}, 20 + i) for i, c in enumerate(correos)]
    assert {(r.status_code, r.json()["detail"]) for r in topes} == {(429, MSG_TOPE)}
    assert [to for to, _c, _p in sent_emails] == ["pend@example.com"]


def test_inv009_login_con_correo_inexistente_verifica_contra_un_hash_senuelo(client, users, bd, bcrypt_contado):
    _alta(users)
    r_real = _login(client, ANA, "mala", 1)
    comprobado_real = list(bcrypt_contado)
    bcrypt_contado.clear()
    r_falso = _login(client, "nadie@example.com", "mala", 2)
    assert r_real.status_code == r_falso.status_code == 401
    assert r_real.json() == r_falso.json() == {"detail": "Credenciales inválidas"}
    assert comprobado_real == ["hash:" + CLAVE]
    assert bcrypt_contado == [security.HASH_SENUELO]              # también una comprobación bcrypt, contra el hash señuelo
    for correo in (ANA, "nadie@example.com"):                     # y ambos cuentan como fallo
        assert _huella_en_bd(bd, correo)["fallos"] == 1


def test_inv039_el_codigo_senuelo_no_puede_verificarse(client, users, bd, sent_emails):
    _alta(users)                                                  # cuenta ACTIVA: resend-code guarda un señuelo
    assert _post(client, "resend-code", {"email": ANA}, 1).status_code == 200
    assert sent_emails == []
    (clave, proposito), fila = next(iter(bd.almacen.codigos.items()))
    assert clave == ae.huella_correo(ANA) and proposito == "verify"
    # ningún valor de 6 dígitos produce el HMAC del señuelo (muestra amplia; el espacio completo son 10^6 valores)
    for n in range(0, 60000):
        assert ae.hmac_codigo("verify", ANA, f"{n:06d}") != fila["codigo_hmac"]
    # y por la ruta: ni los 5 intentos que admite el código dan sesión
    for i in range(6):
        r = _post(client, "verify-email", {"email": ANA, "code": f"{i * 111111:06d}"}, 10 + i)
        assert r.status_code == 400 and "access_token" not in r.text


# ───────────────────────── INV-041: modo demo y memoria ─────────────────────────

def test_inv041_en_produccion_sin_supabase_no_se_usa_memoria(client, users, monkeypatch, sent_emails):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    _alta(users)
    for ruta, cuerpo in (("login", {"email": ANA, "password": CLAVE}), ("forgot-password", {"email": ANA}),
                         ("resend-code", {"email": ANA}), ("verify-email", {"email": ANA, "code": "123456"})):
        r = _post(client, ruta, cuerpo, 1)
        assert r.status_code == 503 and r.json() == {"detail": ae.MENSAJE_503}, ruta
    assert ae._Memoria.intentos == {} and ae._Memoria.codigos == {} and ae._Memoria.eventos == {}
    assert sent_emails == []


def test_inv041_con_supabase_configurado_no_queda_estado_en_memoria(client, users, bd, sent_emails):
    _alta(users)
    for n in range(1, 6):
        _login(client, clave="mala", n=n)
    _post(client, "forgot-password", {"email": ANA}, 7)
    assert sent_emails                                            # sí se emitió un código…
    assert ae._Memoria.intentos == {} and ae._Memoria.codigos == {} and ae._Memoria.eventos == {}   # …pero no en memoria
    assert bd.almacen.intentos and bd.almacen.codigos and bd.almacen.eventos                        # está en la BD
    # los diccionarios y limitadores de memoria de autenticación ya no existen (INV-013, en su alcance)
    from app.utils import email as email_utils
    for nombre in ("_login_fails", "_ip_email_requests", "_email_daily", "_global_daily", "_ip_auth_attempts"):
        assert not hasattr(auth_routes, nombre), nombre
    for nombre in ("_pending_codes", "save_code", "verify_code", "code_recently_sent"):
        assert not hasattr(email_utils, nombre), nombre


def test_inv041_modo_demo_fuera_de_produccion_sigue_funcionando(client, users, sent_emails, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert not settings.SUPABASE_URL
    assert client.post("/api/v1/auth/register", json={"email": ANA, "full_name": "Ana", "password": CLAVE},
                       headers=ip(1)).status_code == 201
    assert _login(client, n=2).json()["status"] == "pending"
    r = _post(client, "verify-email", {"email": ANA, "code": sent_emails[0][1]}, 3)
    assert r.status_code == 200
    assert _login(client, clave="mala", n=4).status_code == 401
    assert ae._Memoria.intentos and ae._Memoria.eventos            # en memoria, solo en el modo demo


# ───────────────────────── INV-040: privacidad y ciclo de vida ─────────────────────────

def test_inv040_las_claves_son_huellas_hmac_no_el_correo_ni_la_ip(client, users, bd, sent_emails):
    correo, ip_cliente = "ana@correo.com", "203.0.113.7"
    _alta(users, correo)
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": correo, "password": "mala"}, headers={"X-Forwarded-For": ip_cliente})
    client.post("/api/v1/auth/forgot-password", json={"email": correo}, headers={"X-Forwarded-For": ip_cliente})
    client.post("/api/v1/auth/resend-code", json={"email": "otra@correo.com"}, headers={"X-Forwarded-For": ip_cliente})
    volcado = repr(bd.llamadas)
    assert correo not in volcado and "otra@correo.com" not in volcado and "203.0.113" not in volcado
    assert sent_emails[0][1] not in volcado
    huellas = [v for _n, a in bd.llamadas for k, v in a.items() if k in ("p_clave", "p_clave_correo", "p_codigo_hmac")]
    assert huellas and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in huellas)
    assert ae.huella_ip(ip_cliente) in huellas and ae.huella_correo(correo) in huellas


def test_inv040_el_codigo_se_guarda_solo_como_hmac(client, users, bd, sent_emails, monkeypatch):
    monkeypatch.setattr(auth_routes, "generate_code", lambda: "482913")
    assert client.post("/api/v1/auth/register", json={"email": ANA, "full_name": "Ana", "password": CLAVE},
                       headers=ip(1)).status_code == 201
    assert sent_emails[0][1] == "482913"
    assert "482913" not in repr(bd.llamadas) and "482913" not in repr(bd.almacen.codigos)
    assert _post(client, "verify-email", {"email": ANA, "code": "482913"}, 2).status_code == 200   # y la verificación funciona


def test_inv040_nada_sensible_en_logs_ni_en_errores(client, users, bd, capsys, caplog):
    _alta(users)
    ip_cliente, codigo = "203.0.113.9", "482913"
    bd.falla = RuntimeError(f"fallo del servidor con {ANA} desde {ip_cliente} y el código {codigo}")
    textos = []
    for ruta, cuerpo in (("login", {"email": ANA, "password": CLAVE}), ("forgot-password", {"email": ANA}),
                         ("verify-email", {"email": ANA, "code": codigo}),
                         ("register", {"email": ANA, "full_name": "Ana", "password": CLAVE})):
        r = client.post(f"/api/v1/auth/{ruta}", json=cuerpo, headers={"X-Forwarded-For": ip_cliente})
        assert r.status_code == 503
        textos.append(r.text)
    salida = capsys.readouterr()
    todo = " ".join(textos) + salida.out + salida.err + caplog.text
    assert "[auth_estado]" in todo
    for dato in (ANA, ip_cliente, codigo, "fallo del servidor"):
        assert dato not in todo


def _borrable(monkeypatch, users):
    async def delete_by_id(user_id):
        for correo, u in list(users.items()):
            if u["id"] == user_id:
                del users[correo]
                return True
        return False
    monkeypatch.setattr(UserDB, "delete_by_id", staticmethod(delete_by_id))


def test_inv040_eliminar_cuenta_borra_intentos_y_codigos(client, users, bd, sent_emails, monkeypatch):
    _borrable(monkeypatch, users)
    _alta(users)
    for n in range(1, 3):
        assert _login(client, clave="mala", n=n).status_code == 401
    assert _post(client, "forgot-password", {"email": ANA}, 3).status_code == 200
    clave = ae.huella_correo(ANA)
    assert clave in bd.almacen.intentos and (clave, "reset") in bd.almacen.codigos
    eventos_antes = {k: list(v) for k, v in bd.almacen.eventos.items()}
    r = client.delete("/api/v1/users/me", headers=_sesion(f"id-{ANA}"))
    assert r.status_code == 204 and ANA not in users
    assert clave not in bd.almacen.intentos
    assert not [k for k in bd.almacen.codigos if k[0] == clave]
    assert bd.almacen.eventos == eventos_antes                     # los eventos de límites NO se borran (Q-5)
    borrado = [a for n, a in bd.llamadas if n == "auth_borrar_de_cuenta"]
    assert borrado == [{"p_clave_correo": clave}]                  # por huella, nunca el correo


def test_inv040_si_falla_la_limpieza_la_baja_no_se_revierte(client, users, bd, monkeypatch, capsys):
    _borrable(monkeypatch, users)
    _alta(users)
    bd.falla_en["auth_borrar_de_cuenta"] = RuntimeError(f"error con {ANA}")
    r = client.delete("/api/v1/users/me", headers=_sesion(f"id-{ANA}"))
    assert r.status_code == 204 and ANA not in users               # la baja se completó
    salida = capsys.readouterr()
    assert "No se pudo limpiar el estado de autenticación" in salida.out + salida.err
    assert ANA not in salida.out + salida.err and ae.huella_correo(ANA) not in salida.out + salida.err


def test_inv040_purga_30_dias_intentos_y_codigos_y_2_dias_eventos_una_vez_al_dia(client, users, bd, reloj):
    _alta(users, "pend@example.com", activa=False)
    ae._intento_purga["ultimo"] = None                             # esta prueba SÍ quiere la purga en segundo plano
    t = reloj.t
    al = bd.almacen

    def intento(hace):
        return {"fallos": 1, "en_vuelo": 0, "ventana_inicio": t - hace, "bloqueado_hasta": None, "actualizado_en": t - hace}

    def codigo(hace):
        return {"codigo_hmac": "0" * 64, "emitido_en": t - hace, "expira_en": t - hace + timedelta(minutes=10), "intentos": 0}
    al.intentos.update({"i31": intento(timedelta(days=31)), "i29": intento(timedelta(days=29))})
    al.codigos.update({("c31", "verify"): codigo(timedelta(days=31)), ("c29", "verify"): codigo(timedelta(days=29))})
    al.eventos.update({("e3", "correo"): [t - timedelta(days=3)], ("e1", "correo"): [t - timedelta(days=1)]})
    assert _post(client, "resend-code", {"email": "pend@example.com"}, 1).status_code == 200   # emite un código nuevo
    assert "i31" not in al.intentos and "i29" in al.intentos
    assert ("c31", "verify") not in al.codigos and ("c29", "verify") in al.codigos
    assert ("e3", "correo") not in al.eventos and ("e1", "correo") in al.eventos
    assert al.ultima_purga == t
    # no se vuelve a purgar el mismo día, ni siquiera desde otra «instancia» (la marca está en la BD)
    # (se usa un intento de 31 días: los eventos vencidos ya los libera auth_limite_registrar por su cuenta, I-A)
    al.intentos["i31b"] = intento(timedelta(days=31))
    bd.reiniciar()
    reloj.avanzar(hours=5)
    _post(client, "resend-code", {"email": "pend@example.com"}, 2)
    assert "i31b" in al.intentos
    reloj.avanzar(hours=20)                                        # pasó un día desde la última purga
    _post(client, "resend-code", {"email": "pend@example.com"}, 3)
    assert "i31b" not in al.intentos


def test_inv040_tope_de_filas_de_eventos_con_ip_falsificada_responde_429(client, users, bd, reloj, monkeypatch, capsys):
    monkeypatch.setattr(ae, "TOPE_FILAS_EVENTOS", 5)
    _alta(users)
    for i in range(6):                                              # un atacante con una IP distinta por petición
        bd.almacen.eventos[(f"ip{i}", "ip_intentos_auth")] = [reloj.t]
    antes = bd.almacen.total_eventos()
    r = _login(client)                                              # una persona legítima, con credenciales correctas
    assert r.status_code == 429 and r.json()["detail"] == MSG_IP and "access_token" not in r.text
    assert bd.almacen.total_eventos() == antes                      # no se insertan más filas
    salida = capsys.readouterr()
    assert "llegó a su tope" in salida.out and ANA not in salida.out + salida.err and "203.0.113" not in salida.out + salida.err


# ───────────────────────── Reglas heredadas, ahora sobre el estado persistente ─────────────────────────

def test_inv007_codigos_de_verificacion_y_reset_siguen_sin_ser_intercambiables(client, users, bd, sent_emails):
    _alta(users)
    _post(client, "forgot-password", {"email": ANA}, 1)
    reset = sent_emails[0][1]
    assert _post(client, "verify-email", {"email": ANA, "code": reset}, 2).status_code == 400       # reset como verificación
    asyncio.run(ae.codigo_emitir(ANA, "verify", "111111"))
    r = _post(client, "reset-password", {"email": ANA, "code": "111111", "new_password": "NuevaClave1"}, 3)
    assert r.status_code == 400                                                                      # verificación como reset
    r = _post(client, "reset-password", {"email": ANA, "code": reset, "new_password": "NuevaClave1"}, 4)
    assert r.status_code == 200                                    # el código de reset sigue vigente: no se gastó


def test_inv010_el_login_correcto_reinicia_los_fallos_y_el_restablecimiento_desbloquea(client, users, bd, sent_emails):
    _alta(users)
    for n in range(1, 5):
        assert _login(client, clave="mala", n=n).status_code == 401                                  # 4 fallos
    assert _login(client, n=5).status_code == 200
    assert _huella_en_bd(bd) is None                               # contador en 0
    for n in range(6, 11):                                         # 5 fallos: bloqueado «por otra persona»
        assert _login(client, clave="mala", n=n).status_code == 401
    assert _login(client, n=11).status_code == 429
    _post(client, "forgot-password", {"email": ANA}, 12)
    codigo = sent_emails[-1][1]
    r = _post(client, "reset-password", {"email": ANA, "code": codigo, "new_password": "NuevaClave1"}, 13)
    assert r.status_code == 200 and _huella_en_bd(bd) is None
    assert _login(client, clave="NuevaClave1", n=14).status_code == 200                              # desbloqueado


def test_inv027_change_password_usa_el_bloqueo_persistente(client, users, bd):
    _alta(users)
    for n in range(1, 5):
        assert _login(client, clave="mala", n=n).status_code == 401                                  # 4 fallos de login
    sesion = _sesion(f"id-{ANA}")
    r = client.post("/api/v1/users/me/password", json={"actual": "equivocada", "nueva": "NuevaClave1"}, headers={**sesion, **ip(1)})
    assert r.status_code == 400                                    # el 5.º fallo, ahora desde el perfil
    bd.reiniciar()
    r = client.post("/api/v1/users/me/password", json={"actual": CLAVE, "nueva": "NuevaClave1"}, headers={**sesion, **ip(1)})
    assert r.status_code == 429 and r.json()["detail"] == MSG_BLOQUEO     # bloqueado 15 min también tras un reinicio
    assert _login(client, n=2).status_code == 429
    assert users[ANA]["session_version"] == 0 and users[ANA]["hashed_password"] == "hash:" + CLAVE


def test_req_n017_llamadas_a_la_bd_por_operacion(client, users, bd, sent_emails, reloj):
    _alta(users)
    _alta(users, "pend@example.com", activa=False)

    def contar(operacion):
        bd.llamadas.clear()
        respuesta = operacion()
        return respuesta, len(bd.llamadas)

    r, n = contar(lambda: _login(client, n=1))
    assert r.status_code == 200 and n == 4                         # límite IP + reservar + resolver + último acceso (segundo plano)
    r, n = contar(lambda: _login(client, clave="mala", n=2))
    assert r.status_code == 401 and n == 3
    r, n = contar(lambda: _login(client, "pend@example.com", CLAVE, 3))
    assert r.json()["status"] == "pending" and n == 4              # + emitir código
    for k in range(4, 8):                                          # dejar el correo bloqueado
        _login(client, ANA, "mala", k + 10)
    r, n = contar(lambda: _login(client, n=30))
    assert r.status_code == 429 and n == 2                         # límite IP + reservar
    reloj.avanzar(seconds=61)                                      # pasó el espacio de 60 s del código que emitió el login
    asyncio.run(ae.codigo_emitir("pend@example.com", "verify", "123456"))
    r, n = contar(lambda: _post(client, "verify-email", {"email": "pend@example.com", "code": "123456"}, 31))
    assert r.status_code == 200 and n == 3                         # límite IP + verificar + último acceso (segundo plano)
    reloj.avanzar(seconds=61)
    asyncio.run(ae.codigo_emitir("pend@example.com", "reset", "654321"))
    r, n = contar(lambda: _post(client, "reset-password", {"email": "pend@example.com", "code": "654321", "new_password": "NuevaClave1"}, 32))
    assert r.status_code == 200 and n == 3                         # límite IP + verificar + reiniciar
    reloj.avanzar(seconds=61)
    r, n = contar(lambda: _post(client, "forgot-password", {"email": "pend@example.com"}, 33))
    assert r.status_code == 200 and n == 2                         # límite IP + emitir


# ───────────────────────── Ciclo 2 de CHG-020 (revisión independiente) ─────────────────────────

def _lenta_y_health(peticion_lenta):
    """Lanza `peticion_lenta` (coroutine con un cliente httpx) y, a la vez, 5 GET /health. Devuelve
    (respuesta_lenta, segundos_lenta, [segundos de cada /health])."""
    async def principal():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://prueba") as c:
            async def lenta():
                t = time.monotonic()
                r = await peticion_lenta(c)
                return r, time.monotonic() - t

            async def salud():
                await asyncio.sleep(0.1)                           # la lenta ya empezó
                tiempos = []
                for _ in range(5):
                    t = time.monotonic()
                    assert (await c.get("/health")).status_code == 200
                    tiempos.append(time.monotonic() - t)
                    await asyncio.sleep(0.05)
                return tiempos
            (r, dur), tiempos = await asyncio.gather(lenta(), salud())
            return r, dur, tiempos
    return asyncio.run(principal())


def test_i3_tabla_de_usuarios_lenta_responde_503_en_5s_y_no_bloquea_otras_peticiones(bd):
    bd.filas_usuarios = [{"id": "u1", "email": ANA, "hashed_password": "hash:" + CLAVE, "is_active": True}]
    bd.espera_usuarios = 4.6                                      # más que el plazo de 4 s por llamada
    r, dur, tiempos = _lenta_y_health(lambda c: c.post(
        "/api/v1/auth/login", json={"email": ANA, "password": CLAVE}, headers=ip(1)))
    assert r.status_code == 503 and r.json() == {"detail": ae.MENSAJE_503} and "access_token" not in r.text
    assert dur <= 5.2                                             # presupuesto de 5 s por petición
    assert max(tiempos) < 0.5                                     # el event loop siguió atendiendo (no se bloqueó 4 s)
    assert bd.hilos_usuarios and all(h.startswith("auth-estado") for h in bd.hilos_usuarios)   # en el ejecutor propio
    assert _huella_en_bd(bd)["fallos"] == 1                       # el intento ya estaba contado (INV-038)
    for _ in range(150):                                          # el hilo colgado termina y libera su ranura
        if ae._ranuras._value == ae.MAX_HILOS:
            break
        time.sleep(0.05)
    assert ae._ranuras._value == ae.MAX_HILOS


def test_i3_la_lectura_estricta_usa_el_cliente_dedicado_y_devuelve_el_usuario(bd):
    bd.filas_usuarios = [{"id": "u1", "email": ANA, "hashed_password": "hash:" + CLAVE, "is_active": True}]
    from fastapi.testclient import TestClient
    r = _login(TestClient(app), n=1)
    assert r.status_code == 200 and "access_token" in r.json()
    assert bd.nombres == ["auth_limite_registrar", "auth_login_reservar", "auth_login_resolver", "registrar_acceso"]
    assert bd.hilos_usuarios and bd.hilos_usuarios[0].startswith("auth-estado")


def _bcrypt_lento(monkeypatch, segundos):
    """verify_password síncrono y lento (como bcrypt, ~0,3 s) que cuenta en qué hilo corre."""
    hilos = []

    def verify(plain, hashed):
        hilos.append(threading.current_thread().name)
        time.sleep(segundos)
        return bool(hashed) and hashed == "hash:" + plain
    for modulo in (security, auth_routes):
        monkeypatch.setattr(modulo, "verify_password", verify)
    return hilos


def test_i6_login_con_cuenta_real_no_bloquea_el_event_loop_con_bcrypt(users, bd, monkeypatch):
    _alta(users)
    hilos = _bcrypt_lento(monkeypatch, 0.8)
    r, dur, tiempos = _lenta_y_health(lambda c: c.post(
        "/api/v1/auth/login", json={"email": ANA, "password": CLAVE}, headers=ip(1)))
    assert r.status_code == 200 and dur >= 0.8
    assert max(tiempos) < 0.4                                     # /health respondió mientras bcrypt tardaba 0,8 s
    assert hilos and threading.main_thread().name not in hilos and hilos[0] != threading.current_thread().name


def test_i6_login_con_cuenta_inexistente_tambien_va_al_hilo_y_tarda_lo_mismo(users, bd, monkeypatch):
    _alta(users)
    hilos = _bcrypt_lento(monkeypatch, 0.8)
    tiempos_login = {}
    for correo in (ANA, "nadie@example.com"):
        r, dur, tiempos = _lenta_y_health(lambda c, correo=correo: c.post(
            "/api/v1/auth/login", json={"email": correo, "password": "Otra12345"}, headers=ip(2)))
        assert r.status_code == 401 and max(tiempos) < 0.4
        tiempos_login[correo] = dur
    assert len(hilos) == 2 and len(set(hilos)) >= 1               # ambas comprobaciones corrieron fuera del loop
    assert abs(tiempos_login[ANA] - tiempos_login["nadie@example.com"]) < 0.3     # mismo tiempo (INV-009)


def test_i6_change_password_no_bloquea_el_event_loop_con_bcrypt(users, bd, monkeypatch):
    _alta(users)
    _bcrypt_lento(monkeypatch, 0.8)
    r, dur, tiempos = _lenta_y_health(lambda c: c.post(
        "/api/v1/users/me/password", json={"actual": CLAVE, "nueva": "NuevaClave1"}, headers={**_sesion(f"id-{ANA}"), **ip(1)}))
    assert r.status_code == 200 and dur >= 0.8 and max(tiempos) < 0.4


def test_i2_si_falla_reiniciar_el_login_change_password_devuelve_exito(client, users, bd, capsys):
    _alta(users)
    bd.falla_en["auth_login_reiniciar"] = RuntimeError(f"caída del estado para {ANA}")
    r = client.post("/api/v1/users/me/password", json={"actual": CLAVE, "nueva": "NuevaClave1"},
                    headers={**_sesion(f"id-{ANA}"), **ip(1)})
    assert r.status_code == 200 and "access_token" in r.json()     # la contraseña ya cambió: nunca 503 (INV-027)
    assert users[ANA]["hashed_password"] == "hash:NuevaClave1" and users[ANA]["session_version"] == 1
    assert "auth_login_reiniciar" in bd.nombres
    salida = capsys.readouterr()
    todo = salida.out + salida.err
    assert "no se pudo reiniciar el bloqueo" in todo and ANA not in todo and "caída del estado" not in todo


def test_i2_si_falla_reiniciar_el_login_reset_password_devuelve_exito_y_el_codigo_queda_gastado(client, users, bd, sent_emails, capsys):
    _alta(users)
    assert _post(client, "forgot-password", {"email": ANA}, 1).status_code == 200
    codigo = sent_emails[-1][1]
    bd.falla_en["auth_login_reiniciar"] = RuntimeError(f"caída del estado para {ANA}")
    r = _post(client, "reset-password", {"email": ANA, "code": codigo, "new_password": "NuevaClave1"}, 2)
    assert r.status_code == 200 and users[ANA]["hashed_password"] == "hash:NuevaClave1"
    assert _post(client, "reset-password", {"email": ANA, "code": codigo, "new_password": "OtraClave12"}, 3).status_code == 400
    salida = capsys.readouterr()
    assert ANA not in salida.out + salida.err and "caída del estado" not in salida.out + salida.err


def test_i1_una_reserva_huerfana_no_impide_que_el_login_correcto_reinicie_la_serie(client, users, bd, reloj):
    _alta(users)
    bd.falla_en["auth_login_resolver"] = RuntimeError("se cayó justo al resolver")
    assert _login(client, n=1).status_code == 503                  # credenciales correctas, pero la reserva quedó sin resolver
    assert _huella_en_bd(bd)["en_vuelo"] == 1 and _huella_en_bd(bd)["fallos"] == 1
    del bd.falla_en["auth_login_resolver"]
    reloj.avanzar(seconds=11)                                      # más de 10 s: ya no está en vuelo
    assert _login(client, n=2).status_code == 200
    assert _huella_en_bd(bd) is None                               # serie reiniciada (con la huérfana la serie quedaba)
    assert [_login(client, clave="mala", n=3 + i).status_code for i in range(5)] == [401] * 5   # 5 fallos NUEVOS
    assert _login(client, n=9).status_code == 429                  # y recién el 5.º bloquea


def test_i4_la_purga_va_aparte_y_su_fallo_no_afecta_la_respuesta(client, users, bd, sent_emails, capsys):
    _alta(users, activa=False)
    ae._intento_purga["ultimo"] = None
    bd.falla_en["auth_purgar"] = RuntimeError(f"purga lenta con {ANA}")
    r = _post(client, "resend-code", {"email": ANA}, 1)
    assert r.status_code == 200 and len(sent_emails) == 1          # el pedido y el correo salen igual
    assert bd.nombres == ["auth_limite_registrar", "auth_codigo_emitir", "auth_purgar"]   # purga en llamada aparte, DESPUÉS
    salida = capsys.readouterr()
    assert "no se pudo purgar" in salida.out + salida.err and ANA not in salida.out + salida.err


def test_i4_la_purga_se_intenta_una_vez_por_hora_por_proceso(client, users, bd, sent_emails, reloj):
    _alta(users, activa=False)
    ae._intento_purga["ultimo"] = None
    assert _post(client, "resend-code", {"email": ANA}, 1).status_code == 200
    reloj.avanzar(seconds=61)
    assert _post(client, "resend-code", {"email": ANA}, 2).status_code == 200
    assert bd.nombres.count("auth_purgar") == 1
    reloj.avanzar(hours=1)
    assert _post(client, "resend-code", {"email": ANA}, 3).status_code == 200
    assert bd.nombres.count("auth_purgar") == 2


def test_m4_si_get_by_id_falla_la_baja_sigue_y_deja_un_aviso_sin_datos(client, users, bd, monkeypatch, capsys):
    _borrable(monkeypatch, users)
    _alta(users)

    async def falla(_user_id):
        return None                                                # lo que devuelve UserDB.get_by_id ante un error
    monkeypatch.setattr(UserDB, "get_by_id", staticmethod(falla))
    r = client.delete("/api/v1/users/me", headers=_sesion(f"id-{ANA}"))
    assert r.status_code == 204 and ANA not in users
    assert "auth_borrar_de_cuenta" not in bd.nombres               # sin correo no hay limpieza por huella
    salida = capsys.readouterr()
    todo = salida.out + salida.err
    assert "se omite la limpieza del estado de autenticación" in todo and ANA not in todo


# ───────────────────────── Ciclo 3 de CHG-020: I-A (purga desde el login), M-A (bcrypt acotado), M-B, M-C ─────────────────────────

def test_ia_el_login_dispara_la_purga_en_segundo_plano_sin_pedir_ningun_codigo(client, users, bd, reloj):
    """Con IP falsificadas solo en /login nadie pide códigos: la purga igual se programa (tras responder), 1 vez por hora."""
    _alta(users)
    ae._intento_purga["ultimo"] = None
    assert _login(client, n=1).status_code == 200
    assert bd.nombres == ["auth_limite_registrar", "auth_login_reservar", "auth_login_resolver", "registrar_acceso",
                          "auth_purgar"]   # DESPUÉS
    assert not any(n == "auth_codigo_emitir" for n in bd.nombres)
    assert _login(client, clave="mala", n=2).status_code == 401                      # también con un 401
    assert bd.nombres.count("auth_purgar") == 1                                      # una vez por hora y proceso
    reloj.avanzar(hours=1, seconds=1)
    assert _login(client, clave="mala", n=3).status_code == 401
    assert bd.nombres.count("auth_purgar") == 2


def test_ia_la_purga_solo_se_programa_en_las_rutas_de_autenticacion(client, users, bd):
    from app.core.purga_fondo import es_ruta_de_auth
    assert es_ruta_de_auth("/api/v1/auth/login") and es_ruta_de_auth("/api/v1/users/me/password")
    assert not es_ruta_de_auth("/health") and not es_ruta_de_auth("/api/v1/categorias") and not es_ruta_de_auth("/api/v1/authx")
    ae._intento_purga["ultimo"] = None
    assert client.get("/health").status_code == 200
    assert "auth_purgar" not in bd.nombres


def test_ia_la_purga_tambien_se_programa_con_429_y_503_y_no_cambia_la_respuesta(client, users, bd, reloj):
    _alta(users)
    ae._intento_purga["ultimo"] = None
    bd.falla_en["auth_login_reservar"] = RuntimeError("caída")
    r = _login(client, n=1)
    assert r.status_code == 503 and r.json() == {"detail": ae.MENSAJE_503}
    assert "auth_purgar" in bd.nombres                                               # tras responder, aun con 503


def test_ia_la_purga_tambien_se_programa_con_un_429_por_ip(client, users, bd):
    _alta(users)
    for _ in range(30):                                                              # 30 intentos por IP/10 min
        _login(client, correo="otro@example.com", n=5)
    ae._intento_purga.update(ultimo=None, fallo=None)
    antes = bd.nombres.count("auth_purgar")
    r = _login(client, correo="otro@example.com", n=5)
    assert r.status_code == 429 and r.json()["detail"] == MSG_IP
    assert bd.nombres.count("auth_purgar") == antes + 1


def test_ia_el_cambio_de_contrasena_y_otras_rutas_de_auth_tambien_la_programan(client, users, bd):
    _alta(users)
    ae._intento_purga["ultimo"] = None
    r = client.post("/api/v1/users/me/password", json={"actual": CLAVE, "nueva": "NuevaClave1"},
                    headers={**_sesion(f"id-{ANA}"), **ip(1)})
    assert r.status_code == 200 and bd.nombres.count("auth_purgar") == 1


def test_mc_si_la_purga_falla_se_reintenta_a_los_5_minutos_y_no_a_la_hora(client, users, bd, reloj):
    _alta(users)
    ae._intento_purga["ultimo"] = None
    bd.falla_en["auth_purgar"] = RuntimeError(f"purga lenta con {ANA}")
    assert _login(client, n=1).status_code == 200                                    # la respuesta no cambia
    assert bd.nombres.count("auth_purgar") == 1 and ae._intento_purga["ultimo"] is None   # sin marca de «hecha»
    reloj.avanzar(seconds=60)
    assert _login(client, n=2).status_code == 200
    assert bd.nombres.count("auth_purgar") == 1                                      # aún no
    reloj.avanzar(seconds=ae.REINTENTO_PURGA_SEG)
    del bd.falla_en["auth_purgar"]
    assert _login(client, n=3).status_code == 200
    assert bd.nombres.count("auth_purgar") == 2 and ae._intento_purga["ultimo"] == reloj.t   # ahora sí funcionó
    reloj.avanzar(minutes=30)
    assert _login(client, n=4).status_code == 200
    assert bd.nombres.count("auth_purgar") == 2                                      # tras un éxito, una hora


def _llenar_bcrypt(monkeypatch):
    sem = threading.BoundedSemaphore(2)
    monkeypatch.setattr(ae, "_ranuras_bcrypt", sem)
    sem.acquire(), sem.acquire()                                                     # los 2 hilos «ocupados»


def test_ma_con_bcrypt_lleno_el_login_responde_503_sin_encolar_y_cierra_la_reserva(client, users, bd, monkeypatch, bcrypt_contado):
    _alta(users)
    _llenar_bcrypt(monkeypatch)
    t = time.monotonic()
    r = _login(client, n=1)
    assert r.status_code == 503 and r.json() == {"detail": ae.MENSAJE_503} and "access_token" not in r.text
    assert time.monotonic() - t < 1.0                                                # no se encoló: respuesta inmediata
    assert bcrypt_contado == []                                                      # no se comprobó nada
    assert _huella_en_bd(bd)["en_vuelo"] == 0 and _huella_en_bd(bd)["fallos"] == 1   # reserva cerrada (el intento ya contaba)
    assert "auth_login_resolver" in bd.nombres


def test_ma_con_bcrypt_lleno_el_login_de_cuenta_inexistente_tambien_503(client, users, bd, monkeypatch):
    _llenar_bcrypt(monkeypatch)
    r = _login(client, correo="nadie@example.com", n=1)
    assert r.status_code == 503 and r.json() == {"detail": ae.MENSAJE_503}


def test_ma_con_bcrypt_lleno_el_cambio_de_contrasena_responde_503_y_no_cambia_nada(client, users, bd, monkeypatch):
    _alta(users)
    _llenar_bcrypt(monkeypatch)
    r = client.post("/api/v1/users/me/password", json={"actual": CLAVE, "nueva": "NuevaClave1"},
                    headers={**_sesion(f"id-{ANA}"), **ip(1)})
    assert r.status_code == 503 and users[ANA]["hashed_password"] == "hash:" + CLAVE and users[ANA]["session_version"] == 0
    assert _huella_en_bd(bd)["en_vuelo"] == 0


def test_ma_el_login_usa_el_ejecutor_propio_de_bcrypt(users, bd, monkeypatch):
    _alta(users)
    hilos = _bcrypt_lento(monkeypatch, 0.05)
    assert _en_paralelo([("/api/v1/auth/login", {"email": ANA, "password": CLAVE}, ip(1))])[0].status_code == 200
    assert hilos and all(h.startswith("auth-bcrypt") for h in hilos)


def test_mb_reset_password_reinicia_el_login_con_presupuesto_propio_aunque_la_peticion_lo_haya_gastado(
        client, users, bd, sent_emails, monkeypatch):
    """M-B: si la petición ya agotó su presupuesto (p. ej. bcrypt lento al cambiar la contraseña), el desbloqueo igual se hace."""
    _alta(users)
    assert [_login(client, clave="mala", n=i).status_code for i in range(1, 6)] == [401] * 5     # correo bloqueado
    assert _post(client, "forgot-password", {"email": ANA}, 7).status_code == 200
    codigo = sent_emails[-1][1]
    original = UserDB.update_password

    async def gasta_el_presupuesto(email, nueva):
        resultado = await original(email, nueva)
        ae._fin_peticion.set(time.monotonic() - 1)                                   # la petición ya no tiene presupuesto
        return resultado
    monkeypatch.setattr(UserDB, "update_password", staticmethod(gasta_el_presupuesto))
    r = _post(client, "reset-password", {"email": ANA, "code": codigo, "new_password": "NuevaClave1"}, 8)
    assert r.status_code == 200
    assert "auth_login_reiniciar" in bd.nombres and _huella_en_bd(bd) is None       # desbloqueado de verdad
    assert _login(client, clave="NuevaClave1", n=9).status_code == 200


def test_mb_change_password_tambien_reinicia_con_presupuesto_propio(client, users, bd, monkeypatch):
    _alta(users)
    original = UserDB.update_password

    async def gasta_el_presupuesto(email, nueva):
        resultado = await original(email, nueva)
        ae._fin_peticion.set(time.monotonic() - 1)
        return resultado
    monkeypatch.setattr(UserDB, "update_password", staticmethod(gasta_el_presupuesto))
    r = client.post("/api/v1/users/me/password", json={"actual": CLAVE, "nueva": "NuevaClave1"},
                    headers={**_sesion(f"id-{ANA}"), **ip(1)})
    assert r.status_code == 200 and "auth_login_reiniciar" in bd.nombres and _huella_en_bd(bd) is None
