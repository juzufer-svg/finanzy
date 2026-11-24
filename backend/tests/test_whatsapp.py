"""CHG-014 · REQ-F-017 · INV-029, INV-030: registrar ingresos y gastos por WhatsApp con IA (BDD-WHATSAPP).

La API de Claude y el envío a Meta se simulan: no se hace ninguna llamada real.
"""
import hashlib
import hmac
import json
from datetime import datetime

import pytest

from app.core.config import settings
from app.utils import whatsapp as wa
from conftest import auth_header

A = auth_header("user-a")
B = auth_header("user-b")
SECRETO = "secreto-de-la-app-de-meta"
TEL_A = "573001112233"
TEL_B = "573004445566"


@pytest.fixture
def meta(monkeypatch):
    """Configura WhatsApp, simula Claude (respuestas en cola) y registra los mensajes enviados."""
    monkeypatch.setattr(settings, "WHATSAPP_TOKEN", "token")
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", SECRETO)
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "palabra-secreta")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "clave")
    estado = {"enviados": [], "claude": [], "payloads": []}

    async def enviar(telefono, texto):
        estado["enviados"].append((telefono, texto))
        return True

    async def claude(payload, origen="asistente"):
        estado["payloads"].append(payload)
        if not estado["claude"]:
            raise AssertionError("Se llamó a Claude sin una respuesta preparada")
        r = estado["claude"].pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(wa, "enviar", enviar)
    monkeypatch.setattr(wa, "llamar_claude", claude)
    return estado


def herramienta(nombre, entrada):
    return {"content": [{"type": "tool_use", "id": "t1", "name": nombre, "input": entrada}], "stop_reason": "tool_use"}


def texto_claude(t):
    return {"content": [{"type": "text", "text": t}], "stop_reason": "end_turn"}


