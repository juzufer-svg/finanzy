"""
Main FastAPI application with Supabase integration
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import auth, users, plataapp


async def cleanup_unverified_loop():
    """Tarea de fondo: cada 10 minutos elimina las cuentas pendientes con más de 1 hora."""
    from app.models.user import UserDB
    while True:
        await asyncio.sleep(600)
        await UserDB.delete_unverified_expired()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(cleanup_unverified_loop())
    print("🚀 Finanzy API iniciada")
    print("🧹 Limpieza activa: cuentas sin verificar con más de 1 hora se eliminan cada 10 min")
    try:
        yield
    finally:
        task.cancel()


_is_production = settings.ENVIRONMENT.lower() == "production"

app = FastAPI(
    title="Finanzy API",
    description="API con autenticación JWT y Base de Datos Supabase",
    version="1.0.0",
    lifespan=lifespan,
    # No exponer la documentación interactiva en producción
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# CORS Middleware Configuration
# IMPORTANT: allow_origins=["*"] is INCOMPATIBLE with allow_credentials=True
# Must use explicit origins or allow_origin_regex
import os

codespace_name = os.getenv("CODESPACE_NAME", "").strip()

allow_origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:5173",
    "https://localhost:3000",
    "https://localhost:8000",
]

if codespace_name:
    allow_origins.extend([
        f"https://{codespace_name}-3000.app.github.dev",
        f"https://{codespace_name}-8000.app.github.dev",
        f"http://{codespace_name}-3000.app.github.dev",
        f"http://{codespace_name}-8000.app.github.dev",
    ])
    print(f"✓ Codespaces detected: {codespace_name}")

# Vercel frontend URL
vercel_url = os.getenv("VERCEL_URL", "").strip()
if vercel_url:
    allow_origins.append(f"https://{vercel_url}")

# Always allow Vercel production domain
allow_origins.extend([
    "https://plataapp-omega.vercel.app",
    "https://plataapp.vercel.app",
])

print(f"✓ CORS allowed origins: {allow_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=r"https://(.*\.app\.github\.dev|.*\.vercel\.app)",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include Routes
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(plataapp.router, prefix="/api/v1", tags=["finanzy"])

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
