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
        # Recicla a conexão bem antes do limite de ociosidade do pooler do
        # Supabase, que fecha conexão parada em silêncio. É prevenção de graça:
        # acontece na hora de devolver a conexão, não no caminho da requisição.
        "pool_recycle": 280,
        "pool_size": 5,
        "max_overflow": 5,
        # pool_pre_ping fica DESLIGADO de propósito. Ele faria um SELECT 1 antes
        # de cada consulta — e com o banco em São Paulo e o app nos EUA, esse
        # teste custa ~170ms em TODA requisição (medido em produção: a consulta
        # trivial de login subiu de 0,35s para 0,52s com ele ligado). O
        # pool_recycle acima já evita quase toda conexão morta, e no caso raro
        # que escapar o handler de SQLAlchemyError devolve 503 com mensagem
        # clara, a conexão é invalidada e a tentativa seguinte já funciona.
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


def garantir_indices() -> None:
    """Cria os índices da listagem em bancos que já existem.

    `create_all` só cria tabelas ausentes — em tabela que já existe (o caso de
    produção) ele não acrescenta índice nenhum. Como o projeto não usa Alembic,
    o jeito mais simples e seguro é este DDL idempotente: roda toda vez, não
    faz nada se o índice já estiver lá, e é instantâneo neste volume de dados.
    """
    comandos = [
        "CREATE INDEX IF NOT EXISTS ix_clientes_listagem ON clientes (status, aceita_visita, lat, lng)",
        "CREATE INDEX IF NOT EXISTS ix_clientes_cidade ON clientes (cidade)",
        "CREATE INDEX IF NOT EXISTS ix_clientes_faixa ON clientes (faixa)",
        "CREATE INDEX IF NOT EXISTS ix_visitas_vendedor_status_inicio ON visitas (vendedor_id, status, inicio)",
    ]
    with engine.begin() as conexao:
        for comando in comandos:
            conexao.execute(text(comando))


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
