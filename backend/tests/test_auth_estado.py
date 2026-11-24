"""CHG-020 (T2) · INV-037 a INV-041: modelo del estado de autenticación persistente (`models/auth_estado.py`),
lectura estricta de usuarios, hash/código señuelo y limitador persistente por IP.

Sin Supabase real: el modo demo usa el almacén en memoria (misma semántica que las funciones SQL) y, para el modo BD,
un cliente de Supabase simulado que registra las llamadas RPC. La atomicidad REAL solo se prueba contra PostgreSQL
(`backend/sql/pruebas/07_comprobar_auth_persistente.sql`). Las pruebas de las rutas están en T3
(`test_auth_persistente.py`).
"""
import asyncio
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.core import rate_limit, security
from app.core.config import settings
from app.models import auth_estado as ae
from app.models.user import UserDB

CORREO = "persona.privada@example.com"
IP = "198.51.100.77"
CODIGO = "123456"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def memoria_limpia(monkeypatch):
    ae._Memoria.limpiar()
    monkeypatch.setattr(ae, "_cliente_estado", None)
    yield
    ae._Memoria.limpiar()


class Reloj:
    """Reloj controlable del modo demo (la BD real usa su propio now())."""

    def __init__(self, monkeypatch):
        self.t = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
        monkeypatch.setattr(ae, "_ahora", lambda: self.t)

    def avanzar(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def reloj(monkeypatch):
    return Reloj(monkeypatch)


# ───────────────────────── Cliente de Supabase simulado (modo BD) ─────────────────────────

class _Ejecucion:
    def __init__(self, cliente, nombre, args):
        self.c, self.nombre, self.args = cliente, nombre, args

    def execute(self):
        self.c.llamadas.append((self.nombre, dict(self.args)))
        if self.c.espera:
            time.sleep(self.c.espera)
        if self.c.falla is not None:
            raise self.c.falla
        valor = self.c.respuestas.get(self.nombre)
        return type("R", (), {"data": valor() if callable(valor) else valor})()


class ClienteFalso:
    def __init__(self, respuestas=None, falla=None, espera=0.0):
        self.llamadas, self.respuestas, self.falla, self.espera = [], respuestas or {}, falla, espera

    def rpc(self, nombre, args):
        return _Ejecucion(self, nombre, args)


@pytest.fixture
def bd(monkeypatch):
    """Configura Supabase y devuelve una función para instalar el cliente simulado."""
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "k")

    def instalar(cliente):
        monkeypatch.setattr(ae, "_cliente", lambda: cliente)
        return cliente
    return instalar


# ───────────────────────── Huellas (INV-040) ─────────────────────────

def test_inv040_las_claves_son_huellas_hmac_no_el_correo_ni_la_ip(bd):
    h = ae.huella_correo(CORREO)
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert CORREO not in h and "persona" not in h
    assert ae.huella_ip(IP) != IP and re.fullmatch(r"[0-9a-f]{64}", ae.huella_ip(IP))
    # determinista y normalizada (INV-014)
    assert ae.huella_correo("  Persona.Privada@Example.COM ") == h
    # el tipo separa dominios: el mismo texto como correo y como IP no coincide
    assert ae.huella("correo", IP) != ae.huella("ip", IP)
    # depende de SECRET_KEY: rotarla cambia las huellas (documentado en ADR-010)
    antes = settings.SECRET_KEY
    try:
        settings.SECRET_KEY = antes + "-otra"
        assert ae.huella_correo(CORREO) != h
    finally:
        settings.SECRET_KEY = antes
    assert ae.huella_correo(CORREO) == h
    # lo que viaja a la BD son huellas, nunca el correo ni la IP en claro
    cliente = bd(ClienteFalso({"auth_login_reservar": [{"permitido": True, "bloqueado_hasta": None}],
                               "auth_limite_registrar": "ok", "auth_codigo_emitir": "enviado"}))
    run(ae.login_reservar(CORREO))
    run(ae.limite_registrar(IP, "ip_intentos_auth", 30, 600))
    run(ae.codigo_emitir(CORREO, "verify", CODIGO))
    volcado = repr(cliente.llamadas)
    assert CORREO not in volcado and IP not in volcado and CODIGO not in volcado


def test_inv040_el_codigo_se_guarda_solo_como_hmac(reloj):
    h = ae.hmac_codigo("verify", CORREO, CODIGO)
    assert re.fullmatch(r"[0-9a-f]{64}", h) and CODIGO not in h
    # separa propósito, correo y código
    assert ae.hmac_codigo("reset", CORREO, CODIGO) != h
    assert ae.hmac_codigo("verify", "otra@example.com", CODIGO) != h
    assert ae.hmac_codigo("verify", CORREO, "654321") != h
    # en memoria (demo) tampoco queda en claro
    run(ae.codigo_emitir(CORREO, "verify", CODIGO))
    assert CODIGO not in repr(ae._Memoria.codigos) and CORREO not in repr(ae._Memoria.codigos)


