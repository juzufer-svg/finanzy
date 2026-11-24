"""
Email utility - sends verification codes via the Brevo transactional email API
"""
import secrets
import httpx
from app.core.config import settings
from app.models import contadores

# Los códigos ya NO se guardan aquí: viven en PostgreSQL solo como HMAC (CHG-020, INV-037/INV-040) y se emiten y
# verifican con `app.models.auth_estado.codigo_emitir` / `codigo_verificar`. Este módulo solo genera y envía.
CODE_EXPIRE_MINUTES = 10   # informativo para el correo; la vigencia real es `auth_estado.VIGENCIA_CODIGO_SEG`


def generate_code(length: int = 6) -> str:
    # secrets: generador criptográficamente seguro (random es predecible)
    return "".join(secrets.choice("0123456789") for _ in range(length))


_TEMPLATES = {
    "verify": {
        "title": "Código de verificación",
        "intro": "Usa el siguiente código para confirmar tu cuenta.",
        "subject": "{code} es tu código de Finanzy",
    },
    "reset": {
        "title": "Restablecer contraseña",
        "intro": "Usa el siguiente código para crear una nueva contraseña.",
        "subject": "{code} es tu código para restablecer tu contraseña de Finanzy",
    },
}


def _build_html(code: str, purpose: str = "verify") -> str:
    tpl = _TEMPLATES[purpose]
    return f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:16px;overflow:hidden;
                    box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#0D1B4B 0%,#00B89C 100%);
                     padding:32px;text-align:center;">
            <h1 style="margin:0;color:#ffffff;font-size:26px;font-weight:700;
                       letter-spacing:-0.5px;">Finanzy</h1>
            <p style="margin:6px 0 0;color:rgba(255,255,255,0.75);font-size:14px;">
              Control Financiero Total
            </p>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:40px 32px;text-align:center;">
            <h2 style="margin:0 0 8px;color:#0D1B4B;font-size:20px;">
              {tpl["title"]}
            </h2>
            <p style="margin:0 0 32px;color:#64748b;font-size:15px;">
              {tpl["intro"]}<br>
              Expira en <strong>{CODE_EXPIRE_MINUTES} minutos</strong>.
            </p>
            <div style="display:inline-block;background:#f8fafc;border:2px solid #00B89C;
                        border-radius:12px;padding:20px 40px;">
              <span style="font-size:40px;font-weight:800;letter-spacing:12px;
                           color:#0D1B4B;font-family:monospace;">{code}</span>
            </div>
            <p style="margin:32px 0 0;color:#94a3b8;font-size:13px;">
              Si no solicitaste esto, ignora este correo.
            </p>
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="background:#f8fafc;padding:20px 32px;text-align:center;
                     border-top:1px solid #e2e8f0;">
            <p style="margin:0;color:#94a3b8;font-size:12px;">
              © 2026 Finanzy · Control a tu medida
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _build_text(code: str, purpose: str) -> str:
    """Versión en texto plano (mejora la entrega en Gmail y otros clientes)."""
    tpl = _TEMPLATES[purpose]
    lines = [
        tpl["title"],
        tpl["intro"],
        f"Tu código: {code}",
        f"Expira en {CODE_EXPIRE_MINUTES} minutos. Si no solicitaste esto, ignora este correo.",
        "Finanzy · Control a tu medida",
    ]
    return "\n\n".join(lines)


def send_verification_email(to_email: str, code: str, purpose: str = "verify") -> bool:
    """Envía un código de verificación / restablecimiento usando la API de Brevo.

    Requiere en el entorno:
      BREVO_API_KEY  → clave de API de Brevo (SMTP & API → API Keys)
      FROM_EMAIL     → remitente verificado en Brevo (Senders)
    """
    if settings.BREVO_API_KEY:
        if not settings.FROM_EMAIL:
            print("[EMAIL ERROR] FROM_EMAIL no está configurado (debe ser un remitente verificado en Brevo)")
            return False
        try:
            resp = httpx.post(
                BREVO_API_URL,
                headers={
                    "api-key": settings.BREVO_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "sender": {"email": settings.FROM_EMAIL, "name": settings.FROM_NAME},
                    "to": [{"email": to_email}],
                    "subject": _TEMPLATES[purpose]["subject"].format(code=code),
                    "htmlContent": _build_html(code, purpose),
                    "textContent": _build_text(code, purpose),
                },
                timeout=15,
            )
            if resp.status_code in (200, 201, 202):
                print(f"[EMAIL] Sent via Brevo ({purpose})")   # sin el correo del destinatario (INV-040)
                contadores.incrementar("brevo_correos_enviados", "general", 1)   # solo si Brevo aceptó (INV-036)
                return True
            # Sin el correo, sin el cuerpo de la respuesta de Brevo (puede repetirlo) y sin el texto de la excepción
            print(f"[EMAIL ERROR] Brevo responded {resp.status_code} ({purpose})")
        except Exception as e:
            print(f"[EMAIL ERROR] Brevo exception {type(e).__name__} ({purpose})")
        return False

    # Sin clave de Brevo: en producción es un error de configuración y el código
    # NO se escribe en los logs; en desarrollo se muestra para poder probar.
    if settings.ENVIRONMENT.lower() == "production":
        print("[EMAIL ERROR] BREVO_API_KEY no está configurada: no se pudo enviar el código")
        return False

    separator = "=" * 40
    print(f"\n{separator}\n[DEV] {purpose} code for {to_email}: {code}\n{separator}\n")
    return True
