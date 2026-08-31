"""Cálculo de RFM: quintis, métricas derivadas, faixa e flag de risco."""
from datetime import date

import pytest

from app.services import rfm


def _cliente(compras, faturamento, primeira, ultima):
    return {
        "no_compras": compras,
        "fat_total": faturamento,
        "primeira_compra": date.fromisoformat(primeira),
        "ultima_compra": date.fromisoformat(ultima),
    }


def _carteira(n=100):
    """Carteira sintética onde quem compra mais também fatura mais e comprou
    mais recentemente — assim as três notas crescem juntas e ficam previsíveis."""
    return [
        _cliente(
            compras=i + 1,
            faturamento=(i + 1) * 1000,
            primeira="2021-01-01",
            ultima=f"2026-01-{(i % 28) + 1:02d}",
        )
        for i in range(n)
    ]


HOJE = date(2026, 8, 31)


def test_quintis_distribuem_em_cinco_faixas_iguais():
    registros = rfm.calcular(_carteira(100), referencia=HOJE)
    contagem = {}
    for reg in registros:
        contagem[reg["f"]] = contagem.get(reg["f"], 0) + 1
    assert contagem == {1: 20, 2: 20, 3: 20, 4: 20, 5: 20}


def test_nota_de_frequencia_acompanha_o_numero_de_compras():
    registros = rfm.calcular(_carteira(100), referencia=HOJE)
    assert registros[0]["f"] == 1    # 1 compra — pior quintil
    assert registros[-1]["f"] == 5   # 100 compras — melhor quintil


def test_recencia_e_invertida_quem_comprou_ontem_tem_nota_maior():
    registros = [
        _cliente(10, 10000, "2021-01-01", "2026-08-30"),  # comprou ontem
        _cliente(10, 10000, "2021-01-01", "2020-01-01"),  # sumiu faz anos
    ]
    rfm.calcular(registros, referencia=HOJE)
    assert registros[0]["recencia_dias"] == 1
    assert registros[0]["r"] > registros[1]["r"]


def test_ticket_medio_e_cadencia():
    registros = [_cliente(compras=10, faturamento=5000, primeira="2026-01-01", ultima="2026-03-31")]
    rfm.calcular(registros, referencia=HOJE)
    assert registros[0]["ticket_medio"] == 500.0
    # 89 dias divididos por 9 intervalos entre as 10 compras
    assert registros[0]["cadencia_dias"] == 10


def test_uma_compra_so_nao_tem_cadencia():
    registros = [_cliente(compras=1, faturamento=800, primeira="2026-05-05", ultima="2026-05-05")]
    rfm.calcular(registros, referencia=HOJE)
    assert registros[0]["cadencia_dias"] is None
    assert registros[0]["ticket_medio"] == 800.0


def test_ouro_exige_valor_recencia_e_frequencia_altos():
    registros = _carteira(100)
    rfm.calcular(registros, referencia=HOJE)
    for reg in registros:
        if reg["faixa"] == "Ouro":
            assert reg["m"] >= 4 and reg["r"] >= 4 and reg["f"] >= 4
        if reg["faixa"] == "Bronze":
            assert reg["m"] <= 2


def test_conta_grande_que_esfriou_fica_em_risco_e_nao_vira_ouro():
    # 99 clientes pequenos e recentes + 1 conta grande que parou há 2 anos
    registros = [
        _cliente(compras=2, faturamento=100, primeira="2026-01-01", ultima="2026-08-01")
        for _ in range(99)
    ]
    grande = _cliente(compras=500, faturamento=900_000, primeira="2021-01-01", ultima="2024-01-01")
    registros.append(grande)
    rfm.calcular(registros, referencia=HOJE)

    assert grande["m"] == 5, "maior faturamento da carteira precisa estar no topo de valor"
    assert grande["r"] <= 2, "quem parou há 2 anos tem a pior recência"
    assert grande["em_risco"] is True
    assert grande["faixa"] != "Ouro"


def test_recencia_usa_a_data_de_hoje_e_nao_uma_constante():
    """Regressão: o script original tinha a data de referência fixa no código,
    o que congelava a recência de toda a carteira."""
    registros = [_cliente(5, 5000, "2021-01-01", "2026-08-01")]
    rfm.calcular(registros, referencia=date(2026, 8, 31))
    assert registros[0]["recencia_dias"] == 30

    registros = [_cliente(5, 5000, "2021-01-01", "2026-08-01")]
    rfm.calcular(registros, referencia=date(2026, 9, 30))
    assert registros[0]["recencia_dias"] == 60


def test_carteira_vazia_nao_quebra():
    assert rfm.calcular([], referencia=HOJE) == []


@pytest.mark.parametrize("tamanho", [1, 2, 3, 7])
def test_carteira_menor_que_cinco_clientes_ainda_recebe_notas_validas(tamanho):
    """Não pode estourar quando há menos clientes que quintis — acontece em
    teste e num banco recém-criado."""
    registros = rfm.calcular(_carteira(tamanho), referencia=HOJE)
    for reg in registros:
        assert 1 <= reg["r"] <= 5
        assert 1 <= reg["f"] <= 5
        assert 1 <= reg["m"] <= 5
        assert reg["faixa"] in {"Ouro", "Prata", "Bronze"}
