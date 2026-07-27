"""Fixtures de teste: banco SQLite em memória + cliente HTTP com dependência trocada."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Cliente, OrigemCliente, StatusCliente


@pytest.fixture
def db():
    """Sessão de banco isolada (SQLite em memória) para cada teste."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    # autoflush=False espelha a sessão real (app/database.py) — sem isso,
    # bugs de "query não vê mudança em memória ainda não commitada" passam
    # despercebidos nos testes mas quebram em produção.
    Sessao = sessionmaker(bind=engine, autoflush=False)
    sessao = Sessao()

    # Semeia alguns clientes de exemplo.
    sessao.add_all([
        Cliente(
            cnpj="11.111.111/0001-11", nome="Empresa Ouro LTDA", cidade="Curitiba", uf="PR",
            lat=-25.4, lng=-49.2, faixa="Ouro", em_risco=False, fat_total=50000,
            origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO,
        ),
        Cliente(
            cnpj="22.222.222/0001-22", nome="Empresa Bronze ME", cidade="Ponta Grossa", uf="PR",
            lat=-25.1, lng=-50.1, faixa="Bronze", em_risco=False, fat_total=3000,
            origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO,
        ),
        Cliente(
            cnpj="33.333.333/0001-33", nome="Empresa Fechada LTDA", cidade="Curitiba", uf="PR",
            lat=-25.4, lng=-49.2, faixa="Prata", origem=OrigemCliente.ANTIGO,
            status=StatusCliente.INATIVO,
        ),
    ])
    sessao.commit()

    yield sessao
    sessao.close()


@pytest.fixture
def cliente_http(db):
    """TestClient da API, com a sessão de banco do teste injetada via override."""
    def _get_db_teste():
        yield db

    app.dependency_overrides[get_db] = _get_db_teste
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
