"""
Email utility - sends verification codes via SendGrid API
"""
import secrets
from datetime import datetime, timedelta
import httpx
from app.core.config import settings

# In-memory store: { email: { code, expires_at, attempts } }
_pending_codes: dict[str, dict] = {}

CODE_EXPIRE_MINUTES = 10
MAX_CODE_ATTEMPTS = 5  # intentos fallidos permitidos por código


def generate_code(length: int = 6) -> str:
    # secrets: generador criptográficamente seguro (random es predecible)
    return "".join(secrets.choice("0123456789") for _ in range(length))


def save_code(email: str, code: str) -> None:
    _pending_codes[email.lower()] = {
        "code": code,
        "expires_at": datetime.utcnow() + timedelta(minutes=CODE_EXPIRE_MINUTES),
        "attempts": 0,
    }


def code_recently_sent(email: str, min_seconds: int = 60) -> bool:
    """True si ya se emitió un código para este email hace menos de min_seconds."""
    entry = _pending_codes.get(email.lower())
    if not entry:
        return False
    issued_at = entry["expires_at"] - timedelta(minutes=CODE_EXPIRE_MINUTES)
    return (datetime.utcnow() - issued_at).total_seconds() < min_seconds


def verify_code(email: str, code: str) -> bool:
    key = email.lower()
    entry = _pending_codes.get(key)
    if not entry:
        return False
    if datetime.utcnow() > entry["expires_at"]:
        _pending_codes.pop(key, None)
        return False
    if not secrets.compare_digest(entry["code"], code):
        entry["attempts"] += 1
        # Tras varios fallos el código se invalida: evita probar los 1.000.000 de combinaciones
        if entry["attempts"] >= MAX_CODE_ATTEMPTS:
            _pending_codes.pop(key, None)
        return False
    _pending_codes.pop(key, None)
    return True


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


def send_verification_email(to_email: str, code: str, purpose: str = "verify") -> bool:
    """Send a verification / password-reset code via SendGrid API."""

    # ── 1. SendGrid API ───────────────────────────────────────────────────────
    if settings.SENDGRID_API_KEY:
        from_addr = settings.FROM_EMAIL or "noreply@finanzy.app"
        try:
            resp = httpx.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": from_addr, "name": settings.FROM_NAME},
                    "subject": _TEMPLATES[purpose]["subject"].format(code=code),
                    "content": [{"type": "text/html", "value": _build_html(code, purpose)}],
                },
                timeout=15,
            )
            if resp.status_code == 202:
                print(f"[EMAIL] Sent via SendGrid to {to_email}")
                return True
            print(f"[EMAIL ERROR] SendGrid responded {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[EMAIL ERROR] SendGrid exception: {e}")
        return False

    # ── 2. Dev mode ───────────────────────────────────────────────────────────
    print(f"\n{'='*40}")
    print(f"[DEV] {purpose} code for {to_email}: {code}")
    print(f"{'='*40}\n")
    return True
