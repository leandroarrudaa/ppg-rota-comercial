"""Listagem de gestão, alteração em lote e agenda de visitas."""
from datetime import date, datetime, timedelta

import pytest

from app.models import Cliente, OrigemCliente, StatusCliente, StatusVisita, Visita
from app.services import clientes as svc
from app.services import visitas as vsvc


@pytest.fixture
def token(cliente_http):
    return cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    ).json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------- listagem de gestão

def test_mostra_inativos_quando_pedido(db):
    """Diferente do mapa e da rota, aqui o inativo precisa aparecer — é como
    o gerente acha o que ele mesmo inativou."""
    so_ativos, _ = svc.listar_admin(db, status="ativo")
    so_inativos, _ = svc.listar_admin(db, status="inativo")
    todos, _ = svc.listar_admin(db, status="todos")

    assert all(c.status == StatusCliente.ATIVO for c in so_ativos)
    assert [c.nome for c in so_inativos] == ["Empresa Fechada LTDA"]
    assert len(todos) == len(so_ativos) + len(so_inativos)


def test_mostra_quem_nao_tem_coordenada(db):
    """Quem não tem lat/lng some do mapa e da rota — esta tela é o único
    lugar onde ele pode ser encontrado e corrigido."""
    db.add(Cliente(nome="Sem Localizacao LTDA", cnpj="77.777.777/0001-77",
                   origem=OrigemCliente.ANTIGO, status=StatusCliente.ATIVO))
    db.commit()

    registros, total = svc.listar_admin(db, sem_localizacao=True)
    assert total == 1
    assert registros[0].nome == "Sem Localizacao LTDA"

    # a listagem que alimenta o mapa continua escondendo
    assert all(c.nome != "Sem Localizacao LTDA" for c in svc.listar(db))


def test_busca_por_nome_cnpj_ou_cidade(db):
    por_nome, _ = svc.listar_admin(db, busca="Ouro")
    por_cnpj, _ = svc.listar_admin(db, busca="22.222")
    por_cidade, _ = svc.listar_admin(db, busca="Ponta Grossa")

    assert [c.nome for c in por_nome] == ["Empresa Ouro LTDA"]
    assert [c.nome for c in por_cnpj] == ["Empresa Bronze ME"]
    assert [c.nome for c in por_cidade] == ["Empresa Bronze ME"]


def test_pagina_e_conta_o_total_separadamente(db):
    """A carteira tem milhares de linhas: a tela precisa do total sem baixar
    tudo."""
    for i in range(8):
        db.add(Cliente(nome=f"Empresa {i}", cnpj=f"90.000.00{i}/0001-00",
                       origem=OrigemCliente.ANTIGO, fat_total=i * 100,
                       lat=-25.0, lng=-50.0))
    db.commit()

    pagina1, total = svc.listar_admin(db, tamanho=3, pagina=1)
    pagina2, _ = svc.listar_admin(db, tamanho=3, pagina=2)

    assert total > 3
    assert len(pagina1) == 3
    assert {c.id for c in pagina1}.isdisjoint({c.id for c in pagina2})


def test_ordena_por_faturamento_com_nulos_no_fim(db):
    registros, _ = svc.listar_admin(db, status="todos", ordenar="faturamento", direcao="desc")
    faturamentos = [c.fat_total for c in registros if c.fat_total is not None]
    assert faturamentos == sorted(faturamentos, reverse=True)


def test_vendedor_nao_acessa_a_tela_de_gestao(cliente_http, token):
    cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Taborda", "usuario": "taborda", "senha": "123456", "papel": "vendedor"},
        headers=_auth(token),
    )
    token_vendedor = cliente_http.post(
        "/api/auth/login", json={"usuario": "taborda", "senha": "123456"}
    ).json()["token"]

    assert cliente_http.get("/api/clientes/admin", headers=_auth(token_vendedor)).status_code == 403


def test_rota_admin_nao_e_confundida_com_a_ficha_de_um_cliente(cliente_http, token):
    """/api/clientes/admin precisa vir ANTES de /api/clientes/{id} na ordem
    das rotas, senão 'admin' é lido como id de cliente."""
    resposta = cliente_http.get("/api/clientes/admin", headers=_auth(token))
    assert resposta.status_code == 200
    assert "itens" in resposta.json()


# --------------------------------------------------- alteração em lote