def _webhook(client, mensajes, firma=True, cuerpo=None):
    payload = {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "123"},
        "messages": [{"id": mid, "from": de, "timestamp": "1", "type": "text", "text": {"body": texto}}
                     for mid, de, texto in mensajes]}}]}]}
    raw = cuerpo if cuerpo is not None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if firma:
        headers["X-Hub-Signature-256"] = "sha256=" + hmac.new(SECRETO.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/v1/whatsapp/webhook", content=raw, headers=headers)


_n = {"i": 0}


def _msg(client, texto, de=TEL_A):
    _n["i"] += 1
    r = _webhook(client, [(f"wamid.{_n['i']}", de, texto)])
    assert r.status_code == 200
    return r


def _enlazar(client, meta, headers=A, tel=TEL_A):
    codigo = client.post("/api/v1/whatsapp/enlace", headers=headers).json()["codigo"]
    _msg(client, codigo, de=tel)
    assert "conectado" in meta["enviados"][-1][1]


def _tx(client, headers=A):
    return client.get("/api/v1/transacciones", headers=headers).json()


def _cat(client, nombre, headers=A):
    return next(c for c in client.get("/api/v1/categorias", headers=headers).json() if c["nombre"] == nombre)


# ── Verificación de Meta ──────────────────────────────────────────────────────

def test_verificacion_del_webhook(client, meta):
    ok = client.get("/api/v1/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "palabra-secreta", "hub.challenge": "1158201444"})
    assert ok.status_code == 200 and ok.text == "1158201444"
    malo = client.get("/api/v1/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "otra", "hub.challenge": "1"})
    assert malo.status_code == 403


def test_sin_configurar_la_verificacion_siempre_falla(client):
    r = client.get("/api/v1/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"})
    assert r.status_code == 403


@pytest.mark.parametrize("firma", ["", "sha256=deadbeef", "md5=abc"])
def test_inv029_firma_invalida_se_rechaza_y_no_procesa(client, meta, firma):
    raw = json.dumps({"entry": []}).encode()
    r = client.post("/api/v1/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": firma})
    assert r.status_code == 403 and meta["enviados"] == [] and meta["payloads"] == []


def test_inv029_sin_app_secret_nada_se_acepta(client, meta, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "")
    assert _webhook(client, [("w1", TEL_A, "hola")]).status_code == 403


# ── Enlace del número ─────────────────────────────────────────────────────────

def test_enlazar_con_el_codigo_y_ver_el_estado(client, meta):
    assert client.get("/api/v1/whatsapp/enlace", headers=A).json() == {"configurado": True, "enlazado": False, "telefono": None}
    _enlazar(client, meta)
    assert client.get("/api/v1/whatsapp/enlace", headers=A).json() == {"configurado": True, "enlazado": True, "telefono": "•••• 2233"}
    # Desconectar
    assert client.delete("/api/v1/whatsapp/enlace", headers=A).status_code == 200
    assert client.get("/api/v1/whatsapp/enlace", headers=A).json()["enlazado"] is False


def test_codigo_de_un_solo_uso_y_codigo_invalido(client, meta):
    codigo = client.post("/api/v1/whatsapp/enlace", headers=A).json()["codigo"]
    _msg(client, codigo, de=TEL_A)
    _msg(client, codigo, de=TEL_B)   # ya usado
    assert "no es válido" in meta["enviados"][-1][1]
    assert client.get("/api/v1/whatsapp/enlace", headers=A).json()["telefono"] == "•••• 2233"


def test_codigo_vencido_no_enlaza(client, meta, monkeypatch):
    codigo = client.post("/api/v1/whatsapp/enlace", headers=A).json()["codigo"]
    reloj = wa.time.time() + wa.CODIGO_MINUTOS * 60 + 1
    monkeypatch.setattr(wa.time, "time", lambda: reloj)
    _msg(client, codigo)
    assert "no es válido" in meta["enviados"][-1][1]
    assert client.get("/api/v1/whatsapp/enlace", headers=A).json()["enlazado"] is False


def test_intentos_de_codigo_limitados_por_numero(client, meta):
    for i in range(7):
        _msg(client, f"FZ-{i:06d}", de=TEL_B)
    assert len(meta["enviados"]) == 5   # del sexto en adelante ni siquiera se responde


def test_generar_codigo_sin_configurar_es_503(client):
    assert client.post("/api/v1/whatsapp/enlace", headers=A).status_code == 503
    assert client.get("/api/v1/whatsapp/enlace", headers=A).json()["configurado"] is False


def test_enlace_requiere_sesion(client):
    assert client.post("/api/v1/whatsapp/enlace", headers={"Authorization": "Bearer x"}).status_code == 401


# ── INV-029: quién puede usarlo ───────────────────────────────────────────────

def test_inv029_numero_no_enlazado_se_ignora_sin_llamar_a_la_ia(client, meta):
    _msg(client, "gasté 20 mil en mercado", de=TEL_B)
    assert meta["payloads"] == [] and meta["enviados"] == [] and _tx(client) == [] and _tx(client, B) == []


def test_inv029_cada_numero_registra_solo_en_su_cuenta(client, meta):
    _enlazar(client, meta, A, TEL_A)
    _enlazar(client, meta, B, TEL_B)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": 5000, "fecha": "2026-11-23"}]}))
    _msg(client, "5 mil de tinto", de=TEL_B)
    assert len(_tx(client, B)) == 1 and _tx(client) == []


def test_inv029_a_la_ia_no_se_envian_telefono_ni_ids(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(texto_claude("¡Hola! Cuéntame tus gastos."))
    _msg(client, "hola")
    enviado = json.dumps(meta["payloads"][-1])
    assert TEL_A not in enviado and "user-a" not in enviado


def test_inv029_mensaje_repetido_por_meta_se_procesa_una_vez(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": 18000, "fecha": "2026-11-23"}]}))
    for _ in range(3):
        _webhook(client, [("wamid.repetido", TEL_A, "almorcé por 18 mil")])
    assert len(_tx(client)) == 1 and len(meta["payloads"]) == 1


# ── Registro con IA ───────────────────────────────────────────────────────────

def test_registra_un_gasto_con_categoria_y_medio(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 85000, "fecha": "2026-11-22", "categoria": "hogar", "medio_pago": "credito", "descripcion": "Internet"}]}))
    _msg(client, "ayer pagué 85 mil de internet con la tarjeta")
    tx = _tx(client)
    assert len(tx) == 1
    t = tx[0]
    assert (t["tipo"], t["monto"], t["fecha"], t["medio_pago"], t["descripcion"], t["categoria_id"]) == \
        ("gasto", 85000, "2026-11-22", "credito", "Internet", _cat(client, "Hogar")["id"])
    assert "Gasto registrado: $85.000 · Hogar · Crédito" in meta["enviados"][-1][1] and "deshacer" in meta["enviados"][-1][1]


