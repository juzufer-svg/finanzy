"""Aplicación FastAPI de Finanzy."""
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import auth, users, plataapp
from app.models.demo_db import DemoUserDB
from app.models.user import UserDB

async def init_demo_users() -> None:
    """Carga usuarios demo solo en desarrollo; producción requiere Supabase."""
    if settings.ENVIRONMENT.lower() == "production" or UserDB._is_supabase_available():
        return
    for username, password in [("julian", "password123"), ("alice", "password123"), ("bob", "password123")]:
        if not await DemoUserDB.get_by_username(username):
            await DemoUserDB.create(username, password)

async def cleanup_unverified_loop() -> None:
    while True:
        await asyncio.sleep(600)
        await UserDB.delete_unverified_expired()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_demo_users()
    task = asyncio.create_task(cleanup_unverified_loop())
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
    description="API con autenticación JWT y base de datos Supabase",
    version="1.1.0",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
    debug=bool(settings.DEBUG and not _is_production),
    lifespan=lifespan,
)

# Lista exacta de orígenes. No se confía en todos los subdominios Vercel o Codespaces.
allow_origins = list(settings.CORS_ORIGINS)
vercel_url = os.getenv("VERCEL_URL", "").strip().strip("/")
if vercel_url and "/" not in vercel_url:
    candidate = f"https://{vercel_url}"
    if candidate not in allow_origins:
        allow_origins.append(candidate)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(plataapp.router, prefix="/api/v1", tags=["finanzy"])

@app.get("/")
async def root():
    return {"message": "Finanzy API", "version": "1.1.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
