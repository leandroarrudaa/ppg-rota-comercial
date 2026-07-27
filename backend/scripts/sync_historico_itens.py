#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sincroniza o histórico de compra POR PRODUTO a partir do banco_mestre.db.

O banco mestre (gerado pelo app gerador_banco_mestre a partir dos XMLs de NFe)
é fonte externa somente-leitura. Este script agrega itens de venda por
(cnpj, produto) e faz upsert na tabela historico_itens_cliente do app.

Exclusões obrigatórias:
  - notas sem CNPJ de cliente (venda de balcão — ~211 mil linhas de item);
  - o CNPJ da própria empresa (auto-emissão).

Rodar manualmente sempre que o banco mestre for regenerado.
Uso:  python backend/scripts/sync_historico_itens.py [caminho_do_banco_mestre]
"""
import os
import sqlite3
import sys
from datetime import date, datetime

# permite importar app.* rodando o script de qualquer diretório
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.database import Base, SessaoLocal, engine  # noqa: E402
from app.models import HistoricoItemCliente  # noqa: E402
from app.services.cnpj import normalizar_cnpj  # noqa: E402

# Caminho padrão do banco mestre (pasta output do repositório maior).
BANCO_MESTRE_PADRAO = os.path.join(
    os.path.dirname(os.path.dirname(BACKEND_DIR)), "output", "banco_mestre.db"
)
# CNPJ da própria empresa — aparece como "cliente" em auto-emissões; excluir.
CNPJ_EMPRESA = "05250137000118"


def _data(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def extrair(caminho_banco: str) -> list[dict]:
    """Agrega os itens de venda por (cnpj, produto) direto no SQLite mestre."""
    con = sqlite3.connect(f"file:{caminho_banco}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT n.cpf_cnpj_cliente,
                   COALESCE(NULLIF(i.codigo_limpo, ''), i.codigo_produto) AS codigo,
                   MAX(i.descricao_produto)  AS descricao,
                   SUM(i.quantidade)          AS quantidade_total,
                   SUM(i.valor_total_item)    AS valor_total,
                   COUNT(DISTINCT n.chave_nota) AS numero_compras,
                   MAX(n.data_emissao)        AS ultima_compra
            FROM notas n
            JOIN itens i ON i.chave_nota = n.chave_nota
            WHERE n.tipo_operacao = 'saida'
              AND n.cpf_cnpj_cliente IS NOT NULL
              AND n.cpf_cnpj_cliente != ''
              AND n.cpf_cnpj_cliente != 'NAO_IDENTIFICADO'
              AND n.cpf_cnpj_cliente != ?
              AND LENGTH(n.cpf_cnpj_cliente) = 14
            GROUP BY n.cpf_cnpj_cliente, codigo
            """,
            (CNPJ_EMPRESA,),
        )
        linhas = []
        for cnpj, codigo, descricao, qtd, valor, compras, ultima in cur.fetchall():
            cnpj_norm = normalizar_cnpj(cnpj)
            if not cnpj_norm or cnpj_norm == CNPJ_EMPRESA:
                continue
            linhas.append({
                "cnpj_normalizado": cnpj_norm,
                "codigo_produto": str(codigo or ""),
                "descricao_produto": descricao or "",
                "quantidade_total": float(qtd or 0),
                "valor_total": round(float(valor or 0), 2),
                "numero_compras": int(compras or 0),
                "ultima_compra": _data(ultima),
            })
        return linhas
    finally:
        con.close()


def main():
    caminho = sys.argv[1] if len(sys.argv) > 1 else BANCO_MESTRE_PADRAO
    if not os.path.exists(caminho):
        print(f"ERRO: banco mestre não encontrado em {caminho}")
        sys.exit(1)

    print(f"Lendo banco mestre: {caminho}")
    linhas = extrair(caminho)
    cnpjs = {l["cnpj_normalizado"] for l in linhas}
    print(f"Agregados: {len(linhas)} produtos x cliente | CNPJs distintos: {len(cnpjs)}")

    Base.metadata.create_all(bind=engine)
    db = SessaoLocal()
    try:
        # upsert: índice existente por (cnpj, codigo)
        existentes = {
            (h.cnpj_normalizado, h.codigo_produto): h
            for h in db.query(HistoricoItemCliente).all()
        }
        criados = atualizados = 0
        for reg in linhas:
            chave = (reg["cnpj_normalizado"], reg["codigo_produto"])
            existente = existentes.get(chave)
            if existente is None:
                db.add(HistoricoItemCliente(**reg))
                criados += 1
            else:
                for campo, valor in reg.items():
                    setattr(existente, campo, valor)
                atualizados += 1
        db.commit()
        print(f"Criados: {criados} | Atualizados: {atualizados}")
        print(f"Concluído em {datetime.now():%Y-%m-%d %H:%M}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