def test_inv040_nada_sensible_en_logs_ni_en_errores(bd, capsys):
    secreto_servidor = f"detalle interno con {CORREO} y {IP} y {CODIGO}"
    bd(ClienteFalso(falla=RuntimeError(secreto_servidor)))
    for coro in (ae.login_reservar(CORREO), ae.login_resolver(CORREO, True), ae.login_reiniciar(CORREO),
                 ae.codigo_emitir(CORREO, "verify", CODIGO), ae.codigo_verificar(CORREO, "verify", CODIGO),
                 ae.limite_registrar(IP, "ip_intentos_auth", 30, 600), ae.borrar_de_cuenta(CORREO), ae.purgar()):
        with pytest.raises(ae.EstadoNoDisponible) as e:
            run(coro)
        assert CORREO not in str(e.value) and IP not in str(e.value) and "detalle interno" not in str(e.value)
    salida = capsys.readouterr()
    todo = salida.out + salida.err
    assert "[auth_estado]" in todo and "RuntimeError" in todo
    for dato in (CORREO, IP, CODIGO, "detalle interno", ae.huella_correo(CORREO), ae.hmac_codigo("verify", CORREO, CODIGO)):
        assert dato not in todo


# ───────────────────────── Login: reservar / resolver (INV-037, INV-038) ─────────────────────────

def test_inv037_cinco_fallos_repartidos_en_menos_de_24_horas_bloquean(reloj):
    permitidos = []
    for i in range(5):
        p, hasta = run(ae.login_reservar(CORREO))
        permitidos.append(p)
        run(ae.login_resolver(CORREO, False))
        if i < 4:
            reloj.avanzar(hours=4)      # 5 fallos en 16 h
    reloj.avanzar(minutes=1)
    assert permitidos == [True] * 5
    assert hasta == datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc) + timedelta(hours=16, minutes=15)
    p, hasta2 = run(ae.login_reservar(CORREO))
    assert p is False and hasta2 == hasta        # bloqueado: no cuenta ni mueve el bloqueo


def test_inv037_fallos_de_mas_de_24_horas_no_acumulan_con_uno_nuevo(reloj):
    for _ in range(4):
        assert run(ae.login_reservar(CORREO))[0]
        run(ae.login_resolver(CORREO, False))
    reloj.avanzar(hours=24)               # caduca la serie (24 h desde el primer fallo)
    p, hasta = run(ae.login_reservar(CORREO))
    assert p is True and hasta is None
    assert ae._Memoria.intentos[ae.huella_correo(CORREO)]["fallos"] == 1


def test_inv037_el_bloqueo_dura_15_minutos_desde_el_quinto_y_luego_la_serie_empieza_de_cero(reloj):
    for _ in range(5):
        run(ae.login_reservar(CORREO))
        run(ae.login_resolver(CORREO, False))
    reloj.avanzar(minutes=14, seconds=59)
    assert run(ae.login_reservar(CORREO))[0] is False
    reloj.avanzar(seconds=1)
    p, hasta = run(ae.login_reservar(CORREO))
    assert p is True and hasta is None
    assert ae._Memoria.intentos[ae.huella_correo(CORREO)]["fallos"] == 1   # de cero, no 6


def test_inv038_la_quinta_reserva_que_acierta_inicia_sesion_y_no_deja_bloqueado(reloj):
    for _ in range(4):
        run(ae.login_reservar(CORREO))
        run(ae.login_resolver(CORREO, False))
    p, hasta = run(ae.login_reservar(CORREO))      # 5.ª: fija el bloqueo
    assert p is True and hasta is not None
    run(ae.login_resolver(CORREO, True))           # y acierta: devuelve el intento y lo levanta
    assert ae.huella_correo(CORREO) not in ae._Memoria.intentos     # sin reservas en vuelo: serie borrada
    assert run(ae.login_reservar(CORREO))[0] is True


def test_inv038_devolver_el_intento_no_borra_los_fallos_en_vuelo(reloj):
    for _ in range(3):
        assert run(ae.login_reservar(CORREO))[0]   # tres reservas en vuelo
    run(ae.login_resolver(CORREO, True))           # una acierta mientras otras 2 siguen comprobando
    f = ae._Memoria.intentos[ae.huella_correo(CORREO)]
    assert f["fallos"] == 2 and f["en_vuelo"] == 2          # no se borró la serie
    run(ae.login_resolver(CORREO, False))
    run(ae.login_resolver(CORREO, False))
    assert ae._Memoria.intentos[ae.huella_correo(CORREO)]["fallos"] == 2


