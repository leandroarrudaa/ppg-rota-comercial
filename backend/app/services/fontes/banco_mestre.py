"""Leitura do banco_mestre.db — a fonte de verdade das vendas.

O banco mestre é gerado fora deste projeto, a partir dos XMLs de NFe, e é
somente-leitura aqui. É a origem MAIS COMPLETA que existe: tem o CNPJ real do
cliente (o relatório do ERP não tem) e o histórico inteiro desde 2021. Por isso
ele sobrepõe qualquer dado vindo do relatório diário de vendas.

Duas coisas são extraídas daqui:

- a carteira agregada por CNPJ (o insumo do cálculo de RFM);
- o de-para ``código do ERP -> CNPJ``, que é o que torna o relatório diário
  aproveitável, já que lá o cliente é identificado só por código interno.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date

from ..cnpj import normalizar_cnpj

# CNPJ da própria PPG. Aparece como "cliente" em notas de auto-emissão e não
# pode entrar na carteira.
CNPJ_EMPRESA = "05250137000118"

# Documento de 14 dígitos é CNPJ (empresa). 11 é CPF — pessoa física de balcão,
# que nunca fez parte da carteira de visitas e não deve entrar nela.
TAMANHO_CNPJ = 14

# Venda avulsa em que o nome do cliente não foi preenchido na nota. O CNPJ é
# real, mas a empresa nunca foi cliente de carteira: são compras de balcão de
# 2021-2023, R$ 123 em média. Elas PRECISAM ficar de fora porque o RFM é
# calculado por quintis — 217 registros minúsculos entrando no cálculo baixam
# o corte de faturamento e promovem de faixa quem não mudou de comportamento.
# Mesma regra que o scripts/01_processar_base.py já aplicava sobre a planilha.
NOMES_GENERICOS = ("CONSUMIDOR",)


def e_nome_generico(nome: str | None) -> bool:
    """Nome de cliente que na verdade é venda de balcão sem identificação."""
    limpo = (nome or "").strip().upper()
    return not limpo or any(termo in limpo for termo in NOMES_GENERICOS)


class BancoMestreInvalido(Exception):
    """Arquivo ausente, ilegível ou sem as tabelas esperadas."""


def _conectar(caminho: str) -> sqlite3.Connection:
    if not os.path.exists(caminho):
        raise BancoMestreInvalido(
            "Arquivo do banco mestre não encontrado. Verifique o caminho e tente de novo."
        )
    try:
        con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
        tabelas = {t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error as erro:
        raise BancoMestreInvalido(
            "Não foi possível ler o arquivo do banco mestre — ele parece corrompido."
        ) from erro
    faltando = {"notas", "cadastro_clientes"} - tabelas
    if faltando:
        con.close()
        raise BancoMestreInvalido(
            "Esse arquivo não parece ser um banco mestre válido "
            f"(faltam as tabelas: {', '.join(sorted(faltando))})."
        )
    return con


def _data(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return None


def ler_carteira(
    caminho: str,
    cnpjs_conhecidos: set[str] | None = None,
    incluir_genericos: bool = False,
) -> list[dict]:
    """Vendas agregadas por CNPJ: nº de compras, faturamento e datas extremas.

    Uma "compra" é uma nota fiscal distinta (``chave_nota``), não uma linha de
    item — é a mesma definição que a carteira sempre usou. Só notas de saída
    entram, e só clientes com CNPJ de 14 dígitos.

    ``cnpjs_conhecidos`` são os CNPJs que já são clientes da carteira. Eles
    entram SEMPRE, mesmo que as notas os tenham registrado como "CONSUMIDOR" —
    sem isso o filtro de nome genérico derrubava 58 clientes de verdade, que
    têm cadastro no app mas cujas notas saíram sem o nome preenchido.

    ``incluir_genericos`` desliga o filtro por completo. É o que o gerador de
    pacote usa: ele roda na máquina do escritório e NÃO tem como saber quem já
    é cliente, então manda tudo e deixa a decisão para o servidor, que sabe.
    Sem isso, aqueles 58 clientes ficavam de fora da atualização mensal.
    """
    conhecidos = cnpjs_conhecidos or set()
    con = _conectar(caminho)
    try:
        linhas = con.execute(
            """
            SELECT cpf_cnpj_cliente,
                   MAX(nome_cliente)            AS nome,
                   COUNT(DISTINCT chave_nota)   AS no_compras,
                   SUM(valor_total)             AS fat_total,
                   MIN(data_emissao)            AS primeira_compra,
                   MAX(data_emissao)            AS ultima_compra
              FROM notas
             WHERE tipo_operacao = 'saida'
               AND cpf_cnpj_cliente IS NOT NULL
               AND LENGTH(cpf_cnpj_cliente) = ?
               AND cpf_cnpj_cliente != ?
             GROUP BY cpf_cnpj_cliente
            """,
            (TAMANHO_CNPJ, CNPJ_EMPRESA),
        ).fetchall()
    finally:
        con.close()

    registros = []
    for cnpj, nome, compras, faturamento, primeira, ultima in linhas:
        chave = normalizar_cnpj(cnpj)
        if not chave or chave == CNPJ_EMPRESA:
            continue
        if not incluir_genericos and e_nome_generico(nome) and chave not in conhecidos:
            continue
        registros.append({
            "cnpj": chave,
            "nome": (nome or "").strip(),
            "no_compras": int(compras or 0),
            "fat_total": round(float(faturamento or 0), 2),
            "primeira_compra": _data(primeira),
            "ultima_compra": _data(ultima),
        })
    return registros


def ler_depara_codigo_cnpj(caminho: str) -> dict[str, str]:
    """Mapa ``código do cliente no ERP -> CNPJ`` (só empresas).

    É o que permite aproveitar o relatório diário de vendas, onde o cliente
    aparece como "729 - RAZÃO SOCIAL" e não há CNPJ em lugar nenhum. Códigos de
    pessoa física (CPF) e de balcão ficam de fora de propósito: eles não são
    clientes de carteira.
    """
    con = _conectar(caminho)
    try:
        linhas = con.execute("SELECT codigo, cpf_cnpj_digits FROM cadastro_clientes").fetchall()
    finally:
        con.close()

    mapa = {}
    for codigo, documento in linhas:
        chave = normalizar_cnpj(documento)
        codigo = (str(codigo or "")).strip()
        if codigo and len(chave) == TAMANHO_CNPJ and chave != CNPJ_EMPRESA:
            mapa[codigo] = chave
    return mapa


def ler_historico_itens(caminho: str) -> list[dict]:
    """Histórico de compra por produto, agregado por (CNPJ, produto).

    Mesma consulta que o scripts/sync_historico_itens.py já fazia — trazida
    para cá para que a importação pela tela use exatamente a mesma regra do
    script de linha de comando, sem duas versões para manter.
    """
    con = _conectar(caminho)
    try:
        linhas = con.execute(
            """
            SELECT n.cpf_cnpj_cliente,
                   COALESCE(NULLIF(i.codigo_limpo, ''), i.codigo_produto) AS codigo,
                   MAX(i.descricao_produto)     AS descricao,
                   SUM(i.quantidade)            AS quantidade_total,
                   SUM(i.valor_total_item)      AS valor_total,
                   COUNT(DISTINCT n.chave_nota) AS numero_compras,
                   MAX(n.data_emissao)          AS ultima_compra
              FROM notas n
              JOIN itens i ON i.chave_nota = n.chave_nota
             WHERE n.tipo_operacao = 'saida'
               AND n.cpf_cnpj_cliente IS NOT NULL
               AND LENGTH(n.cpf_cnpj_cliente) = ?
               AND n.cpf_cnpj_cliente != ?
             GROUP BY n.cpf_cnpj_cliente, codigo
            """,
            (TAMANHO_CNPJ, CNPJ_EMPRESA),
        ).fetchall()
    finally:
        con.close()

    registros = []
    for cnpj, codigo, descricao, quantidade, valor, compras, ultima in linhas:
        chave = normalizar_cnpj(cnpj)
        if not chave or chave == CNPJ_EMPRESA:
            continue
        registros.append({
            "cnpj_normalizado": chave,
            "codigo_produto": str(codigo or ""),
            "descricao_produto": descricao or "",
            "quantidade_total": float(quantidade or 0),
            "valor_total": round(float(valor or 0), 2),
            "numero_compras": int(compras or 0),
            "ultima_compra": _data(ultima),
        })
    return registros