def test_inativa_e_reativa_em_lote(db):
    """Em lote porque o banco fica longe: uma chamada por cliente tornaria a
    limpeza da lista inviável."""
    ids = [c.id for c in svc.listar_admin(db, status="ativo")[0]]

    assert svc.alterar_status_em_lote(db, ids, StatusCliente.INATIVO) == len(ids)
    db.commit()
    assert svc.listar_admin(db, status="ativo")[1] == 0

    svc.alterar_status_em_lote(db, ids, StatusCliente.ATIVO)
    db.commit()
    assert svc.listar_admin(db, status="ativo")[1] == len(ids)


def test_lote_vazio_nao_quebra(db):
    assert svc.alterar_status_em_lote(db, [], StatusCliente.INATIVO) == 0


# --------------------------------------------------- agenda de visitas

def _visita(db, cliente_id, vendedor_id, dias_atras, retorno_data=None):
    inicio = datetime(2026, 9, 1) - timedelta(days=dias_atras)
    db.add(Visita(
        cliente_id=cliente_id, vendedor_id=vendedor_id, inicio=inicio, fim=inicio,
        status=StatusVisita.FINALIZADA, retorno_data=retorno_data,
    ))


def test_a_data_combinada_no_relatorio_manda(db):
    """O vendedor já escolhe 'voltar em X dias' ao fechar cada visita. Esse
    dado existia e nunca era lido — é a base de tudo aqui."""
    agenda = {"ultima_visita": datetime(2026, 7, 2), "retorno_data": date(2026, 7, 17)}
    ultima, proxima = vsvc.proxima_visita(agenda, "Ouro")
    assert ultima == date(2026, 7, 2)
    assert proxima == date(2026, 7, 17), "a combinação vale mais que a cadência da faixa"


def test_sem_combinacao_usa_a_cadencia_da_faixa(db):
    agenda = {"ultima_visita": datetime(2026, 8, 1), "retorno_data": None}
    assert vsvc.proxima_visita(agenda, "Ouro")[1] == date(2026, 8, 31)     # 30 dias
    assert vsvc.proxima_visita(agenda, "Prata")[1] == date(2026, 9, 15)    # 45 dias
    assert vsvc.proxima_visita(agenda, "Bronze")[1] == date(2026, 9, 30)   # 60 dias


def test_nunca_visitado_fica_sem_data(db):
    """Sem data = disponível agora, com prioridade — não 'atrasado desde
    sempre', que jogaria todo mundo para o topo da fila."""
    assert vsvc.proxima_visita(None, "Ouro") == (None, None)
    assert vsvc.proxima_visita({"ultima_visita": None}, "Ouro") == (None, None)


def test_faixa_desconhecida_cai_no_padrao(db):
    agenda = {"ultima_visita": datetime(2026, 8, 1), "retorno_data": None}
    assert vsvc.proxima_visita(agenda, None)[1] == date(2026, 9, 30)


def test_agenda_vale_para_a_empresa_toda_nao_por_vendedor(cliente_http, token, db):
    """Decisão explícita: cliente visitado é cliente visitado, para dois
    vendedores não baterem na mesma porta."""
    from app.models import Usuario
    outro = Usuario(nome="Outro", usuario="outro2", senha_hash="x")
    db.add(outro)
    db.commit()

    cliente = svc.listar_admin(db, status="ativo")[0][0]
    _visita(db, cliente.id, outro.id, dias_atras=5)
    db.commit()

    agenda = vsvc.agenda_de_visitas(db)
    assert cliente.id in agenda, "a visita de outro vendedor também conta"


def test_agenda_usa_a_visita_mais_recente(db):
    from app.models import Usuario
    vendedor = Usuario(nome="V", usuario="v", senha_hash="x")
    db.add(vendedor)
    db.commit()

    cliente = svc.listar_admin(db, status="ativo")[0][0]
    _visita(db, cliente.id, vendedor.id, dias_atras=90)
    _visita(db, cliente.id, vendedor.id, dias_atras=10)
    db.commit()

    agenda = vsvc.agenda_de_visitas(db, [cliente.id])
    assert agenda[cliente.id]["ultima_visita"].date() == date(2026, 8, 22)


def test_visita_nao_finalizada_nao_conta(db):
    """Visita aberta ou aguardando relatório ainda não aconteceu por
    completo — não pode tirar o cliente da fila."""
    from app.models import Usuario
    vendedor = Usuario(nome="V", usuario="v2", senha_hash="x")
    db.add(vendedor)
    db.commit()

    cliente = svc.listar_admin(db, status="ativo")[0][0]
    db.add(Visita(cliente_id=cliente.id, vendedor_id=vendedor.id,
                  inicio=datetime(2026, 8, 30), status=StatusVisita.ABERTA))
    db.commit()

    assert vsvc.agenda_de_visitas(db, [cliente.id]) == {}


