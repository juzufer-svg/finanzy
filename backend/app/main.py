"""
Main FastAPI application with Supabase integration
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import auth, users, plataapp, asistente, whatsapp


async def cleanup_unverified_loop():
    """Tarea de fondo: cada 10 minutos elimina las cuentas pendientes con más de 1 hora."""
    from app.models.user import UserDB
    from app.models.whatsapp import WhatsappDB
    while True:
        await asyncio.sleep(600)
        await UserDB.delete_unverified_expired()
        try:   # ids de mensajes de WhatsApp ya procesados de más de 7 días (CHG-014)
            await WhatsappDB.limpiar_mensajes_antiguos()
        except Exception as e:
            print(f"[cleanup] whatsapp_mensajes: {type(e).__name__}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(cleanup_unverified_loop())
    print("🚀 Finanzy API iniciada")
    print("🧹 Limpieza activa: cuentas sin verificar con más de 1 hora se eliminan cada 10 min")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


_is_production = settings.ENVIRONMENT.lower() == "production"

app = FastAPI(
    title="Finanzy API",
    description="API con autenticación JWT y Base de Datos Supabase",
    version="1.0.0",
    lifespan=lifespan,
    # No exponer la documentación interactiva en producción
    debug=bool(settings.DEBUG and not _is_production),
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# CORS: solo orígenes exactos (CHG-002). El frontend en Vercel llama al backend a
# través del proxy de Next.js (servidor a servidor), por lo que el navegador no
# necesita CORS en producción; esta lista sirve para desarrollo y pruebas.
# Sin comodines ni expresiones regulares: un «*.vercel.app» permitiría que
# cualquier proyecto de Vercel llamara a la API con credenciales.
import os

codespace_name = os.getenv("CODESPACE_NAME", "").strip()

allow_origins = list(settings.CORS_ORIGINS)
allow_origins += [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:5173",
    "https://localhost:3000",
    "https://localhost:8000",
    "https://finanzyapp.vercel.app",
]

if codespace_name:
    allow_origins += [
        f"https://{codespace_name}-3000.app.github.dev",
        f"https://{codespace_name}-8000.app.github.dev",
    ]

# URL del despliegue de Vercel (si se define); solo un host, sin rutas
vercel_url = os.getenv("VERCEL_URL", "").strip().strip("/")
if vercel_url and "/" not in vercel_url and "*" not in vercel_url:
    allow_origins.append(f"https://{vercel_url}")

allow_origins = list(dict.fromkeys(allow_origins))  # sin duplicados, en orden
print(f"✓ CORS allowed origins: {allow_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Include Routes
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(plataapp.router, prefix="/api/v1", tags=["finanzy"])
app.include_router(asistente.router, prefix="/api/v1/asistente", tags=["asistente"])
app.include_router(whatsapp.router, prefix="/api/v1/whatsapp", tags=["whatsapp"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Finanzy API",
        "version": "1.0.0",
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
