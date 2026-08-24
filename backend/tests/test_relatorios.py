"""Testes da tela de Relatórios: filtro por período/vendedor, resumo e permissões."""
from datetime import datetime, timedelta

import pytest

from app.models import Cliente, PapelUsuario, Promessa, StatusVisita, Usuario, Visita
from app.services import auth


@pytest.fixture
def admin_e_vendedor(db):
    admin = Usuario(nome="Ana Admin", usuario="ana", senha_hash=auth.gerar_hash("123456"), papel=PapelUsuario.ADMIN)
    vendedor = Usuario(nome="Taborda", usuario="taborda", senha_hash=auth.gerar_hash("123456"), papel=PapelUsuario.VENDEDOR)
    db.add_all([admin, vendedor])
    db.commit()
    db.refresh(admin)
    db.refresh(vendedor)
    return admin, vendedor


def _cliente_ouro_id(db):
    return db.query(Cliente).filter(Cliente.nome == "Empresa Ouro LTDA").first().id


def _visita_finalizada(db, *, cliente_id, vendedor_id, inicio, duracao_min=20, retorno_dias=None):
    v = Visita(
        cliente_id=cliente_id, vendedor_id=vendedor_id, inicio=inicio,
        fim=inicio + timedelta(minutes=duracao_min), status=StatusVisita.FINALIZADA,
        observacao="ok", retorno_dias=retorno_dias,
        retorno_data=(inicio.date() + timedelta(days=retorno_dias)) if retorno_dias else None,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _auth(usuario):
    return {"Authorization": f"Bearer {auth.criar_token(usuario)}"}


def test_filtra_por_periodo_em_brasilia_nao_em_utc(cliente_http, db, admin_e_vendedor):
    """Visita às 22h de 24/08 em Brasília é gravada como 25/08 01h em UTC —
    pedir o relatório do dia 24 tem que trazer essa visita, e o do dia 25 não."""
    _, vendedor = admin_e_vendedor
    cliente_id = _cliente_ouro_id(db)
    _visita_finalizada(db, cliente_id=cliente_id, vendedor_id=vendedor.id, inicio=datetime(2026, 8, 25, 1, 0, 0))

    r = cliente_http.get("/api/relatorios/visitas?inicio=2026-08-24&fim=2026-08-24", headers=_auth(vendedor))
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["resumo"]["totalVisitas"] == 1
    assert corpo["visitas"][0]["clienteNome"] == "Empresa Ouro LTDA"

    r2 = cliente_http.get("/api/relatorios/visitas?inicio=2026-08-25&fim=2026-08-25", headers=_auth(vendedor))
    assert r2.json()["resumo"]["totalVisitas"] == 0


def test_vendedor_so_ve_as_proprias_visitas(cliente_http, db, admin_e_vendedor):
    _, vendedor = admin_e_vendedor
    outro = Usuario(nome="Outro Vendedor", usuario="outro", senha_hash=auth.gerar_hash("123456"), papel=PapelUsuario.VENDEDOR)
    db.add(outro)
    db.commit()
    db.refresh(outro)
    cliente_id = _cliente_ouro_id(db)
    _visita_finalizada(db, cliente_id=cliente_id, vendedor_id=outro.id, inicio=datetime(2026, 8, 24, 12, 0, 0))

    r = cliente_http.get("/api/relatorios/visitas?inicio=2026-08-24&fim=2026-08-24", headers=_auth(vendedor))
    assert r.json()["resumo"]["totalVisitas"] == 0


def test_vendedor_nao_pode_pedir_relatorio_de_outro_vendedor(cliente_http, admin_e_vendedor):
    admin, vendedor = admin_e_vendedor
    r = cliente_http.get(
        f"/api/relatorios/visitas?inicio=2026-08-24&fim=2026-08-24&vendedorId={admin.id}",
        headers=_auth(vendedor),
    )
    assert r.status_code == 403


def test_admin_ve_visitas_de_todos_por_padrao(cliente_http, db, admin_e_vendedor):
    admin, vendedor = admin_e_vendedor
    cliente_id = _cliente_ouro_id(db)
    _visita_finalizada(db, cliente_id=cliente_id, vendedor_id=vendedor.id, inicio=datetime(2026, 8, 24, 9, 0, 0))
    _visita_finalizada(db, cliente_id=cliente_id, vendedor_id=admin.id, inicio=datetime(2026, 8, 24, 10, 0, 0))

    r = cliente_http.get("/api/relatorios/visitas?inicio=2026-08-24&fim=2026-08-24", headers=_auth(admin))
    assert r.json()["resumo"]["totalVisitas"] == 2


def test_resumo_calcula_duracao_media_promessas_e_retornos(cliente_http, db, admin_e_vendedor):
    _, vendedor = admin_e_vendedor
    cliente_id = _cliente_ouro_id(db)
    v1 = _visita_finalizada(db, cliente_id=cliente_id, vendedor_id=vendedor.id,
                             inicio=datetime(2026, 8, 24, 9, 0, 0), duracao_min=10, retorno_dias=7)
    _visita_finalizada(db, cliente_id=cliente_id, vendedor_id=vendedor.id,
                        inicio=datetime(2026, 8, 24, 10, 0, 0), duracao_min=30)
    db.add(Promessa(cliente_id=cliente_id, visita_origem_id=v1.id, texto="Levar amostra"))
    db.commit()

    r = cliente_http.get("/api/relatorios/visitas?inicio=2026-08-24&fim=2026-08-24", headers=_auth(vendedor))
    resumo = r.json()["resumo"]
    assert resumo["totalVisitas"] == 2
    assert resumo["clientesUnicos"] == 1
    assert resumo["duracaoMediaMin"] == 20  # média de 10 e 30
    assert resumo["promessasFeitas"] == 1
    assert resumo["retornosAgendados"] == 1


def test_fim_antes_do_inicio_e_rejeitado(cliente_http, admin_e_vendedor):
    _, vendedor = admin_e_vendedor
    r = cliente_http.get("/api/relatorios/visitas?inicio=2026-08-24&fim=2026-08-20", headers=_auth(vendedor))
    assert r.status_code == 400


def test_exige_autenticacao(cliente_http):
    r = cliente_http.get("/api/relatorios/visitas?inicio=2026-08-24&fim=2026-08-24")
    assert r.status_code == 401
