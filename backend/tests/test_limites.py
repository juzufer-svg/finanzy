"""INV-010: límites de envío de correos e intentos por IP. (BDD-LIMITES)"""
from datetime import timedelta

from app.models import auth_estado as ae
from conftest import ip


def _pendiente(users, correo):
    users[correo] = {"id": correo, "email": correo, "hashed_password": "", "is_active": False, "full_name": "", "currency": "USD"}


def _eventos_previos(clave, tipo, cantidad, ahora):
    """Eventos de envío de hace 1 hora (fuera del espacio de 60 s, dentro de la ventana de 24 h)."""
    ae._Memoria.eventos[(clave, tipo)] = [ahora - timedelta(hours=1)] * cantidad


def test_ip_maximo_10_pedidos_de_codigo_por_hora(client, users, sent_emails):
    codes = [client.post("/api/v1/auth/forgot-password", json={"email": f"x{i}@example.com"}, headers=ip(1)).status_code for i in range(11)]
    assert codes == [200] * 10 + [429]
    assert client.post("/api/v1/auth/forgot-password", json={"email": "y@example.com"}, headers=ip(2)).status_code == 200


def test_no_se_reenvia_codigo_antes_de_60_segundos(client, users, sent_emails):
    body = {"email": "nuevo@example.com", "full_name": "Nuevo", "password": "Clave12345"}
    assert client.post("/api/v1/auth/register", json=body, headers=ip(1)).status_code == 201
    assert client.post("/api/v1/auth/register", json=body, headers=ip(1)).status_code == 201
    assert len(sent_emails) == 1


def test_maximo_10_correos_por_dia_al_mismo_destinatario(client, users, sent_emails, reloj):
    _pendiente(users, "victima@example.com")
    estados = []
    for i in range(11):
        reloj.avanzar(seconds=61)  # simula que pasaron 60 s entre pedidos
        estados.append(client.post("/api/v1/auth/resend-code", json={"email": "victima@example.com"}, headers=ip(10 + i)).status_code)
    assert estados == [200] * 10 + [429] and len(sent_emails) == 10


def test_forgot_password_aplica_el_limite_diario_en_silencio(client, users, sent_emails, reloj):
    users["ana@example.com"] = {"id": "a", "email": "ana@example.com", "hashed_password": "", "is_active": True, "full_name": "", "currency": "USD"}
    _eventos_previos(ae.huella_correo("ana@example.com"), "correo", 10, reloj.t)
    r = client.post("/api/v1/auth/forgot-password", json={"email": "ana@example.com"}, headers=ip(1))
    assert r.status_code == 200 and sent_emails == []  # no revela el límite (INV-009)


def test_tope_global_de_250_correos_por_dia(client, users, sent_emails, reloj):
    _pendiente(users, "otro@example.com")
    _eventos_previos("global", "global", 250, reloj.t)
    assert client.post("/api/v1/auth/resend-code", json={"email": "otro@example.com"}, headers=ip(1)).status_code == 429
    assert sent_emails == []


def test_ip_maximo_30_intentos_de_login_cada_10_minutos(client, users):
    codes = [client.post("/api/v1/auth/login", json={"email": f"u{i}@example.com", "password": "x"}, headers=ip(7)).status_code for i in range(31)]
    assert codes == [401] * 30 + [429]