def test_varios_movimientos_en_un_mensaje(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 18000, "fecha": "2026-11-23", "categoria": "Comida"},
        {"tipo": "gasto", "monto": 6000, "fecha": "2026-11-23", "categoria": "Transporte"}]}))
    _msg(client, "almorcé por 18 mil y 6 de taxi")
    assert sorted(t["monto"] for t in _tx(client)) == [6000, 18000]
    assert "2 movimientos registrados" in meta["enviados"][-1][1]


def test_categoria_que_no_existe_queda_sin_categoria(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "ingreso", "monto": 2100000, "fecha": "2026-11-23", "categoria": "Inventada"}]}))
    _msg(client, "me llegó plata")
    assert _tx(client)[0]["categoria_id"] in (None, "")
    assert "Sin categoría" in meta["enviados"][-1][1]


def test_inv002_la_ia_no_puede_usar_una_categoria_de_otro_usuario(client, meta):
    ajena = client.post("/api/v1/categorias", json={"nombre": "Secreta", "tipo": "gasto"}, headers=B).json()
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 1000, "fecha": "2026-11-23", "categoria": "Secreta"}]}))
    _msg(client, "1000 en secreta")
    assert _tx(client)[0]["categoria_id"] in (None, "") and _tx(client)[0]["categoria_id"] != ajena["id"]


@pytest.mark.parametrize("movimiento", [
    {"tipo": "gasto", "monto": 0, "fecha": "2026-11-23"},
    {"tipo": "gasto", "monto": -500, "fecha": "2026-11-23"},
    {"tipo": "gasto", "monto": 2e12, "fecha": "2026-11-23"},
    {"tipo": "gasto", "monto": "mucho", "fecha": "2026-11-23"},
    {"tipo": "prestamo", "monto": 1000, "fecha": "2026-11-23"},
])
def test_inv029_lo_que_propone_la_ia_se_valida_y_no_se_guarda_si_es_invalido(client, meta, movimiento):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [movimiento]}))
    _msg(client, "algo raro")
    assert _tx(client) == []
    assert "repites" in meta["enviados"][-1][1]


def test_si_un_movimiento_es_invalido_no_se_guarda_ninguno(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 1000, "fecha": "2026-11-23"}, {"tipo": "gasto", "monto": 0, "fecha": "2026-11-23"}]}))
    _msg(client, "dos cosas")
    assert _tx(client) == []


@pytest.mark.parametrize("fecha", ["2030-01-01", "2020-01-01", "ayer", "2026-02-30"])
def test_fechas_absurdas_o_invalidas_se_guardan_como_hoy(client, meta, fecha):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": 1000, "fecha": fecha}]}))
    _msg(client, "mil pesos")
    hoy = datetime.now(wa.ZONA_COLOMBIA).date().isoformat()
    assert _tx(client)[0]["fecha"] == hoy


