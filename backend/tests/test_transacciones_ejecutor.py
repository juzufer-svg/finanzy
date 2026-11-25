"""CHG-026 · BL-043 · ADR-009 punto 14: ejecutor PROPIO y acotado de `TransaccionDB` (mismo patrón que cuentas).

Con cliente falso: hilos propios (`transacciones`), 503 inmediato sin encolar, hueco liberado en éxito/excepción/cancelación,
no-interferencia con login y cuentas, y la traducción FZ001/FZ002 → 409 y 22003 → 422 intacta, sin texto de la BD."""
import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from app.models import auth_estado, plataapp as modelos, transacciones_ejecutor as tx_mod
from app.models.auth_estado import EstadoNoDisponible, MENSAJE_503
from app.models.plataapp import TransaccionDB
from conftest import auth_header

A = auth_header("user-a")
URL = "/api/v1/transacciones"
TID = "00000000-0000-4000-8000-000000000001"
FILA_TX = {"id": TID, "usuario_id": "user-a", "categoria_id": None, "monto": 5, "descripcion": "", "fecha": "2026-11-22",
           "tipo": "gasto", "medio_pago": None, "cuenta_id": None}
CUERPO = {"categoria_id": "", "monto": 5, "descripcion": "x", "fecha": "2026-11-22", "tipo": "gasto"}


class _ErrorPG(Exception):
    def __init__(self, code):
        super().__init__("secreto-de-la-bd id=7a3f")
        self.code, self.message = code, "secreto-de-la-bd id=7a3f"


class _Consulta:
    def __init__(self, cliente, tabla):
        self.cliente, self.tabla, self.llamadas = cliente, tabla, []

    def __getattr__(self, nombre):
        def registrar(*args, **kwargs):
            self.llamadas.append((nombre, args))
            return self
        return registrar

    def execute(self):
        return SimpleNamespace(data=self.cliente.fuente(self))

    def valor(self, nombre):
        return [a for n, a in self.llamadas if n == nombre]


class _Cliente:
    def __init__(self, fuente):
        self.fuente = fuente

    def table(self, nombre):
        return _Consulta(self, nombre)

    def rpc(self, nombre, args):
        return _Consulta(self, "rpc:" + nombre)


def _con_cliente(monkeypatch, fuente):
    """Solo el cliente DEDICADO con plazo: el general (`SupabaseDB.get_client`) no debe usarse para transacciones."""
    def general():
        raise AssertionError("TransaccionDB no debe usar el cliente general sin plazo")
    monkeypatch.setattr(auth_estado, "_modo", lambda: "bd")
    monkeypatch.setattr(auth_estado, "_cliente_estado", _Cliente(fuente))
    monkeypatch.setattr(modelos, "_supabase_ok", lambda: True)
    monkeypatch.setattr(modelos.SupabaseDB, "get_client", staticmethod(general))


def _fuente_lenta(espera, hilos, falla=None):
    def fuente(q):
        hilos.append(threading.current_thread().name)
        time.sleep(espera)
        if falla:
            raise falla
        return [FILA_TX]
    return fuente


def _huecos():
    return tx_mod._huecos._value


def _esperar_huecos(n, plazo=3.0):
    fin = time.monotonic() + plazo
    while _huecos() != n and time.monotonic() < fin:
        time.sleep(0.01)
    return _huecos()


def test_ejecutor_propio_de_4_hilos_llamados_transacciones_no_auth_estado_ni_cuentas(client, monkeypatch):
    from app.models import cuentas as cuentas_mod
    hilos = []
    _con_cliente(monkeypatch, _fuente_lenta(0, hilos))
    assert tx_mod.MAX_HILOS_TRANSACCIONES == 4
    assert tx_mod._ejecutor is not auth_estado._ejecutor and tx_mod._ejecutor is not cuentas_mod._ejecutor
    assert client.get(URL, headers=A).status_code == 200
    assert client.get(f"{URL}/{TID}", headers=A).status_code == 200
    assert client.post(URL, json=CUERPO, headers=A).status_code == 200
    assert client.put(f"{URL}/{TID}", json=CUERPO, headers=A).status_code == 200
    assert client.delete(f"{URL}/{TID}", headers=A).status_code == 200
    assert hilos and all(h.startswith("transacciones") and "auth-estado" not in h and "cuentas" not in h for h in hilos)


def test_sin_hueco_503_inmediato_sin_encolar_ni_llamar_a_la_bd(client, monkeypatch):
    hilos = []
    _con_cliente(monkeypatch, _fuente_lenta(0, hilos))
    tomados = 0
    while tx_mod._huecos.acquire(blocking=False):
        tomados += 1
    try:
        inicio = time.monotonic()
        for r in (client.get(URL, headers=A), client.post(URL, json=CUERPO, headers=A), client.delete(f"{URL}/{TID}", headers=A)):
            assert r.status_code == 503 and r.json() == {"detail": MENSAJE_503}
        assert time.monotonic() - inicio < 1.0 and hilos == []
    finally:
        for _ in range(tomados):
            tx_mod._huecos.release()