def test_inv038_login_correcto_sin_reservas_en_vuelo_borra_la_serie(reloj):
    for _ in range(3):
        run(ae.login_reservar(CORREO))
        run(ae.login_resolver(CORREO, False))
    run(ae.login_reservar(CORREO))
    run(ae.login_resolver(CORREO, True))
    assert ae._Memoria.intentos == {}


def test_inv010_el_login_correcto_reinicia_los_fallos_y_el_restablecimiento_desbloquea(reloj):
    for _ in range(5):
        run(ae.login_reservar(CORREO))
        run(ae.login_resolver(CORREO, False))
    assert run(ae.login_reservar(CORREO))[0] is False
    run(ae.login_reiniciar(CORREO))                # restablecimiento / cambio de contraseña con éxito
    assert run(ae.login_reservar(CORREO))[0] is True


def test_inv038_resolver_sin_serie_no_falla_ni_crea_filas():
    run(ae.login_resolver(CORREO, True))
    run(ae.login_resolver(CORREO, False))
    assert ae._Memoria.intentos == {}


# ───────────────────────── Códigos (INV-007, INV-037, INV-038) ─────────────────────────

def test_inv037_emitir_respeta_60_segundos_y_un_codigo_nuevo_reemplaza_al_anterior(reloj):
    assert run(ae.codigo_emitir(CORREO, "verify", "111111")) == "enviado"
    reloj.avanzar(seconds=59)
    assert run(ae.codigo_emitir(CORREO, "verify", "222222")) == "reciente"
    assert run(ae.codigo_emitir(CORREO, "reset", "333333")) == "reciente"    # el espacio es por correo
    reloj.avanzar(seconds=1)
    assert run(ae.codigo_emitir(CORREO, "verify", "444444")) == "enviado"
    assert run(ae.codigo_verificar(CORREO, "verify", "111111")) == "incorrecto"
    assert run(ae.codigo_verificar(CORREO, "verify", "444444")) == "ok"


def test_inv007_codigos_de_verificacion_y_reset_siguen_sin_ser_intercambiables(reloj):
    run(ae.codigo_emitir(CORREO, "verify", CODIGO))
    assert run(ae.codigo_verificar(CORREO, "reset", CODIGO)) == "invalido"    # no hay código de reset
    reloj.avanzar(seconds=61)
    run(ae.codigo_emitir(CORREO, "reset", "999999"))
    assert run(ae.codigo_verificar(CORREO, "verify", "999999")) == "incorrecto"
    assert run(ae.codigo_verificar(CORREO, "reset", CODIGO)) == "incorrecto"
    assert run(ae.codigo_verificar(CORREO, "reset", "999999")) == "ok"


def test_inv007_codigo_de_un_solo_uso_y_vence_a_los_10_minutos(reloj):
    run(ae.codigo_emitir(CORREO, "verify", CODIGO))
    assert run(ae.codigo_verificar(CORREO, "verify", CODIGO)) == "ok"
    assert run(ae.codigo_verificar(CORREO, "verify", CODIGO)) == "invalido"   # un solo uso
    reloj.avanzar(minutes=2)
    run(ae.codigo_emitir(CORREO, "verify", CODIGO))
    reloj.avanzar(minutes=9, seconds=59)
    assert run(ae.codigo_verificar(CORREO, "verify", "000000")) == "incorrecto"
    reloj.avanzar(seconds=1)
    assert run(ae.codigo_verificar(CORREO, "verify", CODIGO)) == "invalido"   # venció


def test_inv007_cinco_intentos_fallidos_invalidan_el_codigo(reloj):
    run(ae.codigo_emitir(CORREO, "verify", CODIGO))
    for _ in range(5):
        assert run(ae.codigo_verificar(CORREO, "verify", "000000")) == "incorrecto"
    assert run(ae.codigo_verificar(CORREO, "verify", CODIGO)) == "invalido"   # ni el correcto sirve ya


def test_inv038_emitir_un_codigo_nuevo_reinicia_los_intentos(reloj):
    run(ae.codigo_emitir(CORREO, "verify", CODIGO))
    for _ in range(4):
        run(ae.codigo_verificar(CORREO, "verify", "000000"))
    reloj.avanzar(seconds=61)
    run(ae.codigo_emitir(CORREO, "verify", "777777"))
    assert ae._Memoria.codigos[(ae.huella_correo(CORREO), "verify")]["intentos"] == 0


def test_inv038_limite_de_correos_por_destinatario_10_al_dia(reloj):
    estados = []
    for i in range(12):
        estados.append(run(ae.codigo_emitir(CORREO, "verify", f"{i:06d}", espacio_seg=0)))
    assert estados == ["enviado"] * 10 + ["limitado"] * 2
    assert run(ae.codigo_emitir("otra@example.com", "verify", CODIGO)) == "enviado"
    reloj.avanzar(hours=24, seconds=1)                 # la ventana de 24 h pasó
    assert run(ae.codigo_emitir(CORREO, "verify", CODIGO)) == "enviado"


