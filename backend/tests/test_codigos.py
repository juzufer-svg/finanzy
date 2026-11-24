"""Códigos y recuperación de contraseña: INV-007, INV-009, REQ-F-003. (BDD-RECUPERACION)"""
import asyncio

from app.models import auth_estado as ae
from app.utils.email import generate_code
from conftest import ip


def _usuario(users, activa=True):
    from app.core.security import get_password_hash
    users["ana@example.com"] = {"id": "u1", "email": "ana@example.com", "hashed_password": get_password_hash("Vieja1234"),
                                "is_active": activa, "full_name": "Ana", "currency": "USD"}


def test_inv009_forgot_password_responde_igual_exista_o_no(client, users, sent_emails):
    _usuario(users)
    a = client.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"}, headers=ip(1))
    b = client.post("/api/v1/auth/forgot-password", json={"email": "nadie@example.com"}, headers=ip(1))
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert [s[0] for s in sent_emails] == ["ana@example.com"] and sent_emails[0][2] == "reset"


def test_inv009_resend_code_responde_igual_y_solo_envia_a_pendientes(client, users, sent_emails, reloj):
    _usuario(users, activa=False)
    a = client.post("/api/v1/auth/resend-code", json={"email": "nadie@example.com"}, headers=ip(1))
    b = client.post("/api/v1/auth/resend-code", json={"email": "ana@example.com"}, headers=ip(1))
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert len(sent_emails) == 1
    users["ana@example.com"]["is_active"] = True
    reloj.avanzar(seconds=61)  # pasaron 60 s: el espacio entre códigos no es lo que se prueba aquí
    client.post("/api/v1/auth/resend-code", json={"email": "ana@example.com"}, headers=ip(1))
    assert len(sent_emails) == 1  # cuenta activa: no se envía


def test_restablecer_contrasena_flujo_completo(client, users, sent_emails):
    _usuario(users, activa=False)
    client.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"}, headers=ip(1))
    code = sent_emails[0][1]
    assert client.post("/api/v1/auth/reset-password", json={"email": "ana@example.com", "code": code, "new_password": "corta"}, headers=ip(1)).status_code == 422
    r = client.post("/api/v1/auth/reset-password", json={"email": "ANA@example.com", "code": code, "new_password": "NuevaClave1"}, headers=ip(1))
    assert r.status_code == 200 and users["ana@example.com"]["is_active"] is True
    login = client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "NuevaClave1"}, headers=ip(1))
    assert login.status_code == 200 and "access_token" in login.json()
    assert client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "Vieja1234"}, headers=ip(1)).status_code == 401


def test_inv007_codigo_de_un_solo_uso(client, users, sent_emails):
    _usuario(users)
    client.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"}, headers=ip(1))
    code = sent_emails[0][1]
    body = {"email": "ana@example.com", "code": code, "new_password": "NuevaClave1"}
    assert client.post("/api/v1/auth/reset-password", json=body, headers=ip(1)).status_code == 200
    assert client.post("/api/v1/auth/reset-password", json=body, headers=ip(1)).status_code == 400


def test_inv007_codigos_de_verificacion_y_reset_no_son_intercambiables(client, users, sent_emails):
    _usuario(users)
    client.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"}, headers=ip(1))
    code = sent_emails[0][1]
    assert client.post("/api/v1/auth/verify-email", json={"email": "ana@example.com", "code": code}, headers=ip(1)).status_code == 400


def test_inv007_codigo_se_invalida_tras_5_fallos_y_vence(reloj):
    run = asyncio.run
    assert run(ae.codigo_emitir("v@example.com", "verify", "123456")) == "enviado"
    for _ in range(5):
        assert run(ae.codigo_verificar("v@example.com", "verify", "000000")) == "incorrecto"
    # al 6.º intento ya está agotado: ni siquiera el código correcto lo activa
    assert run(ae.codigo_verificar("v@example.com", "verify", "123456")) == "invalido"

    assert run(ae.codigo_emitir("w@example.com", "verify", "654321")) == "enviado"
    reloj.avanzar(minutes=10, seconds=1)
    assert run(ae.codigo_verificar("w@example.com", "verify", "654321")) == "invalido"  # vencido
    assert (ae.huella_correo("w@example.com"), "verify") not in ae._Memoria.codigos      # y el vencido se borra


def test_inv007_codigo_de_6_digitos_generado_con_secrets():
    codigos = {generate_code() for _ in range(50)}
    assert all(len(c) == 6 and c.isdigit() for c in codigos) and len(codigos) > 1
