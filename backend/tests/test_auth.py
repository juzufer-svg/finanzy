"""Registro, login y sesiones: INV-006, INV-010 (login), INV-011, INV-014, INV-015. (BDD-AUTH)"""
import base64
import hashlib
import hmac
import json
import time

import bcrypt

from app.core import security
from app.core.config import settings
from conftest import ip

REGISTRO = {"email": "Ana@Example.com", "full_name": "Ana", "password": "Clave12345"}


def test_registro_crea_cuenta_pendiente_y_envia_codigo(client, users, sent_emails):
    r = client.post("/api/v1/auth/register", json=REGISTRO, headers=ip(1))
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert users["ana@example.com"]["is_active"] is False
    assert len(sent_emails) == 1 and sent_emails[0][0] == "ana@example.com" and sent_emails[0][2] == "verify"


def test_verificar_codigo_activa_la_cuenta_y_da_sesion(client, users, sent_emails):
    client.post("/api/v1/auth/register", json=REGISTRO, headers=ip(1))
    code = sent_emails[0][1]
    r = client.post("/api/v1/auth/verify-email", json={"email": "ana@example.com", "code": code}, headers=ip(1))
    assert r.status_code == 200 and "access_token" in r.json()
    assert users["ana@example.com"]["is_active"] is True


def test_registro_con_correo_activo_es_409(client, users, sent_emails):
    users["ana@example.com"] = {"id": "1", "email": "ana@example.com", "hashed_password": "", "is_active": True, "full_name": "", "currency": "USD"}
    assert client.post("/api/v1/auth/register", json=REGISTRO, headers=ip(1)).status_code == 409


def test_inv014_correo_se_normaliza_a_minusculas(client, users, sent_emails):
    client.post("/api/v1/auth/register", json=REGISTRO, headers=ip(1))
    assert list(users) == ["ana@example.com"]


def test_inv006_cuenta_pendiente_no_obtiene_sesion(client, users, sent_emails):
    client.post("/api/v1/auth/register", json=REGISTRO, headers=ip(1))
    r = client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "Clave12345"}, headers=ip(1))
    assert r.status_code == 200 and r.json()["status"] == "pending" and "access_token" not in r.json()


def test_login_correcto_e_incorrecto(client, users, sent_emails):
    users["ana@example.com"] = {"id": "1", "email": "ana@example.com", "hashed_password": security.get_password_hash("Clave12345"), "is_active": True, "full_name": "", "currency": "USD"}
    ok = client.post("/api/v1/auth/login", json={"email": "ANA@example.com", "password": "Clave12345"}, headers=ip(1))
    assert ok.status_code == 200 and security.decode_token(ok.json()["access_token"])["sub"] == "1"
    mal = client.post("/api/v1/auth/login", json={"email": "ana@example.com", "password": "otra"}, headers=ip(1))
    assert mal.status_code == 401 and mal.json()["detail"] == "Credenciales inválidas"


def test_inv010_login_se_bloquea_tras_5_fallos(client, users):
    codes = [client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "mala"}, headers=ip(i)).status_code for i in range(6)]
    assert codes == [401] * 5 + [429]


# ── INV-015: contraseñas ──────────────────────────────────────────────────────

def test_inv015_valida_hash_2a_creado_con_sql():
    h2a = bcrypt.hashpw(b"Julian123", bcrypt.gensalt(prefix=b"2a")).decode()
    assert security.verify_password("Julian123", h2a)
    assert not security.verify_password("julian123", h2a)


def test_inv015_valida_contrasenas_largas_de_passlib():
    largo = "a" * 80
    h = bcrypt.hashpw(largo.encode()[:72], bcrypt.gensalt()).decode()
    assert security.verify_password(largo, h)


def test_inv015_hash_nuevo_es_bcrypt_y_hash_invalido_no_rompe():
    h = security.get_password_hash("Otra1234")
    assert h.startswith("$2b$") and security.verify_password("Otra1234", h)
    assert not security.verify_password("x", "") and not security.verify_password("x", "no-es-un-hash")


# ── INV-011: sesiones ─────────────────────────────────────────────────────────

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _token(header, payload, key=None):
    key = key or settings.SECRET_KEY
    h, p = _b64(json.dumps(header).encode()), _b64(json.dumps(payload).encode())
    firma = _b64(hmac.new(key.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{firma}"


def test_inv011_token_valido_y_tokens_previos_siguen_validos():
    previo = _token({"alg": "HS256", "typ": "JWT"}, {"sub": "user-1", "exp": int(time.time()) + 600})
    assert security.decode_token(previo)["sub"] == "user-1"
    assert security.decode_token(security.create_access_token({"sub": "user-2"}))["sub"] == "user-2"


def test_inv011_tokens_invalidos_se_rechazan():
    ahora = int(time.time())
    assert security.decode_token(_token({"alg": "HS256"}, {"sub": "u", "exp": ahora - 10})) is None  # vencido
    assert security.decode_token(_token({"alg": "HS256"}, {"sub": "u"})) is None  # sin exp
    assert security.decode_token(_token({"alg": "HS256"}, {"exp": ahora + 60})) is None  # sin sub
    assert security.decode_token(_token({"alg": "HS256"}, {"sub": "u", "exp": ahora + 60}, key="otra")) is None
    sin_firma = _b64(json.dumps({"alg": "none"}).encode()) + "." + _b64(json.dumps({"sub": "u", "exp": ahora + 60}).encode()) + "."
    assert security.decode_token(sin_firma) is None
