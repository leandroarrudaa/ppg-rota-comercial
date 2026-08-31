"""Ajustes do negócio: piso de faturamento para o alerta de risco."""
import pytest

from app.models import Cliente, OrigemCliente
from app.services import configuracoes as svc
from app.services import rfm


@pytest.fixture
def token(cliente_http):
    """Admin — o primeiro usuário criado pelo setup."""
    return cliente_http.post(
        "/api/auth/setup", json={"nome": "Antonio", "usuario": "antonio", "senha": "123456"}
    ).json()["token"]


@pytest.fixture
def token_vendedor(cliente_http, token):
    cliente_http.post(
        "/api/auth/usuarios",
        json={"nome": "Taborda", "usuario": "taborda", "senha": "123456", "papel": "vendedor"},
        headers=_auth(token),
    )
    return cliente_http.post(
        "/api/auth/login", json={"usuario": "taborda", "senha": "123456"}
    ).json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _cliente(db, nome, fat, m, r, em_risco):
    c = Cliente(nome=nome, cnpj=None, origem=OrigemCliente.ANTIGO,
                fat_total=fat, m=m, r=r, f=3, em_risco=em_risco, faixa="Prata")
    db.add(c)
    return c


# ------------------------------------------------- leitura/escrita da opção

def test_valor_padrao_quando_nunca_foi_definido(db):
    assert svc.obter_numero(db, svc.FATURAMENTO_MINIMO_RISCO) == 0


def test_grava_e_le_de_volta(db):
    svc.definir_numero(db, svc.FATURAMENTO_MINIMO_RISCO, 5000)
    db.commit()
    assert svc.obter_numero(db, svc.FATURAMENTO_MINIMO_RISCO) == 5000


def test_valor_fora_dos_limites_e_recusado_com_mensagem_amigavel(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as erro:
        svc.definir_numero(db, svc.FATURAMENTO_MINIMO_RISCO, -1)
    assert erro.value.status_code == 400
    assert "Informe um valor" in erro.value.detail


def test_valor_corrompido_no_banco_cai_no_padrao(db):
    """Configuração ilegível não pode derrubar o app na mão do vendedor."""
    from app.models import Configuracao
    db.add(Configuracao(chave=svc.FATURAMENTO_MINIMO_RISCO, valor="cinco mil"))
    db.commit()
    assert svc.obter_numero(db, svc.FATURAMENTO_MINIMO_RISCO) == 0


def test_chave_desconhecida_da_404(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as erro:
        svc.obter_numero(db, "opcao_que_nao_existe")
    assert erro.value.status_code == 404


def test_listar_traz_rotulo_e_ajuda_para_a_tela(db):
    opcoes = svc.listar(db)
    assert len(opcoes) == len(svc.OPCOES)
    piso = next(o for o in opcoes if o["chave"] == svc.FATURAMENTO_MINIMO_RISCO)
    assert piso["rotulo"] and piso["ajuda"]
    assert piso["valor"] == 0


# ------------------------------------------------- efeito na carteira

def test_piso_remove_risco_de_cliente_pequeno(db):
    pequeno = _cliente(db, "Pequeno", fat=800, m=4, r=1, em_risco=True)
    grande = _cliente(db, "Grande", fat=40000, m=5, r=1, em_risco=True)
    db.commit()

    resultado = svc.reavaliar_risco(db, 5000)
    db.commit()

    assert resultado == {"marcados": 0, "removidos": 1}
    assert pequeno.em_risco is False
    assert grande.em_risco is True


def test_baixar_o_piso_devolve_o_risco(db):
    pequeno = _cliente(db, "Pequeno", fat=800, m=4, r=1, em_risco=False)
    db.commit()

    resultado = svc.reavaliar_risco(db, 0)
    db.commit()

    assert resultado == {"marcados": 1, "removidos": 0}
    assert pequeno.em_risco is True


def test_piso_nao_marca_quem_o_quintil_nao_aponta(db):
    """O piso só TIRA de risco; quem compra recente (R alto) não vira risco
    por ser grande."""
    fiel = _cliente(db, "Grande e Fiel", fat=90000, m=5, r=5, em_risco=False)
    db.commit()

    svc.reavaliar_risco(db, 0)
    db.commit()

    assert fiel.em_risco is False


def test_cliente_sem_rfm_calculado_nunca_vira_risco(db):
    """Lead cadastrado em campo não tem R/M — não pode ser marcado."""
    lead = Cliente(nome="Lead", origem=OrigemCliente.NOVO, em_risco=True)
    db.add(lead)
    db.commit()

    svc.reavaliar_risco(db, 0)
    db.commit()

    assert lead.em_risco is False


# ------------------------------------------------- efeito na importação

def test_piso_vale_tambem_no_calculo_da_importacao():
    """Sem isso, a próxima importação remarcaria de risco todo mundo que o
    gerente tinha acabado de tirar pela tela."""
    from datetime import date
    registros = [
        {"no_compras": 2, "fat_total": 100, "primeira_compra": date(2026, 1, 1),
         "ultima_compra": date(2026, 8, 1)}
        for _ in range(99)
    ]
    pequeno_parado = {"no_compras": 5, "fat_total": 900, "primeira_compra": date(2021, 1, 1),
                      "ultima_compra": date(2023, 1, 1)}
    registros.append(pequeno_parado)

    rfm.calcular(registros, referencia=date(2026, 8, 31), faturamento_minimo_risco=0)
    assert pequeno_parado["em_risco"] is True, "sem piso, o quintil marca o pequeno"

    rfm.calcular(registros, referencia=date(2026, 8, 31), faturamento_minimo_risco=5000)
    assert pequeno_parado["em_risco"] is False, "com piso, ele sai do alerta"


# ------------------------------------------------- rota HTTP

def test_vendedor_le_mas_nao_altera(cliente_http, token_vendedor):
    assert cliente_http.get("/api/configuracoes", headers=_auth(token_vendedor)).status_code == 200
    resposta = cliente_http.put(
        f"/api/configuracoes/{svc.FATURAMENTO_MINIMO_RISCO}",
        json={"valor": 5000}, headers=_auth(token_vendedor),
    )
    assert resposta.status_code == 403


def test_admin_altera_e_a_resposta_conta_o_efeito(cliente_http, token, db):
    _cliente(db, "Pequeno", fat=800, m=4, r=1, em_risco=True)
    db.commit()

    resposta = cliente_http.put(
        f"/api/configuracoes/{svc.FATURAMENTO_MINIMO_RISCO}",
        json={"valor": 5000}, headers=_auth(token),
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["valor"] == 5000
    assert corpo["efeito"]["removidos"] == 1
