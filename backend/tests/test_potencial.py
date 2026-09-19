"""Nota de potencial ouro: partes, recência ao contrário e igualdade Python x SQL."""
import itertools

import pytest

from app.models import Cliente, OrigemCliente, Prospecto, StatusCliente
from app.services import potencial as pot
from app.services.ramos import RAMO_OUTROS, TIPO_EMPRESA, TIPO_MEI, ramo_por_descricao


def test_ramo_por_descricao_da_carteira():
    assert ramo_por_descricao("Instalação e manutenção elétrica") == "Elétrica (instalação/manutenção)"
    assert ramo_por_descricao("Fabricação de artigos de serralheria, exceto esquadrias") == "Metalurgia / serralheria / esquadrias"
    assert ramo_por_descricao("Incorporação de empreendimentos imobiliários") == "Condomínios / imobiliário"
    assert ramo_por_descricao("Cabeleireiros, manicure e pedicure") == RAMO_OUTROS
    assert ramo_por_descricao(None) == RAMO_OUTROS


def test_estrutura_por_tres_sinais():
    assert pot.nivel_estrutura(TIPO_EMPRESA, 200_000, "Pequena") == "alta"
    assert pot.nivel_estrutura(TIPO_EMPRESA, 5_000, "Micro") == "media"   # só é empresa
    assert pot.nivel_estrutura(TIPO_MEI, 1_000, "Micro") == "baixa"
    assert pot.nivel_estrutura(TIPO_MEI, 80_000, "Pequena") == "alta"


def test_reativacao_premia_quem_parou_de_vir():
    """O contrário do RFM: recência alta (sumiu) vale MAIS que recência baixa."""
    assert pot.pontos_reativacao(30) < pot.pontos_reativacao(120) < pot.pontos_reativacao(400)
    assert pot.pontos_reativacao(400) == pot.pontos_reativacao(700) == 10
    assert pot.pontos_reativacao(1500) < 10  # muito tempo: pode ter fechado
    assert pot.pontos_reativacao(None) == 0


def test_cliente_que_sumiu_tem_nota_maior_que_o_que_compra_toda_semana():
    base = dict(ramo="Construção civil / obras", tipo=TIPO_EMPRESA, capital=200_000, porte="Pequena", compras=12)
    sumido, _ = pot.calcular_nota(**base, recencia_dias=300)
    fiel, _ = pot.calcular_nota(**base, recencia_dias=20)
    assert sumido > fiel


def test_nota_maxima_e_partes():
    nota, partes = pot.calcular_nota(
        ramo="Manutenção / montagem industrial", tipo=TIPO_EMPRESA, capital=500_000, porte="Pequena",
        compras=15, recencia_dias=300,
    )
    assert nota == 100
    assert partes == {"ramo": 35, "estrutura": 25, "capital": 20, "historico": 10, "reativacao": 10}


def test_sem_historico_reescala_para_0_a_100():
    nota, partes = pot.calcular_nota(
        ramo="Construção civil / obras", tipo=TIPO_EMPRESA, capital=500_000, porte="Demais")
    assert nota == 100 and "historico" not in partes
    nota_fraca, _ = pot.calcular_nota(ramo=RAMO_OUTROS, tipo=TIPO_MEI, capital=1_000, porte="Micro")
    assert nota_fraca == round(7 / 80 * 100 + 0.01)  # só o capital pontua (7 de 80)


def test_ouro_e_inativo_nao_tem_nota():
    assert pot.nota_de_cliente(Cliente(nome="X LTDA", faixa="Ouro", status=StatusCliente.ATIVO)) is None
    assert pot.nota_de_cliente(Cliente(nome="X LTDA", faixa="Prata", status=StatusCliente.INATIVO)) is None
    assert pot.nota_de_cliente(Cliente(nome="X LTDA", faixa="Prata", status=StatusCliente.ATIVO, no_compras=3,
                                       recencia_dias=200)) is not None


def test_ramo_gravado_no_cliente_vale_mais_que_o_cnae():
    c = Cliente(nome="Lead LTDA", faixa=None, status=StatusCliente.ATIVO, origem=OrigemCliente.NOVO,
                ramo="Construção civil / obras", cnae=None, capital_social=300_000, porte="Demais")
    nota, partes = pot.nota_de_cliente(c)
    assert partes["ramo"] == 35


def test_sql_e_python_dao_a_mesma_nota(db):
    """A nota que ordena a lista de prospectos (SQL) tem que ser a mesma da tela (Python)."""
    ramos = ["Construção civil / obras", "Móveis / madeira", RAMO_OUTROS]
    tipos = [TIPO_EMPRESA, TIPO_MEI]
    capitais = [None, 1_000, 30_000, 50_000, 99_999, 100_000, 5_000_000]
    portes = ["Micro", "Pequena", "Demais", "Sem dado"]
    for i, (r, t, c, p) in enumerate(itertools.product(ramos, tipos, capitais, portes)):
        db.add(Prospecto(cnpj=f"{i:014d}", razao_social="X", ramo=r, tipo=t, capital_social=c, porte=p))
    db.commit()
    linhas = db.query(Prospecto, pot.nota_sql(Prospecto)).all()
    assert len(linhas) == len(ramos) * len(tipos) * len(capitais) * len(portes)
    for p, nota_sql in linhas:
        esperado, _ = pot.calcular_nota(ramo=p.ramo, tipo=p.tipo, capital=p.capital_social, porte=p.porte)
        assert int(nota_sql) == esperado, (p.ramo, p.tipo, p.capital_social, p.porte)


def test_api_de_clientes_traz_nota_e_ouro_fica_sem(cliente_http, db):
    token = cliente_http.post("/api/auth/setup", json={"nome": "A", "usuario": "a", "senha": "123456"}).json()["token"]
    db.add(Cliente(nome="Metalurgica Beta LTDA", cnpj="55.555.555/0001-55", faixa="Prata", origem=OrigemCliente.ANTIGO,
                   status=StatusCliente.ATIVO, cnae="Fabricação de estruturas metálicas", capital_social=200_000,
                   porte="Pequena", no_compras=12, recencia_dias=300, lat=-25.1, lng=-50.1, geo_status="preciso"))
    db.commit()
    r = cliente_http.get("/api/clientes", headers={"Authorization": f"Bearer {token}"}).json()
    por_nome = {c["nome"]: c for c in r}
    prata = por_nome["Metalurgica Beta LTDA"]
    assert prata["notaPotencial"] == 100 and prata["ramo"] == "Metalurgia / serralheria / esquadrias"
    assert prata["potencialDetalhe"] == "Ramo 35 · Estrutura 25 · Capital 20 · Histórico 10 · Reativação 10"
    assert por_nome["Empresa Ouro LTDA"]["notaPotencial"] is None