def test_medio_de_pago_desconocido_queda_sin_especificar(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": 1000, "fecha": "2026-11-23", "medio_pago": "bitcoin"}]}))
    _msg(client, "mil en bitcoin")
    assert _tx(client)[0]["medio_pago"] is None


def test_si_falta_el_monto_la_ia_pregunta_y_no_registra(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(texto_claude("¿Cuánto gastaste en el mercado?"))
    _msg(client, "gasté plata en el mercado")
    assert _tx(client) == [] and meta["enviados"][-1][1] == "¿Cuánto gastaste en el mercado?"


def test_la_ia_recibe_las_categorias_la_fecha_y_la_conversacion_reciente(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(texto_claude("¿Cuánto fue?"))
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": 80000, "fecha": "2026-11-23"}]}))
    _msg(client, "pagué el mercado")
    _msg(client, "80 mil")
    segundo = meta["payloads"][-1]
    assert "Comida" in segundo["system"] and "Hoy es" in segundo["system"]
    assert [m["role"] for m in segundo["messages"]] == ["user", "assistant", "user"]
    assert segundo["messages"][0]["content"] == "pagué el mercado"
    assert {h["name"] for h in segundo["tools"]} == {"registrar_movimientos", "deshacer_ultimo", "corregir_ultimo"}


def test_ayuda_no_gasta_ia(client, meta):
    _enlazar(client, meta)
    _msg(client, "ayuda")
    assert meta["payloads"] == [] and "deshacer" in meta["enviados"][-1][1]


def test_si_la_ia_falla_no_se_registra_nada_y_se_avisa(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(wa.AsistenteError(503, "sin saldo"))
    _msg(client, "gasté 20 mil")
    assert _tx(client) == [] and "No se registró nada" in meta["enviados"][-1][1]


def test_sin_clave_de_ia_se_avisa_sin_llamar(client, meta, monkeypatch):
    _enlazar(client, meta)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    _msg(client, "gasté 20 mil")
    assert meta["payloads"] == [] and "no está configurada" in meta["enviados"][-1][1]


# ── Deshacer y corregir ───────────────────────────────────────────────────────

def test_deshacer_borra_solo_lo_ultimo_registrado_por_whatsapp(client, meta):
    _enlazar(client, meta)
    client.post("/api/v1/transacciones", json={"monto": 999, "fecha": "2026-11-20", "tipo": "gasto"}, headers=A)  # desde la app
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": 1000, "fecha": "2026-11-23"}]}))
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 2000, "fecha": "2026-11-23"}, {"tipo": "gasto", "monto": 3000, "fecha": "2026-11-23"}]}))
    meta["claude"].append(herramienta("deshacer_ultimo", {}))
    meta["claude"].append(herramienta("deshacer_ultimo", {}))
    meta["claude"].append(herramienta("deshacer_ultimo", {}))
    _msg(client, "mil")
    _msg(client, "dos mil y tres mil")
    _msg(client, "deshacer")
    assert sorted(t["monto"] for t in _tx(client)) == [999, 1000] and "Deshecho" in meta["enviados"][-1][1]
    _msg(client, "deshacer")
    assert [t["monto"] for t in _tx(client)] == [999]
    _msg(client, "deshacer")   # lo hecho desde la app nunca se toca
    assert [t["monto"] for t in _tx(client)] == [999] and "nada reciente" in meta["enviados"][-1][1]


def test_corregir_el_monto_de_lo_ultimo(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 85000, "fecha": "2026-11-23", "categoria": "Hogar", "medio_pago": "debito"}]}))
    meta["claude"].append(herramienta("corregir_ultimo", {"monto": 80000}))
    _msg(client, "85 mil de internet")
    _msg(client, "no, eran 80 mil")
    t = _tx(client)[0]
    assert (t["monto"], t["medio_pago"], t["categoria_id"]) == (80000, "debito", _cat(client, "Hogar")["id"])
    assert "Corregido" in meta["enviados"][-1][1] and "$80.000" in meta["enviados"][-1][1]