def test_inv038_limite_global_250_al_dia_y_un_rechazo_no_cuenta(reloj):
    for i in range(250):
        assert run(ae.codigo_emitir(f"u{i}@example.com", "verify", CODIGO)) == "enviado"
    assert run(ae.codigo_emitir("extra@example.com", "verify", CODIGO)) == "limitado"
    assert ae._Memoria.total_eventos() == 500          # 250 de correo + 250 globales; el rechazado no suma
    assert (ae.huella_correo("extra@example.com"), "verify") not in ae._Memoria.codigos


def test_inv039_el_codigo_senuelo_no_puede_verificarse(reloj):
    senuelo = security.codigo_senuelo()
    assert senuelo != security.codigo_senuelo() and len(senuelo) >= 64 and not re.fullmatch(r"\d{6}", senuelo)
    run(ae.codigo_emitir(CORREO, "verify", senuelo))           # se guarda y cuenta como un envío real
    # ningún código de 6 dígitos coincide (se prueba un barrido pequeño y la propiedad estructural)
    for intento in ("000000", "123456", "999999"):
        assert ae.hmac_codigo("verify", CORREO, intento) != ae.hmac_codigo("verify", CORREO, senuelo)
    assert run(ae.codigo_verificar(CORREO, "verify", "123456")) == "incorrecto"
    assert run(ae.codigo_verificar(CORREO, "verify", senuelo)) == "ok"   # solo quien lo conoce (nadie: no se envía)


def test_inv039_el_senuelo_ocupa_el_mismo_lugar_que_un_envio_real(reloj):
    """El señuelo ejecuta y cuenta IGUAL: mismo espacio de 60 s y mismos eventos."""
    run(ae.codigo_emitir("real@example.com", "reset", "123456"))
    run(ae.codigo_emitir("falso@example.com", "reset", security.codigo_senuelo()))
    assert run(ae.codigo_emitir("real@example.com", "reset", "654321")) == "reciente"
    assert run(ae.codigo_emitir("falso@example.com", "reset", security.codigo_senuelo())) == "reciente"
    assert ae._Memoria.total_eventos() == 4


def test_codigo_emitir_y_verificar_rechazan_propositos_desconocidos():
    with pytest.raises(ValueError):
        run(ae.codigo_emitir(CORREO, "otro", CODIGO))
    with pytest.raises(ValueError):
        run(ae.codigo_verificar(CORREO, "otro", CODIGO))


# ───────────────────────── Límites por IP, baja y purga ─────────────────────────

def test_inv037_las_ventanas_siguen_siendo_deslizantes_con_los_mismos_numeros(reloj):
    # 30 intentos por IP cada 10 min
    res = []
    for i in range(32):
        res.append(run(ae.limite_registrar(IP, "ip_intentos_auth", 30, 600)))
        reloj.avanzar(seconds=1)
    assert res == ["ok"] * 30 + ["limitado"] * 2
    reloj.avanzar(seconds=600)                       # todo sale de la ventana
    assert run(ae.limite_registrar(IP, "ip_intentos_auth", 30, 600)) == "ok"
    # 10 pedidos por IP/hora, contador independiente del anterior y por IP
    res = [run(ae.limite_registrar(IP, "ip_pedidos_codigo", 10, 3600)) for _ in range(11)]
    assert res == ["ok"] * 10 + ["limitado"]
    assert run(ae.limite_registrar("198.51.100.78", "ip_pedidos_codigo", 10, 3600)) == "ok"
    # deslizante exacta: el cupo se libera de a uno
    reloj.avanzar(seconds=3600)
    assert run(ae.limite_registrar(IP, "ip_pedidos_codigo", 10, 3600)) == "ok"


def test_inv040_tope_de_filas_de_eventos_con_ip_falsificada(reloj, monkeypatch):
    monkeypatch.setattr(ae, "TOPE_FILAS_EVENTOS", 3)
    resultados = [run(ae.limite_registrar(f"10.0.0.{i}", "ip_intentos_auth", 30, 600)) for i in range(6)]
    assert resultados == ["ok", "ok", "ok", "ok", "lleno", "lleno"]   # > tope (3) → lleno


def test_inv040_eliminar_cuenta_borra_intentos_y_codigos_pero_no_los_eventos(reloj):
    run(ae.login_reservar(CORREO))
    run(ae.codigo_emitir(CORREO, "verify", CODIGO))
    run(ae.codigo_emitir(CORREO, "reset", CODIGO, espacio_seg=0))
    eventos = ae._Memoria.total_eventos()
    assert run(ae.borrar_de_cuenta(CORREO)) == 3
    assert ae._Memoria.intentos == {} and ae._Memoria.codigos == {}
    assert ae._Memoria.total_eventos() == eventos      # el tope «10 correos/día» no se reinicia con la baja
    assert run(ae.borrar_de_cuenta(CORREO)) == 0


