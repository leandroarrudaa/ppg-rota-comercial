"""Cálculo de RFM (Recência / Frequência / Valor) sobre a carteira inteira.

Extraído do scripts/01_processar_base.py para virar código de servidor: o mesmo
cálculo passa a servir as três origens de dados (recarga pelo banco mestre,
relatório diário de vendas do ERP e a tela de importação do gerente), em vez de
existir só dentro de um script de linha de comando com pandas.

Duas diferenças propositais em relação ao script original:

1. A data de referência é a de hoje em Brasília, não uma constante escrita no
   código (o script tinha ``HOJE = pd.Timestamp("2026-06-25")`` fixo — com
   atualização diária isso congelaria a recência de todo mundo).
2. Sem pandas. Os quintis são calculados por posição no ranking, que é o que o
   ``pd.qcut`` sobre ``rank(method="first")`` fazia — o resultado é o mesmo e o
   servidor não precisa carregar pandas para responder uma importação.
"""
from __future__ import annotations

from datetime import date

from .tempo import hoje_brasil

# Notas de 1 a 5 por quintil. Recência é invertida: menos dias sem comprar é
# uma nota MAIOR (comprou recentemente = melhor).
NOTAS = 5


def _quintis(valores: list[float | None], invertido: bool = False) -> list[int]:
    """Nota de 1 a 5 por posição no ranking, em faixas de tamanho igual.

    Empates são desempatados pela ordem de entrada (equivalente ao
    ``rank(method="first")`` do pandas). Quem não tem valor fica com a nota
    mínima — é o caso de cliente sem data de compra utilizável.
    """
    total = len(valores)
    if total == 0:
        return []

    # ordena os índices pelo valor; None vai para o começo (pior situação)
    ordem = sorted(range(total), key=lambda i: (valores[i] is None, valores[i] or 0))

    notas = [1] * total
    for posicao, indice in enumerate(ordem):
        faixa = min(posicao * NOTAS // total, NOTAS - 1)  # 0..4
        notas[indice] = (NOTAS - faixa) if invertido else (faixa + 1)
    return notas


def _dias(inicio: date | None, fim: date | None) -> int | None:
    if inicio is None or fim is None:
        return None
    return (fim - inicio).days


def calcular(registros: list[dict], referencia: date | None = None) -> list[dict]:
    """Enriquece cada registro com as métricas derivadas e as notas de RFM.

    Espera em cada registro: ``no_compras``, ``fat_total``, ``primeira_compra``
    e ``ultima_compra``. Devolve os mesmos dicionários (alterados no lugar) com
    ``ticket_medio``, ``recencia_dias``, ``cadencia_dias``, ``r``, ``f``, ``m``,
    ``rfm_score``, ``faixa`` e ``em_risco``.

    As notas são relativas à carteira RECEBIDA — quintis só fazem sentido sobre
    o conjunto inteiro, nunca sobre um cliente isolado. Por isso a importação
    diária precisa recalcular tudo, não só as linhas que mudaram.
    """
    if not registros:
        return registros
    hoje = referencia or hoje_brasil()

    for reg in registros:
        compras = reg.get("no_compras") or 0
        faturamento = reg.get("fat_total") or 0.0
        reg["ticket_medio"] = round(faturamento / compras, 2) if compras else None
        reg["recencia_dias"] = _dias(reg.get("ultima_compra"), hoje)

        # Cadência = intervalo médio entre uma compra e a seguinte. Com uma
        # compra só não existe intervalo nenhum, então fica sem cadência (o
        # motor de recomendação já trata a ausência).
        intervalo = _dias(reg.get("primeira_compra"), reg.get("ultima_compra"))
        if compras > 1 and intervalo is not None:
            reg["cadencia_dias"] = round(intervalo / (compras - 1))
        else:
            reg["cadencia_dias"] = None

    notas_r = _quintis([r["recencia_dias"] for r in registros], invertido=True)
    notas_f = _quintis([r.get("no_compras") for r in registros])
    notas_m = _quintis([r.get("fat_total") for r in registros])

    for reg, r, f, m in zip(registros, notas_r, notas_f, notas_m):
        reg["r"], reg["f"], reg["m"] = r, f, m
        reg["rfm_score"] = r + f + m

        # Faixa = valor + lealdade. Ouro é conta grande que compra recente E
        # com frequência; Bronze é baixo faturamento; Prata é o meio — o que
        # inclui, de propósito, a conta grande que esfriou.
        if m >= 4 and r >= 4 and f >= 4:
            reg["faixa"] = "Ouro"
        elif m <= 2:
            reg["faixa"] = "Bronze"
        else:
            reg["faixa"] = "Prata"

        # Em risco = conta GRANDE que esfriou. É o alerta máximo do app e o
        # que manda o vendedor fazer visita de reativação.
        reg["em_risco"] = m >= 4 and r <= 2

    return registros
