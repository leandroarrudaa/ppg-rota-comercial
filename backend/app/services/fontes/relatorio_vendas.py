"""Leitura do relatório "Pedidos com Produtos (Detalhado)" exportado do ERP.

Este arquivo NÃO é uma tabela — é um relatório de impressão salvo como CSV,
com blocos aninhados e uma quantidade enorme de ponto-e-vírgula de recheio:

    Cliente:;729 - R O L COMERCIO DE REDES LTDA;;;;
    Pedido:;26367;;;Data Cadastro:;01/08/2026;;;...;Vendedor:;;;5 - TABORDA
    Código;;;Descrição;;;...;Vlr Custo;;;Unid;;;Qtde;;;Vlr Venda;;;;Total
    5018;;;GANCHO P/BUCHA C/ABA 08;;;;;;;;;;;;0,43;;;;;;UN;;;200;;;0,77;;;;154,00
    Total Custo:;;;90,00;;;;;;Desconto:;;;;0,00;;;;;Total Liq:;;;;170,00

O cliente aparece como "código - nome", sem CNPJ nenhum — daí a necessidade do
de-para (ver fontes/banco_mestre.ler_depara_codigo_cnpj). O arquivo vem em
latin-1, não em UTF-8.

O parser é deliberadamente tolerante: linha que não reconhece, ele ignora e
segue. Um relatório com uma seção a mais no cabeçalho não pode derrubar a
importação do mês inteiro.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

# "729 - R O L COMERCIO DE REDES LTDA"
_CLIENTE = re.compile(r"^(\d+)\s*-\s*(.+)$")
_DATA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
# valor no padrão brasileiro: 1.234,56 (com ou sem sinal)
_VALOR = re.compile(r"^-?[\d.]*\d,\d{2}$")
# "5 - TABORDA" — o vendedor vem no mesmo formato do cliente
_VENDEDOR = re.compile(r"^\d+\s*-\s*\D")

CODIFICACAO = "latin-1"


class RelatorioInvalido(Exception):
    """Arquivo que não é o relatório esperado, ou está vazio."""


@dataclass
class Pedido:
    numero: str
    codigo_cliente: str
    nome_cliente: str
    data: date | None
    vendedor: str | None = None
    total: float = 0.0
    itens: list[dict] = field(default_factory=list)


def _valor(texto: str) -> float:
    """1.234,56 -> 1234.56"""
    try:
        return float(texto.strip().replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _data(texto: str) -> date | None:
    achado = _DATA.match(texto.strip())
    if not achado:
        return None
    dia, mes, ano = achado.groups()
    try:
        return date(int(ano), int(mes), int(dia))
    except ValueError:
        return None


def ler(conteudo: bytes | str) -> list[Pedido]:
    """Converte o relatório em uma lista de pedidos com seus itens.

    Aceita bytes (o que chega do upload) ou texto já decodificado.
    """
    if isinstance(conteudo, bytes):
        # errors="replace" de propósito: um acento estranho numa descrição de
        # produto não pode impedir a importação do faturamento do mês.
        texto = conteudo.decode(CODIFICACAO, errors="replace")
    else:
        texto = conteudo

    pedidos: list[Pedido] = []
    codigo_cliente = nome_cliente = ""
    atual: Pedido | None = None

    for linha in texto.splitlines():
        colunas = linha.split(";")
        primeira = colunas[0].strip()

        if primeira.startswith("Cliente:"):
            bruto = colunas[1].strip() if len(colunas) > 1 else ""
            achado = _CLIENTE.match(bruto)
            codigo_cliente, nome_cliente = achado.groups() if achado else ("", bruto)
            nome_cliente = nome_cliente.strip()
            atual = None

        elif primeira.startswith("Pedido:"):
            numero = colunas[1].strip() if len(colunas) > 1 else ""
            if not numero:
                atual = None
                continue
            data_pedido = next(
                (_data(c) for c in colunas if _DATA.match(c.strip())), None
            )
            # o vendedor vem depois do rótulo; procurar por posição seria
            # frágil (a quantidade de campos de recheio varia), então
            # localizamos o rótulo e pegamos o primeiro "n - NOME" seguinte
            vendedor = None
            for i, coluna in enumerate(colunas):
                if coluna.strip().startswith("Vendedor:"):
                    vendedor = next(
                        (c.strip() for c in colunas[i + 1:] if _VENDEDOR.match(c.strip())), None
                    )
                    break
            atual = Pedido(
                numero=numero,
                codigo_cliente=codigo_cliente,
                nome_cliente=nome_cliente,
                data=data_pedido,
                vendedor=vendedor,
            )
            pedidos.append(atual)

        elif primeira.startswith("Total Liq:") or "Total Liq:" in linha:
            # o total do pedido fecha o bloco; é o último valor da linha
            if atual is not None:
                valores = [c for c in colunas if _VALOR.match(c.strip())]
                if valores:
                    atual.total = _valor(valores[-1])
            atual = None

        elif primeira.isdigit() and atual is not None:
            # linha de item: código na primeira coluna, e os números que
            # interessam são os três últimos valores (venda unitária e total)
            valores = [c.strip() for c in colunas if _VALOR.match(c.strip())]
            quantidades = [
                c.strip() for c in colunas[1:]
                if c.strip().replace(".", "").isdigit() and c.strip() != primeira
            ]
            descricao = next((c.strip() for c in colunas[1:] if c.strip() and not c.strip().replace(".", "").replace(",", "").isdigit()), "")
            atual.itens.append({
                "codigo": primeira,
                "descricao": descricao,
                "quantidade": float(quantidades[0].replace(".", "")) if quantidades else 0.0,
                "total": _valor(valores[-1]) if valores else 0.0,
            })

    if not pedidos:
        raise RelatorioInvalido(
            "Não encontrei nenhum pedido nesse arquivo. Confira se é o relatório "
            "'Pedidos com Produtos (Detalhado)' exportado do ERP em CSV."
        )
    return pedidos


def periodo(pedidos: list[Pedido]) -> tuple[date | None, date | None]:
    """Primeira e última data de pedido — mostrado na prévia da importação."""
    datas = [p.data for p in pedidos if p.data]
    return (min(datas), max(datas)) if datas else (None, None)