def test_inv040_purga_30_dias_intentos_y_codigos_y_2_dias_eventos_una_vez_al_dia(reloj):
    run(ae.login_reservar("vieja@example.com"))
    run(ae.codigo_emitir("vieja@example.com", "verify", CODIGO))
    reloj.avanzar(days=1)
    assert run(ae.purgar()) >= 0 and ae._Memoria.intentos       # primera purga: nada vence aún salvo eventos de 1 día no
    reloj.avanzar(days=2)
    run(ae.limite_registrar(IP, "ip_intentos_auth", 30, 600))   # evento reciente: debe sobrevivir
    reloj.avanzar(hours=1)
    assert run(ae.purgar()) > 0
    assert ae._Memoria.total_eventos() == 1                     # los eventos de más de 2 días se fueron
    assert run(ae.purgar()) == -1                               # solo una vez al día
    assert ae._Memoria.intentos and ae._Memoria.codigos         # intentos y códigos duran 30 días
    reloj.avanzar(days=31)
    assert run(ae.purgar()) > 0
    assert ae._Memoria.intentos == {} and ae._Memoria.codigos == {}


# ───────────────────────── Modo BD: llamadas RPC reales (nombres, parámetros, retornos) ─────────────────────────

def test_inv038_las_ventanas_usan_el_reloj_de_la_bd_y_el_backend_nunca_envia_la_hora(bd):
    cliente = bd(ClienteFalso({
        "auth_login_reservar": [{"permitido": True, "bloqueado_hasta": None}],
        "auth_login_resolver": None, "auth_login_reiniciar": None,
        "auth_codigo_emitir": "enviado", "auth_codigo_verificar": "ok",
        "auth_limite_registrar": "ok", "auth_borrar_de_cuenta": 2, "auth_purgar": -1}))
    run(ae.login_reservar(CORREO)); run(ae.login_resolver(CORREO, True)); run(ae.login_reiniciar(CORREO))
    run(ae.codigo_emitir(CORREO, "verify", CODIGO)); run(ae.codigo_verificar(CORREO, "verify", CODIGO))
    run(ae.limite_registrar(IP, "ip_pedidos_codigo", 10, 3600)); run(ae.borrar_de_cuenta(CORREO)); run(ae.purgar())
    nombres = [n for n, _ in cliente.llamadas]
    assert nombres == ["auth_login_reservar", "auth_login_resolver", "auth_login_reiniciar", "auth_codigo_emitir",
                       "auth_codigo_verificar", "auth_limite_registrar", "auth_borrar_de_cuenta", "auth_purgar"]
    assert all("p_ahora" not in a for _, a in cliente.llamadas)
    assert all(not isinstance(v, datetime) for _, a in cliente.llamadas for v in a.values())


def test_req_n017_parametros_y_retornos_de_cada_funcion_sql(bd):
    hc = ae.huella_correo(CORREO)
    cliente = bd(ClienteFalso({
        "auth_login_reservar": [{"permitido": False, "bloqueado_hasta": "2026-11-24T12:15:00.12345+00:00"}],
        "auth_codigo_emitir": "limitado", "auth_codigo_verificar": "incorrecto",
        "auth_limite_registrar": "lleno", "auth_borrar_de_cuenta": 3, "auth_purgar": 7}))
    permitido, hasta = run(ae.login_reservar(CORREO))
    assert permitido is False and hasta == datetime(2026, 11, 24, 12, 15, 0, 123450, tzinfo=timezone.utc)
    assert run(ae.codigo_emitir(CORREO, "reset", CODIGO)) == "limitado"
    assert run(ae.codigo_verificar(CORREO, "reset", CODIGO)) == "incorrecto"
    assert run(ae.limite_registrar(IP, "ip_intentos_auth", 30, 600)) == "lleno"
    assert run(ae.borrar_de_cuenta(CORREO)) == 3 and run(ae.purgar()) == 7
    llamadas = dict(cliente.llamadas)
    assert llamadas["auth_login_reservar"] == {"p_clave": hc, "p_max": 5, "p_ventana_seg": 86400, "p_bloqueo_seg": 900}
    assert llamadas["auth_codigo_emitir"] == {
        "p_clave_correo": hc, "p_proposito": "reset", "p_codigo_hmac": ae.hmac_codigo("reset", CORREO, CODIGO),
        "p_espacio_seg": 60, "p_limite_destinatario": 10, "p_limite_global": 250,
        "p_ventana_seg": 86400, "p_vigencia_seg": 600}
    assert llamadas["auth_codigo_verificar"] == {
        "p_clave_correo": hc, "p_proposito": "reset", "p_codigo_hmac": ae.hmac_codigo("reset", CORREO, CODIGO), "p_max": 5}
    assert llamadas["auth_limite_registrar"] == {
        "p_clave": ae.huella_ip(IP), "p_tipo": "ip_intentos_auth", "p_limite": 30, "p_ventana_seg": 600}
    assert llamadas["auth_borrar_de_cuenta"] == {"p_clave_correo": hc}
    assert llamadas["auth_purgar"] == {}


