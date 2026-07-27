"""Aplicação FastAPI da plataforma de representação comercial PPG."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .database import Base, engine
from .routers import auth, clientes, vinculos, visitas

# Cria as tabelas que ainda não existem (idempotente).
Base.metadata.create_all(bind=engine)

app = FastAPI(title="PPG Rota Comercial", version="0.1.0")

# Frontend roda em porta separada (Vite) — liberar as origens de dev + produção.
origens = ["http://localhost:5175", "http://127.0.0.1:5175"]
if config.cors_origem_extra:
    origens.append(config.cors_origem_extra)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(visitas.router)
app.include_router(vinculos.router)


@app.get("/api/saude")
def saude():
    """Endpoint simples de verificação (usado pelo Render e pelo frontend)."""
    return {"ok": True}
