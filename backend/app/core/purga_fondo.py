"""
Purga oportunista del estado de autenticación DESPUÉS de responder (CHG-020, I-A, ADR-010, INV-040).

Middleware ASGI puro: cuando una petición a las rutas de autenticación (o al cambio de contraseña) ya envió su respuesta,
sea cual sea (200, 401, 429, 503...), intenta `auth_estado.purgar_en_segundo_plano()`. Se hace aquí y no con
`BackgroundTasks` porque FastAPI descarta las tareas de fondo cuando la ruta lanza `HTTPException`, y un ataque de logins
con IP falsificadas solo produce 401/429: justo ahí la limpieza no puede depender de que alguien pida códigos.

`purgar_en_segundo_plano` se limita sola a una vez por hora y proceso (cinco minutos tras un fallo), nunca corre dos a la
vez y nunca lanza ni imprime datos personales.
"""
from app.models import auth_estado

_RUTAS_EXACTAS = ("/api/v1/users/me/password",)
_PREFIJOS = ("/api/v1/auth/",)


def es_ruta_de_auth(ruta: str) -> bool:
    return ruta in _RUTAS_EXACTAS or ruta.startswith(_PREFIJOS)


class PurgaEnSegundoPlano:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            await self.app(scope, receive, send)
        finally:
            if scope.get("type") == "http" and es_ruta_de_auth(scope.get("path", "")):
                await auth_estado.purgar_en_segundo_plano()