def test_inv039_bd_de_estado_con_error_o_respuesta_inesperada_es_fail_closed(bd):
    bd(ClienteFalso(falla=ConnectionError("caída")))
    with pytest.raises(ae.EstadoNoDisponible):
        run(ae.login_reservar(CORREO))
    # respuestas fuera de contrato: nunca se interpretan como «permitido» ni «ok»
    for nombre, llamar in (
        ("auth_login_reservar", lambda: ae.login_reservar(CORREO)),
        ("auth_codigo_emitir", lambda: ae.codigo_emitir(CORREO, "verify", CODIGO)),
        ("auth_codigo_verificar", lambda: ae.codigo_verificar(CORREO, "verify", CODIGO)),
        ("auth_limite_registrar", lambda: ae.limite_registrar(IP, "t", 1, 1)),
        ("auth_borrar_de_cuenta", lambda: ae.borrar_de_cuenta(CORREO)),
    ):
        for raro in (None, "quizas", [], {}, 3.5):
            bd(ClienteFalso({nombre: raro}))
            with pytest.raises(ae.EstadoNoDisponible):
                run(llamar())


def test_inv039_el_plazo_se_impone_en_cada_llamada_al_cliente_de_la_bd(monkeypatch):
    """El cliente de estado se crea con plazo ≤ 4 s EN EL CLIENTE HTTP y sin reintentos (no solo wait_for)."""
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "eyJhbGciOiJIUzI1NiJ9.e30.x")
    cliente = ae._crear_cliente()
    assert cliente.postgrest.session.timeout.read <= 4 and cliente.postgrest.session.timeout.connect <= 4
    assert cliente.postgrest.retry_enabled is False
    # es dedicado: distinto del cliente compartido del resto de la app
    from app.core.supabase import SupabaseDB
    monkeypatch.setattr(SupabaseDB, "_client", None)
    assert cliente is not SupabaseDB.get_client()


def test_inv039_operacion_de_estado_lenta_responde_503_en_5s(bd, monkeypatch):
    """Una llamada que no responde al plazo da EstadoNoDisponible; el hilo colgado no se acumula (se libera al terminar)."""
    monkeypatch.setattr(ae, "PLAZO_LLAMADA_SEG", 0.2)
    bd(ClienteFalso({"auth_login_reservar": [{"permitido": True, "bloqueado_hasta": None}]}, espera=0.6))
    t0 = time.monotonic()
    with pytest.raises(ae.EstadoNoDisponible):
        run(ae.login_reservar(CORREO))
    assert time.monotonic() - t0 < 0.5
    # la ranura sigue ocupada mientras el hilo vive y se libera cuando termina
    for _ in range(50):
        if ae._ranuras._value == ae.MAX_HILOS:
            break
        time.sleep(0.05)
    assert ae._ranuras._value == ae.MAX_HILOS


def test_inv039_presupuesto_de_5s_por_peticion_se_agota_entre_llamadas(bd, monkeypatch):
    bd(ClienteFalso({"auth_login_reiniciar": None}))

    async def peticion():
        ae.iniciar_presupuesto(0.05)
        await ae.login_reiniciar(CORREO)             # entra: queda presupuesto
        await asyncio.sleep(0.08)                    # la petición se alarga
        await ae.login_reiniciar(CORREO)             # sin presupuesto: 503 sin llamar a la BD

    with pytest.raises(ae.EstadoNoDisponible):
        run(peticion())


def test_inv039_cada_llamada_recibe_el_minimo_entre_4s_y_lo_que_queda(bd, monkeypatch):
    vistos = []
    real = asyncio.wait_for

    async def espia(aw, timeout):
        vistos.append(timeout)
        return await real(aw, timeout)

    monkeypatch.setattr(ae.asyncio, "wait_for", espia)
    bd(ClienteFalso({"auth_login_reiniciar": None}))

    async def peticion():
        ae.iniciar_presupuesto(5.0)
        await ae.login_reiniciar(CORREO)
        ae.iniciar_presupuesto(1.5)
        await ae.login_reiniciar(CORREO)

    run(peticion())
    assert vistos[0] == pytest.approx(4.0) and 1.0 < vistos[1] <= 1.5


