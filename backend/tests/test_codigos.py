"""Códigos y recuperación de contraseña: INV-007, INV-009, REQ-F-003. (BDD-RECUPERACION)"""
from app.utils import email as em
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


def test_inv009_resend_code_responde_igual_y_solo_envia_a_pendientes(client, users, sent_emails):
    _usuario(users, activa=False)
    a = client.post("/api/v1/auth/resend-code", json={"email": "nadie@example.com"}, headers=ip(1))
    b = client.post("/api/v1/auth/resend-code", json={"email": "ana@example.com"}, headers=ip(1))
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert len(sent_emails) == 1
    users["ana@example.com"]["is_active"] = True
    em._pending_codes.clear()
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


def test_inv007_codigo_se_invalida_tras_5_fallos_y_vence():
    em.save_code("v@example.com", "123456")
    for _ in range(5):
        assert not em.verify_code("v@example.com", "000000")
    assert not em.verify_code("v@example.com", "123456")  # invalidado

    em.save_code("w@example.com", "654321")
    from datetime import datetime, timedelta, timezone
    em._pending_codes["w@example.com"]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert not em.verify_code("w@example.com", "654321")  # vencido


def test_inv007_codigo_de_6_digitos_generado_con_secrets():
    codigos = {em.generate_code() for _ in range(50)}
    assert all(len(c) == 6 and c.isdigit() for c in codigos) and len(codigos) > 1