def test_corregir_el_segundo_de_varios(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 18000, "fecha": "2026-11-23"}, {"tipo": "gasto", "monto": 6000, "fecha": "2026-11-23"}]}))
    meta["claude"].append(herramienta("corregir_ultimo", {"numero": 2, "medio_pago": "efectivo"}))
    _msg(client, "18 mil y 6 mil")
    _msg(client, "el taxi fue en efectivo")
    medios = {t["monto"]: t["medio_pago"] for t in _tx(client)}
    assert medios == {18000: None, 6000: "efectivo"}


def test_corregir_con_monto_invalido_no_cambia_nada(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": 5000, "fecha": "2026-11-23"}]}))
    meta["claude"].append(herramienta("corregir_ultimo", {"monto": -1}))
    _msg(client, "5 mil")
    _msg(client, "eran menos uno")
    assert _tx(client)[0]["monto"] == 5000


def test_inv029_deshacer_de_un_numero_no_toca_lo_de_otra_cuenta(client, meta):
    _enlazar(client, meta, A, TEL_A)
    _enlazar(client, meta, B, TEL_B)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": 7000, "fecha": "2026-11-23"}]}))
    meta["claude"].append(herramienta("deshacer_ultimo", {}))
    _msg(client, "7 mil", de=TEL_A)
    _msg(client, "deshacer", de=TEL_B)
    assert len(_tx(client)) == 1


# ── INV-030: topes de costo ───────────────────────────────────────────────────

def test_inv030_tope_diario_por_usuario(client, meta, monkeypatch):
    from app.api.routes import whatsapp as rutas
    monkeypatch.setattr(rutas._por_usuario_dia, "limit", 3)
    monkeypatch.setattr(rutas._por_minuto, "limit", 100)
    _enlazar(client, meta)
    for _ in range(3):
        meta["claude"].append(texto_claude("ok"))
    for _ in range(5):
        _msg(client, "hola")
    assert len(meta["payloads"]) == 3
    avisos = [t for _, t in meta["enviados"] if "límite" in t]
    assert len(avisos) == 1   # se avisa una sola vez


def test_inv030_tope_por_minuto(client, meta):
    _enlazar(client, meta)
    for _ in range(10):
        meta["claude"].append(texto_claude("ok"))
    for _ in range(12):
        _msg(client, "hola")
    assert len(meta["payloads"]) == 10


def test_inv030_valores_por_defecto():
    assert settings.WHATSAPP_MENSAJES_POR_DIA == 50 and wa.MAX_TOKENS <= 600 and wa.MAX_MOVIMIENTOS == 10


# ── Formatos ──────────────────────────────────────────────────────────────────

def test_formato_de_pesos():
    assert wa.pesos(85000) == "$85.000"
    assert wa.pesos(2100000) == "$2.100.000"
    assert wa.pesos(1234.5) == "$1.234,50"


def test_mensajes_que_no_son_texto_se_responden_sin_ia(client, meta):
    _enlazar(client, meta)
    payload = {"entry": [{"changes": [{"value": {"messages": [{"id": "wamid.audio", "from": TEL_A, "type": "audio", "audio": {}}]}}]}]}
    raw = json.dumps(payload).encode()
    firma = "sha256=" + hmac.new(SECRETO.encode(), raw, hashlib.sha256).hexdigest()
    client.post("/api/v1/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": firma})
    assert meta["payloads"] == [] and "solo entiendo mensajes de texto" in meta["enviados"][-1][1]


# ── Revisión independiente de CHG-014 ─────────────────────────────────────────

def test_h1_corregir_con_campos_vacios_no_borra_lo_que_tenia(client, meta):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 85000, "fecha": "2026-11-20", "categoria": "Hogar", "medio_pago": "credito", "descripcion": "Internet"}]}))
    meta["claude"].append(herramienta("corregir_ultimo", {"monto": 80000, "categoria": "", "medio_pago": "", "fecha": "", "descripcion": "  "}))
    _msg(client, "85 mil de internet el 20")
    _msg(client, "no, eran 80 mil")
    t = _tx(client)[0]
    assert (t["monto"], t["categoria_id"], t["medio_pago"], t["fecha"], t["descripcion"]) == \
        (80000, _cat(client, "Hogar")["id"], "credito", "2026-11-20", "Internet")