def test_el_hueco_se_libera_tras_terminar_tras_excepcion_y_tras_cancelacion(monkeypatch):
    base = _huecos()
    hilos = []
    _con_cliente(monkeypatch, _fuente_lenta(0, hilos))
    assert len(asyncio.run(TransaccionDB.obtener_por_usuario("user-a"))) == 1
    assert _esperar_huecos(base) == base                       # tras terminar
    _con_cliente(monkeypatch, _fuente_lenta(0, hilos, RuntimeError("secreto")))
    with pytest.raises(EstadoNoDisponible):
        asyncio.run(TransaccionDB.obtener_por_usuario("user-a"))
    assert _esperar_huecos(base) == base                       # tras excepción
    _con_cliente(monkeypatch, _fuente_lenta(0.5, hilos))

    async def cancelar():
        tarea = asyncio.create_task(TransaccionDB.obtener_por_usuario("user-a"))
        await asyncio.sleep(0.1)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea
    asyncio.run(cancelar())
    assert _esperar_huecos(base) == base                       # tras cancelación (al terminar el hilo)


def test_no_interfiere_con_login_ni_con_cuentas_con_4_llamadas_lentas_de_transacciones(client, users, monkeypatch):
    from app.models import cuentas as cuentas_mod
    from app.models.user import UserDB
    hilos = []
    _con_cliente(monkeypatch, _fuente_lenta(0.8, hilos))
    monkeypatch.setattr(auth_estado, "_modo", lambda: "memoria")   # el login usa su almacén
    monkeypatch.setattr(cuentas_mod, "_modo", lambda: "bd")        # cuentas usa el cliente falso
    asyncio.run(UserDB.create("otra@x.com", "Clave-123456", is_active=True))

    async def tormenta():
        return await asyncio.gather(*[TransaccionDB.obtener_por_usuario("user-a") for _ in range(8)], return_exceptions=True)
    resultado = []
    hilo = threading.Thread(target=lambda: resultado.extend(asyncio.run(tormenta())))
    hilo.start()
    time.sleep(0.2)
    r = client.post("/api/v1/auth/login", json={"email": "otra@x.com", "password": "Clave-123456"})
    assert r.status_code == 200 and r.json()["access_token"]
    assert asyncio.run(auth_estado.ejecutar("sonda", lambda: "ok")) == "ok"                       # auth-estado, libre
    assert asyncio.run(cuentas_mod._llamar("sonda", lambda: "ok")) == "ok"                         # cuentas, libre
    hilo.join()
    assert sum(isinstance(x, EstadoNoDisponible) for x in resultado) == 4     # 4 corren, 4 sin hueco = 503
    assert len(hilos) == 4 and all(h.startswith("transacciones") for h in hilos)
    _esperar_huecos(tx_mod.MAX_HILOS_TRANSACCIONES)


@pytest.mark.parametrize("metodo,codigo,estado,texto", [
    (m, c, e, t) for m in ("post", "put", "delete")
    for c, e, t in (("FZ001", 409, "Saldo insuficiente"), ("FZ002", 409, "archivada"), ("22003", 422, "demasiado grande"))
    if not (m == "delete" and c == "22003")])   # 22003 no aplica al borrado
def test_fz_a_409_y_22003_a_422_siguen_intactos_sin_texto_de_la_bd(client, monkeypatch, capsys, metodo, codigo, estado, texto):
    def fuente(q):
        if q.tabla == "transacciones" and (q.valor("insert") or q.valor("update") or q.valor("delete")):
            raise _ErrorPG(codigo)
        return [FILA_TX]
    _con_cliente(monkeypatch, fuente)
    if metodo == "post":
        r = client.post(URL, json=CUERPO, headers=A)
    elif metodo == "put":
        r = client.put(f"{URL}/{TID}", json=CUERPO, headers=A)
    else:
        r = client.delete(f"{URL}/{TID}", headers=A)
    assert r.status_code == estado and texto in r.json()["detail"]
    assert "secreto" not in r.text and "7a3f" not in r.text
    assert "secreto" not in capsys.readouterr().out


def test_un_fallo_de_la_bd_es_503_generico_sin_datos_en_respuesta_ni_logs(client, monkeypatch, capsys):
    def roto(q):
        raise RuntimeError("secreto host-interno 10.0.0.7 password=abc")
    _con_cliente(monkeypatch, roto)
    for r in (client.get(URL, headers=A), client.get(f"{URL}/{TID}", headers=A), client.post(URL, json=CUERPO, headers=A)):
        assert r.status_code == 503 and r.json() == {"detail": MENSAJE_503}
        assert "secreto" not in r.text
    assert "secreto" not in capsys.readouterr().out
    _con_cliente(monkeypatch, lambda q: {"no": "es una lista"})   # respuesta inesperada: también 503
    assert client.get(URL, headers=A).status_code == 503