def test_cliente_sai_com_a_agenda_na_resposta_da_api(cliente_http, token, db):
    """É por esses campos que o Plano da Semana decide quem entra."""
    corpo = cliente_http.get("/api/clientes", headers=_auth(token)).json()
    assert corpo, "a carteira de teste não pode estar vazia"
    assert "ultimaVisita" in corpo[0]
    assert "proximaVisita" in corpo[0]


def test_toda_coluna_ordena_nos_dois_sentidos(db):
    """O cabeçalho da tabela é clicável e o segundo clique inverte, então cada
    coluna precisa das duas direções no servidor — ordenar só a página visível
    daria uma ordem falsa sobre a carteira inteira."""
    # dados próprios: os clientes da fixture não têm nota nem data de compra,
    # e com valores iguais as duas direções dariam a mesma ordem sem provar nada
    for i, (nome, cidade, fat, score, dia) in enumerate([
        ("Alfa LTDA", "Araucaria", 1000.0, 5, date(2026, 1, 10)),
        ("Beta LTDA", "Curitiba", 50000.0, 12, date(2026, 6, 20)),
        ("Gama LTDA", "Ponta Grossa", 9000.0, 9, date(2026, 3, 5)),
    ]):
        db.add(Cliente(nome=nome, cidade=cidade, cnpj=f"60.000.00{i}/0001-00",
                       origem=OrigemCliente.ANTIGO, fat_total=fat, rfm_score=score,
                       ultima_compra=dia, lat=-25.0, lng=-50.0))
    db.commit()

    for campo in ("nome", "cidade", "faturamento", "rfm", "ultimaCompra"):
        subindo, _ = svc.listar_admin(db, ordenar=campo, direcao="asc", status="todos")
        descendo, _ = svc.listar_admin(db, ordenar=campo, direcao="desc", status="todos")
        assert [c.id for c in subindo] != [c.id for c in descendo], campo


def test_nulos_ficam_no_fim_nos_dois_sentidos(db):
    """Cliente sem faturamento não é 'o menor', é 'não sei' — no topo da lista
    ele só atrapalharia quem está procurando o maior ou o menor de verdade."""
    db.add(Cliente(nome="Sem Numero", origem=OrigemCliente.NOVO, fat_total=None))
    db.commit()
    for direcao in ("asc", "desc"):
        registros, _ = svc.listar_admin(db, ordenar="faturamento", direcao=direcao, status="todos")
        assert registros[-1].fat_total is None, direcao


def test_ordenar_por_nota_rfm(db):
    """A nota agora aparece na tela de gestão, então precisa dar para ordenar
    por ela — faturamento alto com nota baixa é justamente o que se procura."""
    for i, score in enumerate([3, 15, 9]):
        db.add(Cliente(nome=f"Empresa {score}", cnpj=f"70.000.00{i}/0001-00",
                       origem=OrigemCliente.ANTIGO, rfm_score=score,
                       r=1, f=1, m=1, lat=-25.0, lng=-50.0))
    db.commit()

    registros, _ = svc.listar_admin(db, ordenar="rfm", direcao="desc", status="todos")
    notas = [c.rfm_score for c in registros if c.rfm_score is not None]
    assert notas == sorted(notas, reverse=True)
    assert notas[0] == 15


def test_cliente_sem_nota_nao_quebra_a_ordenacao(db):
    """Lead cadastrado em campo não tem RFM — vai para o fim, não estoura."""
    db.add(Cliente(nome="Lead sem nota", origem=OrigemCliente.NOVO, rfm_score=None))
    db.commit()
    registros, _ = svc.listar_admin(db, ordenar="rfm", direcao="desc", status="todos")
    assert registros[-1].rfm_score is None


def test_a_api_devolve_as_tres_notas_separadas(cliente_http, token):
    """A tela mostra R, F e M individualmente, não só o total — é o que
    explica POR QUE o cliente está na faixa em que está."""
    corpo = cliente_http.get("/api/clientes/admin", headers=_auth(token)).json()
    primeiro = corpo["itens"][0]
    for campo in ("R", "F", "M", "score"):
        assert campo in primeiro