def test_h2_cambiar_la_contrasena_desconecta_whatsapp(client, meta, users):
    from app.core import security
    users["ana@example.com"] = {"id": "user-a", "email": "ana@example.com", "hashed_password": security.get_password_hash("Vieja1234"),
                                "is_active": True, "full_name": "Ana", "currency": "COP", "session_version": 0}
    _enlazar(client, meta)
    r = client.post("/api/v1/users/me/password", json={"actual": "Vieja1234", "nueva": "NuevaClave1"}, headers=A)
    assert r.status_code == 200
    nueva = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/api/v1/whatsapp/enlace", headers=nueva).json()["enlazado"] is False
    _msg(client, "gasté 10 mil")   # el número ya no puede registrar
    assert meta["payloads"] == []


def test_h2_restablecer_la_contrasena_desconecta_whatsapp(client, meta, users, sent_emails):
    from app.core import security
    from conftest import ip
    users["ana@example.com"] = {"id": "user-a", "email": "ana@example.com", "hashed_password": security.get_password_hash("Vieja1234"),
                                "is_active": True, "full_name": "Ana", "currency": "COP", "session_version": 0}
    _enlazar(client, meta)
    client.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"}, headers=ip(1))
    code = [s for s in sent_emails if s[2] == "reset"][-1][1]
    r = client.post("/api/v1/auth/reset-password", json={"email": "ana@example.com", "code": code, "new_password": "NuevaClave1"}, headers=ip(1))
    assert r.status_code == 200
    from app.models.whatsapp import _Memoria
    assert "user-a" not in _Memoria.enlaces


def test_h3_si_falla_a_mitad_del_lote_no_queda_nada_y_se_avisa(client, meta, monkeypatch):
    from app.models import plataapp as modelos
    _enlazar(client, meta)
    original = modelos.TransaccionDB.crear
    llamadas = {"n": 0}

    async def falla_en_la_segunda(*args, **kwargs):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise RuntimeError("Supabase caído")
        return await original(*args, **kwargs)

    monkeypatch.setattr(modelos.TransaccionDB, "crear", staticmethod(falla_en_la_segunda))
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 1000, "fecha": "2026-11-23"}, {"tipo": "gasto", "monto": 2000, "fecha": "2026-11-23"}]}))
    _msg(client, "mil y dos mil")
    monkeypatch.setattr(modelos.TransaccionDB, "crear", staticmethod(original))
    assert _tx(client) == [] and "No se registró nada" in meta["enviados"][-1][1]


def test_h3_un_error_inesperado_se_avisa_al_numero_enlazado(client, meta, monkeypatch):
    _enlazar(client, meta)

    async def explota(*args, **kwargs):
        raise RuntimeError("inesperado")

    monkeypatch.setattr(wa, "responder", explota)
    _msg(client, "gasté 5 mil")
    assert "error del servidor" in meta["enviados"][-1][1]


def test_h4_un_codigo_nunca_reemplaza_el_de_otra_persona(monkeypatch):
    secuencia = iter([123456, 123456, 654321])
    monkeypatch.setattr(wa.secrets, "randbelow", lambda n: next(secuencia))
    assert wa.nuevo_codigo("user-a") == "FZ-123456"
    assert wa.nuevo_codigo("user-b") == "FZ-654321"
    assert wa.usar_codigo("FZ-123456") == "user-a"


def test_h5_ayuda_no_gasta_cupo_ni_requiere_clave_de_ia(client, meta, monkeypatch):
    from app.api.routes import whatsapp as rutas
    _enlazar(client, meta)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(rutas._por_usuario_dia, "limit", 1)
    for _ in range(3):
        _msg(client, "ayuda")
    assert all("deshacer" in t for _, t in meta["enviados"][1:]) and meta["payloads"] == []


