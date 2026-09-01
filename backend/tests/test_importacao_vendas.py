"""Relatório de vendas do ERP: leitura do formato e importação incremental."""
from datetime import date

import pytest

from app.models import Cliente, MapaCodigoErp, OrigemCliente, PedidoImportado
from app.services.fontes import relatorio_vendas as rv
from app.services.importacao import aplicar_relatorio_vendas

# Reproduz a ESTRUTURA do arquivo real (relatório de impressão, ponto-e-vírgula
# de recheio, valores em padrão brasileiro, cliente identificado só por
# "código - nome" e sem CNPJ nenhum) — mas com nomes e produtos inventados.
# Dado de cliente real não entra em teste: teste vai para o repositório.
RELATORIO = """Pedidos com Produtos (Detalhado);;;;
PPG - PARAFUSOS E FERRAMENTAS;;;;

Cliente:;729 - METALFICTA COMERCIO DE PECAS LTDA;;;;
Pedido:;26367;;;Data Cadastro:;01/08/2026;;;Cond. Pagto:;;;;;;CARTAO;;;;;;;;;;Vendedor:;;;5 - TABORDA;;;;
Codigo;;;Descricao;;;;;;;;;;;;Vlr Custo;;;;;;Unid;;;Qtde;;;Vlr Venda;;;;Total;;

5018;;;PECA DE TESTE A ;;;;;;;;;;;;0,43;;;;;;UN;;;200;;;0,77;;;;154,00;;
212;;;PECA DE TESTE B ;;;;;;;;;;;;0,02;;;;;;UN;;;200;;;0,08;;;;16,00;;
Total Custo:;;;90,00;;;;;;Desconto:;;;;0,00;;;;;Total Liq:;;;;170,00;;

Cliente:;10340 - FULANO DE TAL;;;;
Pedido:;26368;;;Data Cadastro:;02/08/2026;;;Cond. Pagto:;;;;;;DINHEIRO;;;;;;;;;;Vendedor:;;;8 - EDUARDO;;;;
Codigo;;;Descricao;;;;;;;;;;;;Vlr Custo;;;;;;Unid;;;Qtde;;;Vlr Venda;;;;Total;;

3620;;;PECA DE TESTE C ;;;;;;;;;;;;1,12;;;;;;PC;;;1;;;3,50;;;;3,50;;
Total Custo:;;;1,12;;;;;;Desconto:;;;;0,00;;;;;Total Liq:;;;;3,50;;
"""

CNPJ_ROL = "44444444000144"  # não semeado pelo conftest, de propósito


# ------------------------------------------------------------ leitura

def test_le_pedidos_itens_e_metadados():
    pedidos = rv.ler(RELATORIO)
    assert len(pedidos) == 2

    primeiro = pedidos[0]
    assert primeiro.numero == "26367"
    assert primeiro.codigo_cliente == "729"
    assert primeiro.nome_cliente == "METALFICTA COMERCIO DE PECAS LTDA"
    assert primeiro.data == date(2026, 8, 1)
    assert primeiro.vendedor == "5 - TABORDA"
    assert primeiro.total == 170.00
    assert len(primeiro.itens) == 2
    assert primeiro.itens[0]["codigo"] == "5018"
    assert primeiro.itens[0]["total"] == 154.00


def test_usa_o_total_liquido_e_nao_a_soma_dos_itens():
    """O Total Liq já desconta; somar os itens inflaria o faturamento."""
    relatorio = RELATORIO.replace("Desconto:;;;;0,00;;;;;Total Liq:;;;;170,00", "Desconto:;;;;20,00;;;;;Total Liq:;;;;150,00")
    pedidos = rv.ler(relatorio)
    assert pedidos[0].total == 150.00
    assert sum(i["total"] for i in pedidos[0].itens) == 170.00


def test_aceita_bytes_em_latin1():
    """O ERP exporta em latin-1, não em UTF-8."""
    pedidos = rv.ler(RELATORIO.replace("Descricao", "Descrição").encode("latin-1"))
    assert len(pedidos) == 2


def test_pedido_com_linha_truncada_nao_derruba_a_importacao():
    """Acontece no arquivo real: uma linha sai cortada no meio pelo próprio
    ERP. Um pedido defeituoso não pode custar o mês inteiro."""
    relatorio = RELATORIO.replace(
        "Pedido:;26368;;;Data Cadastro:;02/08/2026;;;Cond. Pagto:;;;;;;DINHEIRO;;;;;;;;;;Vendedor:;;;8 - EDUARDO;;;;",
        "Pedido:;26368;;;Data Cadastro:",
    )
    pedidos = rv.ler(relatorio)
    assert len(pedidos) == 2
    assert pedidos[1].data is None
    assert pedidos[0].data == date(2026, 8, 1)


def test_arquivo_que_nao_e_o_relatorio_da_erro_amigavel():
    with pytest.raises(rv.RelatorioInvalido) as erro:
        rv.ler("nome;cnpj;valor\nEmpresa;123;10,00\n")
    assert "Pedidos com Produtos" in str(erro.value)


