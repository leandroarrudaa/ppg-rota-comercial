"""Reimportação da carteira NÃO pode sobrescrever campos donos do app."""
from datetime import date

from app.models import Cliente, MotivoRecusaVisita, OrigemCliente, StatusCliente
from app.services.importacao import aplicar_vendas, upsert_clientes_antigos


def _registro(cnpj, faixa, fat_total):
    """Registro mínimo no formato que o pipeline produz (todas as chaves de CAMPOS_PIPELINE)."""
    return {
        "cnpj": cnpj, "nome": "Empresa Teste", "endereco": None, "bairro": None, "cep": None,
        "cidade": "Curitiba", "uf": "PR", "lat": -25.4, "lng": -49.2, "geo_status": "preciso",
        "faixa": faixa, "em_risco": False, "fat_total": fat_total, "no_compras": 10,
        "ticket_medio": fat_total / 10, "recencia_dias": 5, "cadencia_dias": 30,
        "ultima_compra": None, "r": 5, "f": 5, "m": 5, "rfm_score": 15,
        "porte": "Pequena", "capital_social": None, "cnae": "Comércio", "telefone": None,
        "email": None,
    }


def test_cria_cliente_novo(db):
    resultado = upsert_clientes_antigos(db, [_registro("44.444.444/0001-44", "Ouro", 60000)])
    db.commit()
    assert resultado == {"criados": 1, "atualizados": 0}
    cliente = db.query(Cliente).filter(Cliente.cnpj == "44.444.444/0001-44").one()
    assert cliente.faixa == "Ouro"
    assert cliente.origem == OrigemCliente.ANTIGO


def test_reimportacao_preserva_campos_do_app(db):
    # cliente já existe no banco, com dados "do app" preenchidos pelo uso real
    cliente = Cliente(
        cnpj="55.555.555/0001-55", nome="Empresa Antiga", origem=OrigemCliente.ANTIGO,
        faixa="Bronze", fat_total=1000, status=StatusCliente.INATIVO,
        aceita_visita=False, motivo_recusa_visita=MotivoRecusaVisita.CALOTE,
        contato_nome="Sr. João", contato_celular="42999990000",
    )
    db.add(cliente)
    db.commit()

    # reprocessamento do Excel: RFM mudou (agora Ouro, faturamento maior)
    resultado = upsert_clientes_antigos(
        db, [_registro("55.555.555/0001-55", "Ouro", 90000)]
    )
    db.commit()
    db.refresh(cliente)

    assert resultado == {"criados": 0, "atualizados": 1}
    # campos do pipeline foram atualizados
    assert cliente.faixa == "Ouro"
    assert cliente.fat_total == 90000
    # campos donos do app permanecem intocados
    assert cliente.status == StatusCliente.INATIVO
    assert cliente.aceita_visita is False
    assert cliente.motivo_recusa_visita == MotivoRecusaVisita.CALOTE
    assert cliente.contato_nome == "Sr. João"
    assert cliente.contato_celular == "42999990000"


def test_registro_sem_cnpj_e_ignorado(db):
    total_antes = db.query(Cliente).count()  # fixture já semeia 3 clientes
    resultado = upsert_clientes_antigos(db, [_registro("", "Ouro", 1000)])
    db.commit()
    assert resultado == {"criados": 0, "atualizados": 0}
    assert db.query(Cliente).count() == total_antes


# ---------------------------------------------------------- atualização de vendas
# (banco mestre / relatório do ERP — só mexem em número de compra, nunca em cadastro)

def _venda(cnpj, **extra):
    """Registro no formato que o cálculo de RFM devolve."""
    dados = {
        "cnpj": cnpj, "nome": "Nome Vindo Das Notas", "no_compras": 50,
        "fat_total": 90000.0, "ticket_medio": 1800.0, "recencia_dias": 3,
        "cadencia_dias": 20, "ultima_compra": date(2026, 7, 31),
        "r": 5, "f": 5, "m": 5, "rfm_score": 15, "faixa": "Ouro", "em_risco": False,
    }
    dados.update(extra)
    return dados


