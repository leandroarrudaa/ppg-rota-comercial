"""Aplicação FastAPI da plataforma de representação comercial PPG."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .config import config
from .database import Base, checar_conexao, engine, garantir_colunas, garantir_indices
from .routers import auth, clientes, configuracoes, importacao, relatorios, vinculos, visitas

log = logging.getLogger(__name__)

# De quanto em quanto tempo tocar no banco só para ele não pausar. O Supabase
# gratuito pausa o projeto após ~7 dias parado; como o serviço aqui fica sempre
# ligado, ele mesmo se encarrega disso, sem cron externo nem custo extra.
_INTERVALO_KEEP_ALIVE_S = 12 * 60 * 60


async def _manter_banco_acordado():
    """Toca no banco periodicamente para impedir a pausa por inatividade."""
    while True:
        await asyncio.sleep(_INTERVALO_KEEP_ALIVE_S)
        try:
            await asyncio.to_thread(checar_conexao)
        except Exception:  # nunca deixar a tarefa de fundo derrubar o app
            log.exception("Falha no keep-alive do banco")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Sobe o app SEM depender do banco.

    Antes, `create_all` rodava na importação do módulo e sem timeout: com o
    Supabase pausado, o processo travava antes de abrir a porta e o serviço
    inteiro ficava inacessível por tempo indeterminado. Agora a preparação do
    esquema é best-effort — se o banco estiver fora, o app sobe assim mesmo e
    responde com erro claro, voltando ao normal sozinho quando o banco volta.
    """
    try:
        await asyncio.to_thread(Base.metadata.create_all, engine)
        await asyncio.to_thread(garantir_colunas)
        await asyncio.to_thread(garantir_indices)
    except SQLAlchemyError:
        log.exception("Não foi possível preparar o esquema — app sobe mesmo assim")

    tarefa = asyncio.create_task(_manter_banco_acordado())
    try:
        yield
    finally:
        tarefa.cancel()


app = FastAPI(title="PPG Rota Comercial", version="0.1.0", lifespan=lifespan)

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

# A carteira inteira dá ~1 MB de JSON, e o vendedor baixa isso no 4G. Comprimida
# cai para ~1/7 do tamanho. Só vale a pena a partir de alguns KB — abaixo disso
# o custo de comprimir supera a economia.
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.exception_handler(SQLAlchemyError)
async def erro_de_banco(_request: Request, erro: SQLAlchemyError):
    """Qualquer falha de banco vira uma mensagem que o vendedor entende —
    nunca um stack trace nem uma requisição pendurada."""
    log.exception("Erro de banco na requisição", exc_info=erro)
    return JSONResponse(
        status_code=503,
        content={"detail": "O banco de dados está fora do ar no momento. Tente de novo em alguns minutos."},
    )


app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(visitas.router)
app.include_router(vinculos.router)
app.include_router(relatorios.router)
app.include_router(configuracoes.router)
app.include_router(importacao.router)


@app.get("/api/saude")
def saude():
    """Verificação usada pelo health check do Render.

    De propósito NÃO consulta o banco: se dependesse dele, um Supabase pausado
    faria o Render considerar o deploy inteiro com falha e parar de rotear
    tráfego — transformando um problema de banco em app totalmente fora do ar.
    Aqui basta responder que o processo está de pé.
    """
    return {"ok": True}


@app.get("/api/diagnostico")
def diagnostico():
    """Estado real das dependências — para investigar problema em produção.

    Devolve também QUAL versão do código está rodando. Sem isso não havia como
    responder "o deploy já entrou?" quando a mudança era só interna (sem rota
    nova, sem texto novo) — ficava-se olhando o app responder "ok" sem saber se
    era o código velho ou o novo.

    A variável vem do próprio Render; fora dele fica "desenvolvimento".
    """
    return {
        "app": "ok",
        "banco": "ok" if checar_conexao() else "indisponivel",
        "versao": (os.getenv("RENDER_GIT_COMMIT") or "")[:7] or "desenvolvimento",
    }