def test_h6_el_tope_global_tiene_su_propio_aviso(client, meta, monkeypatch):
    from app.api.routes import whatsapp as rutas
    monkeypatch.setattr(rutas._global_dia, "limit", 0)
    _enlazar(client, meta)
    _msg(client, "hola")
    assert "registro por WhatsApp alcanzó su límite" in meta["enviados"][-1][1]


@pytest.mark.parametrize("monto", ["85.000", "85000", True, None])
def test_h7_monto_que_no_es_numero_se_rechaza(client, meta, monto):
    _enlazar(client, meta)
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [{"tipo": "gasto", "monto": monto, "fecha": "2026-11-23"}]}))
    _msg(client, "algo")
    assert _tx(client) == []


def test_h9_numero_desconocido_no_deja_rastro(client, meta):
    from app.models.whatsapp import _Memoria
    _msg(client, "spam", de="570000000000")
    assert _Memoria.mensajes == set()


@pytest.mark.parametrize("payload", [
    {"entry": {"no": "es lista"}},
    {"entry": [{"changes": "texto"}]},
    {"entry": [{"changes": [{"value": {"messages": [{"id": "x", "from": "1", "type": "text", "text": "no es objeto"}]}}]}]},
    ["lista"],
])
def test_h10_payloads_raros_no_rompen_el_webhook(client, meta, payload):
    raw = json.dumps(payload).encode()
    firma = "sha256=" + hmac.new(SECRETO.encode(), raw, hashlib.sha256).hexdigest()
    assert client.post("/api/v1/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": firma}).status_code == 200


def test_h10_mensajes_de_otro_numero_de_meta_se_ignoran(client, meta):
    _enlazar(client, meta)
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "999"},
                                                 "messages": [{"id": "wamid.otro", "from": TEL_A, "type": "text", "text": {"body": "hola"}}]}}]}]}
    raw = json.dumps(payload).encode()
    firma = "sha256=" + hmac.new(SECRETO.encode(), raw, hashlib.sha256).hexdigest()
    client.post("/api/v1/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": firma})
    assert meta["payloads"] == [] and len(meta["enviados"]) == 1   # solo la confirmación del enlace


# ── Revisión independiente de CHG-014, ciclo 2 ────────────────────────────────

def _ana(users):
    from app.core import security
    users["ana@example.com"] = {"id": "user-a", "email": "ana@example.com", "hashed_password": security.get_password_hash("Vieja1234"),
                                "is_active": True, "full_name": "Ana", "currency": "COP", "session_version": 0}


def test_inv016_si_no_se_puede_desconectar_whatsapp_no_cambia_la_contrasena(client, meta, users, monkeypatch):
    from app.models.whatsapp import WhatsappDB
    _ana(users)
    _enlazar(client, meta)

    async def falla(*args):
        raise RuntimeError("Supabase caído")

    monkeypatch.setattr(WhatsappDB, "desenlazar", staticmethod(falla))
    r = client.post("/api/v1/users/me/password", json={"actual": "Vieja1234", "nueva": "NuevaClave1"}, headers=A)
    assert r.status_code == 503 and users["ana@example.com"]["session_version"] == 0


def test_inv016_restablecer_tampoco_cambia_nada_si_no_se_puede_desconectar(client, meta, users, sent_emails, monkeypatch):
    from app.core import security
    from app.models.whatsapp import WhatsappDB
    from conftest import ip
    _ana(users)
    _enlazar(client, meta)
    client.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"}, headers=ip(1))
    code = [s for s in sent_emails if s[2] == "reset"][-1][1]

    async def falla(*args):
        raise RuntimeError("Supabase caído")

    monkeypatch.setattr(WhatsappDB, "desenlazar", staticmethod(falla))
    r = client.post("/api/v1/auth/reset-password", json={"email": "ana@example.com", "code": code, "new_password": "NuevaClave1"}, headers=ip(1))
    assert r.status_code == 503
    assert security.verify_password("Vieja1234", users["ana@example.com"]["hashed_password"])