def test_atualizacao_de_vendas_nao_apaga_endereco_nem_coordenada(db):
    """Regressão do risco mais caro: as vendas não trazem endereço nem lat/lng.
    Se esses campos fossem atualizados junto, a primeira importação zeraria a
    localização da carteira inteira e o mapa ficaria vazio."""
    cliente = Cliente(
        cnpj="66.666.666/0001-66", nome="Nome Bom no App", origem=OrigemCliente.ANTIGO,
        endereco="Rua das Flores, 100", bairro="Centro", cep="84010-000",
        cidade="Ponta Grossa", uf="PR", lat=-25.09, lng=-50.16, geo_status="manual",
        telefone="4232221100", porte="Pequena", cnae="Comércio",
        faixa="Bronze", fat_total=1000, no_compras=3,
    )
    db.add(cliente)
    db.commit()

    relatorio = aplicar_vendas(db, [_venda("66666666000166")])
    db.commit()
    db.refresh(cliente)

    assert relatorio.atualizados == 1
    # o que a venda SABE foi atualizado
    assert cliente.faixa == "Ouro"
    assert cliente.fat_total == 90000.0
    assert cliente.no_compras == 50
    assert cliente.ultima_compra == date(2026, 7, 31)
    # o que a venda NÃO sabe ficou intacto
    assert cliente.endereco == "Rua das Flores, 100"
    assert cliente.bairro == "Centro"
    assert cliente.cep == "84010-000"
    assert cliente.lat == -25.09
    assert cliente.lng == -50.16
    assert cliente.geo_status == "manual"
    assert cliente.telefone == "4232221100"
    assert cliente.porte == "Pequena"
    assert cliente.cnae == "Comércio"
    assert cliente.nome == "Nome Bom no App", "o nome do app não é sobrescrito pelo nome da nota"


def test_atualizacao_de_vendas_preserva_campos_donos_do_app(db):
    cliente = Cliente(
        cnpj="77.777.777/0001-77", nome="Empresa", origem=OrigemCliente.ANTIGO,
        status=StatusCliente.INATIVO, aceita_visita=False,
        motivo_recusa_visita=MotivoRecusaVisita.CALOTE,
        contato_nome="Dona Maria", contato_celular="42988887777",
        faixa="Bronze", fat_total=500,
    )
    db.add(cliente)
    db.commit()

    aplicar_vendas(db, [_venda("77777777000177")])
    db.commit()
    db.refresh(cliente)

    assert cliente.faixa == "Ouro"
    assert cliente.status == StatusCliente.INATIVO
    assert cliente.aceita_visita is False
    assert cliente.motivo_recusa_visita == MotivoRecusaVisita.CALOTE
    assert cliente.contato_nome == "Dona Maria"
    assert cliente.contato_celular == "42988887777"


def test_cnpj_sem_cliente_na_carteira_e_reportado_e_nao_criado(db):
    """Cliente sem endereço não apareceria no mapa — vira lixo invisível.
    A decisão de criar é humana, então aqui ele só é listado."""
    antes = db.query(Cliente).count()
    relatorio = aplicar_vendas(db, [_venda("88888888000188", nome="Empresa Nova LTDA")])
    db.commit()

    assert db.query(Cliente).count() == antes
    assert relatorio.atualizados == 0
    assert relatorio.sem_cliente_na_carteira == ["Empresa Nova LTDA"]


def test_relatorio_aponta_quem_sai_de_risco_e_muda_de_faixa(db):
    """É o que o gerente lê na prévia antes de confirmar a importação."""
    cliente = Cliente(
        cnpj="99.999.999/0001-99", nome="Voltou a Comprar LTDA",
        origem=OrigemCliente.ANTIGO, faixa="Prata", em_risco=True,
        ultima_compra=date(2025, 1, 30), fat_total=40000,
    )
    db.add(cliente)
    db.commit()

    relatorio = aplicar_vendas(db, [_venda("99999999000199")])
    db.commit()

    assert relatorio.saiu_de_risco == ["Voltou a Comprar LTDA"]
    assert relatorio.mudou_faixa == [("Voltou a Comprar LTDA", "Prata", "Ouro")]
    assert relatorio.recencia_corrigida == 1
    assert relatorio.resumo()["saiuDeRisco"] == 1


def test_cnpj_casa_mesmo_com_formatacao_diferente(db):
    """A carteira guarda formatado, o banco mestre guarda só dígitos."""
    db.add(Cliente(cnpj="12.345.678/0001-90", nome="Formatada LTDA",
                   origem=OrigemCliente.ANTIGO, faixa="Bronze"))
    db.commit()
    relatorio = aplicar_vendas(db, [_venda("12345678000190")])
    db.commit()
    assert relatorio.atualizados == 1
    assert relatorio.sem_cliente_na_carteira == []
