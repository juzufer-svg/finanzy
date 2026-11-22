"""Envío de códigos con Brevo (ADR-002) e INV-012 (códigos fuera de los logs). (BDD-CORREO)"""
import pytest

from app.core.config import settings
from app.utils import email as em


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text


@pytest.fixture
def brevo(monkeypatch):
    """Simula la API de Brevo y guarda las peticiones."""
    calls = []
    state = {"status": 201, "text": '{"messageId":"<x@brevo>"}'}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json})
        return _Resp(state["status"], state["text"])

    monkeypatch.setattr(em.httpx, "post", fake_post)
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(settings, "FROM_EMAIL", "remitente@example.com")
    monkeypatch.setattr(settings, "FROM_NAME", "Finanzy")
    return calls, state


def test_envia_con_el_formato_de_la_api_de_brevo(brevo, capsys):
    calls, _ = brevo
    assert em.send_verification_email("ana@example.com", "123456", "reset") is True
    c = calls[-1]
    assert c["url"] == "https://api.brevo.com/v3/smtp/email"
    assert c["headers"]["api-key"] == "xkeysib-test"
    body = c["json"]
    assert body["sender"] == {"email": "remitente@example.com", "name": "Finanzy"}
    assert body["to"] == [{"email": "ana@example.com"}]
    assert "123456" in body["subject"] and "123456" in body["htmlContent"] and "123456" in body["textContent"]
    assert "Restablecer" in body["htmlContent"]
    assert "Sent via Brevo" in capsys.readouterr().out


def test_plantilla_de_verificacion(brevo):
    calls, _ = brevo
    em.send_verification_email("ana@example.com", "654321", "verify")
    assert "Código de verificación" in calls[-1]["json"]["htmlContent"]


def test_error_de_brevo_devuelve_false_y_registra_el_motivo(brevo, capsys):
    _, state = brevo
    state.update(status=401, text='{"message":"Key not found"}')
    assert em.send_verification_email("ana@example.com", "111111") is False
    out = capsys.readouterr().out
    assert "Brevo responded 401" in out and "Key not found" in out


def test_sin_remitente_no_llama_a_brevo(brevo, monkeypatch, capsys):
    calls, _ = brevo
    monkeypatch.setattr(settings, "FROM_EMAIL", "")
    assert em.send_verification_email("ana@example.com", "222222") is False
    assert calls == [] and "FROM_EMAIL" in capsys.readouterr().out


def test_inv012_en_produccion_sin_clave_el_codigo_no_va_a_los_logs(monkeypatch, capsys):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert em.send_verification_email("ana@example.com", "333333") is False
    out = capsys.readouterr().out
    assert "333333" not in out and "BREVO_API_KEY" in out


def test_en_desarrollo_sin_clave_el_codigo_se_muestra(monkeypatch, capsys):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert em.send_verification_email("ana@example.com", "444444") is True
    assert "444444" in capsys.readouterr().out