def test_inv039_ejecutor_de_estado_agotado_responde_503_sin_encolar(bd):
    cliente = bd(ClienteFalso({"auth_login_reiniciar": None}))
    tomadas = 0
    while ae._ranuras.acquire(blocking=False):      # simula 8 llamadas colgadas
        tomadas += 1
    try:
        assert tomadas == ae.MAX_HILOS
        t0 = time.monotonic()
        with pytest.raises(ae.EstadoNoDisponible):
            run(ae.login_reiniciar(CORREO))
        assert time.monotonic() - t0 < 0.5           # inmediato, no espera hilo
        assert cliente.llamadas == []                # y no llegó a la BD
    finally:
        for _ in range(tomadas):
            ae._ranuras.release()
    run(ae.login_reiniciar(CORREO))                  # liberadas: vuelve a funcionar
    assert len(cliente.llamadas) == 1


def test_inv039_ejecutor_propio_no_supera_8_hilos_concurrentes(bd):
    activos, maximo, lock = 0, 0, threading.Lock()

    class Lento(ClienteFalso):
        def rpc(self, nombre, args):
            nonlocal activos, maximo
            with lock:
                activos += 1
                maximo = max(maximo, activos)
            time.sleep(0.15)
            with lock:
                activos -= 1
            return super().rpc(nombre, args)

    bd(Lento({"auth_login_reiniciar": None}))

    async def rafaga():
        return await asyncio.gather(*[ae.login_reiniciar(f"u{i}@example.com") for i in range(20)],
                                    return_exceptions=True)

    resultados = run(rafaga())
    assert maximo <= ae.MAX_HILOS
    assert sum(isinstance(r, ae.EstadoNoDisponible) for r in resultados) >= 20 - ae.MAX_HILOS
    assert sum(r is None for r in resultados) >= 1


# ───────────────────────── Modo demo e INV-041 ─────────────────────────

