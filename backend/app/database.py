"""Conexão com o banco de dados e sessão do SQLAlchemy.

Resiliência é requisito aqui, não luxo: o banco de produção é um Supabase no
plano gratuito, que pausa sozinho após dias sem uso e cujo pooler derruba
conexões ociosas. O app precisa continuar de pé e responder com erro claro
nesses casos, em vez de travar esperando para sempre.
"""
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import config

log = logging.getLogger(__name__)

# Quanto esperar por uma conexão nova antes de desistir. Sem isso, um banco
# pausado prende a requisição indefinidamente (foi o que derrubou o app em
# produção: o servidor ficava minutos sem devolver um único byte).
_TIMEOUT_CONEXAO_S = 10
# Teto para uma query isolada. Protege contra a mesma classe de travamento
# depois que a conexão já foi aberta.
_TIMEOUT_QUERY_MS = 15_000

_e_sqlite = config.database_url.startswith("sqlite")

if _e_sqlite:
    conectar_args = {"check_same_thread": False}
    opcoes_pool = {}
else:
    conectar_args = {
        "connect_timeout": _TIMEOUT_CONEXAO_S,
        "options": f"-c statement_timeout={_TIMEOUT_QUERY_MS}",
    }
    opcoes_pool = {
        # Testa a conexão antes de entregá-la. O pooler do Supabase fecha
        # conexões ociosas em silêncio; sem isso, a primeira requisição depois
        # de um período parado falha com "server closed the connection".
        "pool_pre_ping": True,
        # Recicla antes do limite do pooler, para não usar conexão já morta.
        "pool_recycle": 280,
        "pool_size": 5,
        "max_overflow": 5,
    }

engine = create_engine(config.database_url, connect_args=conectar_args, **opcoes_pool)
SessaoLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Fornece uma sessão de banco por requisição (dependência do FastAPI)."""
    db = SessaoLocal()
    try:
        yield db
    finally:
        db.close()


def checar_conexao() -> bool:
    """Faz um toque leve no banco. Usado pelo diagnóstico e pelo keep-alive
    que impede o Supabase gratuito de pausar por inatividade."""
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as erro:
        log.warning("Banco indisponível: %s", erro)
        return False