def test_si_tambien_falla_la_reversion_no_se_afirma_que_no_se_registro_nada(client, meta, monkeypatch):
    from app.models import plataapp as modelos
    _enlazar(client, meta)
    original = modelos.TransaccionDB.crear
    llamadas = {"n": 0}

    async def falla_en_la_segunda(*args, **kwargs):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise RuntimeError("Supabase caído")
        return await original(*args, **kwargs)

    async def no_borra(*args, **kwargs):
        raise RuntimeError("Supabase caído")

    monkeypatch.setattr(modelos.TransaccionDB, "crear", staticmethod(falla_en_la_segunda))
    monkeypatch.setattr(modelos.TransaccionDB, "eliminar", staticmethod(no_borra))
    meta["claude"].append(herramienta("registrar_movimientos", {"movimientos": [
        {"tipo": "gasto", "monto": 1000, "fecha": "2026-11-23"}, {"tipo": "gasto", "monto": 2000, "fecha": "2026-11-23"}]}))
    _msg(client, "mil y dos mil")
    assert "puede que parte" in meta["enviados"][-1][1] and "No se registró nada" not in meta["enviados"][-1][1]


def test_inv030_ayuda_tambien_respeta_el_tope_por_minuto(client, meta):
    _enlazar(client, meta)
    antes = len(meta["enviados"])
    for _ in range(15):
        _msg(client, "ayuda")
    assert len(meta["enviados"]) - antes == 10


# ── Diagnóstico de entrega (CHG-014): por qué Meta no entrega una respuesta ───

def _firmar(client, payload):
    raw = json.dumps(payload).encode()
    firma = "sha256=" + hmac.new(SECRETO.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/api/v1/whatsapp/webhook", content=raw, headers={"X-Hub-Signature-256": firma})


def test_una_entrega_fallida_se_registra_en_el_log_sin_datos_personales(client, meta, capsys):
    payload = {"entry": [{"changes": [{"value": {"statuses": [{
        "id": "wamid.SECRETO123", "status": "failed", "recipient_id": TEL_A,
        "errors": [{"code": 131031, "title": "Business Account locked", "message": "x", "error_data": {"details": "y"}}]}]}}]}]}
    assert _firmar(client, payload).status_code == 200
    salida = capsys.readouterr().out
    assert "Meta no entregó una respuesta: código 131031 Business Account locked" in salida
    assert TEL_A not in salida and "wamid.SECRETO123" not in salida and "token" not in salida.lower()


def test_los_estados_que_no_fallaron_no_se_registran(client, meta, capsys):
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}, {"status": "sent"}, {"status": "read"}]}}]}]}
    _firmar(client, payload)
    assert "no entregó" not in capsys.readouterr().out


def test_un_numero_de_telefono_distinto_se_avisa_en_el_log(client, meta, capsys):
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "999"},
                                                 "messages": [{"id": "w1", "from": TEL_A, "type": "text", "text": {"body": "hola"}}]}}]}]}
    _firmar(client, payload)
    salida = capsys.readouterr().out
    assert "no coincide con WHATSAPP_PHONE_NUMBER_ID" in salida and TEL_A not in salida


@pytest.mark.parametrize("payload", [{"entry": [{"changes": [{"value": {"statuses": "no es lista"}}]}]},
                                     {"entry": [{"changes": [{"value": {"statuses": [{"status": "failed", "errors": "x"}]}}]}]},
                                     {"entry": [{"changes": [{"value": {"statuses": [None, 5]}}]}]}])
def test_estados_raros_no_rompen_el_webhook(client, meta, payload):
    assert _firmar(client, payload).status_code == 200