def test_periodo_do_arquivo():
    assert rv.periodo(rv.ler(RELATORIO)) == (date(2026, 8, 1), date(2026, 8, 2))


# ------------------------------------------------------------ importação

@pytest.fixture
def carteira(db):
    """Um cliente da carteira com de-para, e o código de balcão sem de-para."""
    cliente = Cliente(
        cnpj="44.444.444/0001-44", nome="Metalficta Comercio de Pecas LTDA",
        origem=OrigemCliente.ANTIGO, no_compras=10, fat_total=5000.0,
        primeira_compra=date(2021, 1, 1), ultima_compra=date(2026, 5, 1),
        faixa="Prata",
    )
    db.add(cliente)
    db.add(MapaCodigoErp(codigo="729", cnpj=CNPJ_ROL))
    db.commit()
    return cliente


def test_soma_os_pedidos_no_acumulado_do_cliente(db, carteira):
    relatorio = aplicar_relatorio_vendas(db, rv.ler(RELATORIO))
    db.commit()
    db.refresh(carteira)

    assert carteira.no_compras == 11
    assert carteira.fat_total == 5170.0
    assert carteira.ultima_compra == date(2026, 8, 1)
    assert relatorio.clientes_atualizados == 1
    assert relatorio.faturamento == 170.0


def test_subir_o_mesmo_arquivo_de_novo_nao_soma_duas_vezes(db, carteira):
    """A proteção mais importante: a importação é incremental, e reenviar o
    arquivo do mês ('será que subiu mesmo?') dobraria o faturamento."""
    aplicar_relatorio_vendas(db, rv.ler(RELATORIO))
    db.commit()
    fat_apos_primeira = carteira.fat_total
    compras_apos_primeira = carteira.no_compras

    segunda = aplicar_relatorio_vendas(db, rv.ler(RELATORIO))
    db.commit()
    db.refresh(carteira)

    assert segunda.pedidos_novos == 0
    assert segunda.pedidos_ja_importados == 2
    assert segunda.clientes_atualizados == 0
    assert carteira.fat_total == fat_apos_primeira
    assert carteira.no_compras == compras_apos_primeira


def test_venda_de_balcao_sem_depara_e_contada_mas_nao_vira_cliente(db, carteira):
    """85% do arquivo é CPF/balcão. Eles são registrados como importados para
    não serem reprocessados, mas não entram na carteira."""
    antes = db.query(Cliente).count()
    relatorio = aplicar_relatorio_vendas(db, rv.ler(RELATORIO))
    db.commit()

    assert relatorio.sem_depara == 1              # o pedido do FULANO DE TAL
    assert db.query(Cliente).count() == antes     # ninguém foi criado
    assert db.query(PedidoImportado).count() == 2  # os dois ficam registrados


def test_cnpj_conhecido_mas_fora_da_carteira_e_reportado(db):
    """Empresa que compra e ainda não é cliente — precisa aparecer para o
    gerente decidir, nunca ser criada sem endereço."""
    db.add(MapaCodigoErp(codigo="729", cnpj=CNPJ_ROL))
    db.commit()

    relatorio = aplicar_relatorio_vendas(db, rv.ler(RELATORIO))
    db.commit()

    assert relatorio.cnpj_fora_da_carteira == 1
    assert "METALFICTA COMERCIO DE PECAS LTDA" in relatorio.nomes_fora_da_carteira
    assert db.query(Cliente).filter(Cliente.cnpj == CNPJ_ROL).count() == 0


def test_pedido_sem_data_ainda_soma_faturamento(db, carteira):
    """A data serve para a recência; sem ela o pedido ainda é uma compra."""
    relatorio_sem_data = RELATORIO.replace("Data Cadastro:;01/08/2026", "Data Cadastro:")
    aplicar_relatorio_vendas(db, rv.ler(relatorio_sem_data))
    db.commit()
    db.refresh(carteira)

    assert carteira.fat_total == 5170.0
    assert carteira.ultima_compra == date(2026, 5, 1), "data antiga preservada"


def test_recalcula_o_rfm_da_carteira_inteira(db, carteira):
    """As notas são por quintil: mexer num cliente muda a posição relativa de
    todos, então recalcular só os tocados daria notas incoerentes."""
    outro = Cliente(
        cnpj="99.999.999/0001-99", nome="Outra Empresa", origem=OrigemCliente.ANTIGO,
        no_compras=1, fat_total=50.0, primeira_compra=date(2026, 1, 1),
        ultima_compra=date(2026, 1, 1), faixa=None, rfm_score=None,
    )
    db.add(outro)
    db.commit()

    aplicar_relatorio_vendas(db, rv.ler(RELATORIO))
    db.commit()
    db.refresh(outro)

    assert outro.faixa is not None, "quem não teve pedido também é reavaliado"
    assert outro.rfm_score is not None