def test_inv041_en_produccion_sin_supabase_no_se_usa_memoria(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    for coro in (ae.login_reservar(CORREO), ae.login_resolver(CORREO, True), ae.login_reiniciar(CORREO),
                 ae.codigo_emitir(CORREO, "verify", CODIGO), ae.codigo_verificar(CORREO, "verify", CODIGO),
                 ae.limite_registrar(IP, "t", 1, 1), ae.borrar_de_cuenta(CORREO), ae.purgar()):
        with pytest.raises(ae.EstadoNoDisponible):
            run(coro)
    assert ae._Memoria.intentos == {} and ae._Memoria.codigos == {} and ae._Memoria.eventos == {}


def test_inv041_con_supabase_configurado_no_queda_estado_en_memoria(bd):
    bd(ClienteFalso({"auth_login_reservar": [{"permitido": True, "bloqueado_hasta": None}],
                     "auth_codigo_emitir": "enviado", "auth_codigo_verificar": "ok",
                     "auth_limite_registrar": "ok", "auth_login_resolver": None, "auth_login_reiniciar": None,
                     "auth_borrar_de_cuenta": 0, "auth_purgar": -1}))
    run(ae.login_reservar(CORREO)); run(ae.login_resolver(CORREO, False)); run(ae.login_reiniciar(CORREO))
    run(ae.codigo_emitir(CORREO, "verify", CODIGO)); run(ae.codigo_verificar(CORREO, "verify", CODIGO))
    run(ae.limite_registrar(IP, "t", 1, 1)); run(ae.borrar_de_cuenta(CORREO)); run(ae.purgar())
    assert ae._Memoria.intentos == {} and ae._Memoria.codigos == {} and ae._Memoria.eventos == {}
    assert ae._Memoria.ultima_purga is None


def test_inv041_con_supabase_y_fallo_no_se_cae_a_memoria(bd):
    bd(ClienteFalso(falla=RuntimeError("x")))
    with pytest.raises(ae.EstadoNoDisponible):
        run(ae.login_reservar(CORREO))
    with pytest.raises(ae.EstadoNoDisponible):
        run(ae.codigo_emitir(CORREO, "verify", CODIGO))
    assert ae._Memoria.intentos == {} and ae._Memoria.codigos == {} and ae._Memoria.eventos == {}


def test_inv041_modo_demo_fuera_de_produccion_sigue_funcionando(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert run(ae.login_reservar(CORREO))[0] is True
    assert run(ae.codigo_emitir(CORREO, "verify", CODIGO)) == "enviado"
    assert run(ae.codigo_verificar(CORREO, "verify", CODIGO)) == "ok"


# ───────────────────────── Lectura estricta de usuarios (INV-039, I-17) ─────────────────────────

class _Tabla:
    def __init__(self, filas=None, falla=None):
        self.filas, self.falla = filas or [], falla

    def __getattr__(self, _):
        return lambda *a, **k: self

    def execute(self):
        if self.falla:
            raise self.falla
        return type("R", (), {"data": self.filas})()


class _Cli:
    def __init__(self, tabla):
        self.tabla = tabla

    def table(self, _):
        return self.tabla


def test_inv039_get_by_email_estricto_propaga_los_errores_y_get_by_email_los_traga(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "k")
    from app.models import user as user_mod
    monkeypatch.setattr(user_mod.SupabaseDB, "get_client",
                        staticmethod(lambda: _Cli(_Tabla(falla=RuntimeError("tabla caída")))))
    with pytest.raises(RuntimeError):
        run(UserDB.get_by_email_estricto("a@example.com"))
    assert run(UserDB.get_by_email("a@example.com")) is None          # el actual se conserva para el resto


def test_inv039_get_by_email_estricto_devuelve_usuario_o_none(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_KEY", "k")
    from app.models import user as user_mod
    fila = {"id": "1", "email": "a@example.com", "hashed_password": "h", "is_active": True}
    monkeypatch.setattr(user_mod.SupabaseDB, "get_client", staticmethod(lambda: _Cli(_Tabla([fila]))))
    assert run(UserDB.get_by_email_estricto("A@Example.com"))["id"] == "1"
    monkeypatch.setattr(user_mod.SupabaseDB, "get_client", staticmethod(lambda: _Cli(_Tabla([]))))
    assert run(UserDB.get_by_email_estricto("a@example.com")) is None


def test_get_by_email_estricto_sin_supabase_devuelve_none():
    assert run(UserDB.get_by_email_estricto("a@example.com")) is None


# ───────────────────────── Hash señuelo (INV-009, M-5) ─────────────────────────

def test_inv009_hash_senuelo_tiene_el_mismo_costo_que_un_hash_real():
    real = security.get_password_hash("Clave12345")
    assert security.HASH_SENUELO.startswith("$2") and security.HASH_SENUELO.split("$")[2] == real.split("$")[2]
    assert len(security.HASH_SENUELO) == len(real)
    assert security.verify_password_senuelo("Clave12345") is False
    assert security.verify_password_senuelo("") is False


def test_inv009_verify_password_senuelo_pasa_por_verify_password(monkeypatch):
    llamadas = []
    monkeypatch.setattr(security, "verify_password", lambda p, h: llamadas.append(h) or False)
    security.verify_password_senuelo("x")
    assert llamadas == [security.HASH_SENUELO]


# ───────────────────────── Limitador persistente por IP (INV-010, INV-039, INV-040) ─────────────────────────

class _Req:
    def __init__(self, ip):
        self.headers = {"x-forwarded-for": f"{ip}, 10.0.0.1"}
        self.client = None


def test_inv010_limitador_persistente_responde_429_al_superar_el_limite(reloj):
    estados = []
    for _ in range(31):
        try:
            run(rate_limit.enforce_persistente(rate_limit.ip_intentos_auth, _Req(IP), "Demasiadas solicitudes."))
            estados.append(200)
        except HTTPException as e:
            estados.append(e.status_code)
    assert estados == [200] * 30 + [429]
    run(rate_limit.enforce_persistente(rate_limit.ip_intentos_auth, _Req("198.51.100.99"), "x"))   # otra IP


def test_inv010_los_dos_limitadores_de_auth_tienen_los_numeros_de_la_spec():
    assert (rate_limit.ip_pedidos_codigo.limit, rate_limit.ip_pedidos_codigo.window) == (10, 3600)
    assert (rate_limit.ip_intentos_auth.limit, rate_limit.ip_intentos_auth.window) == (30, 600)
    assert rate_limit.ip_pedidos_codigo.tipo != rate_limit.ip_intentos_auth.tipo


def test_inv039_fallo_del_limite_por_ip_no_deja_pasar(bd):
    bd(ClienteFalso(falla=RuntimeError("x")))
    with pytest.raises(ae.EstadoNoDisponible):
        run(rate_limit.enforce_persistente(rate_limit.ip_pedidos_codigo, _Req(IP), "x"))


def test_inv040_limite_lleno_responde_429_con_aviso_sin_datos(bd, capsys):
    bd(ClienteFalso({"auth_limite_registrar": "lleno"}))
    with pytest.raises(HTTPException) as e:
        run(rate_limit.enforce_persistente(rate_limit.ip_pedidos_codigo, _Req(IP), "Demasiadas solicitudes."))
    assert e.value.status_code == 429
    salida = capsys.readouterr()
    assert "tope" in salida.out and IP not in salida.out + salida.err


def test_los_limitadores_de_los_demas_usos_siguen_en_memoria():
    sw = rate_limit.SlidingWindow(limit=2, window_seconds=60)
    assert sw.hit("k") and sw.hit("k") and not sw.hit("k")
