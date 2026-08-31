"""Orquestração das duas origens de atualização da carteira.

O gerente sobe um de dois arquivos e o resto acontece aqui:

- **pacote do banco mestre** (mensal): fonte de verdade. Sobrepõe os números de
  venda de quem ele conhece, atualiza o histórico por produto e renova o
  de-para de código do ERP.
- **relatório de vendas do ERP** (diário): incremental. Soma os pedidos novos
  ao acumulado e recalcula o RFM.

Toda operação tem prévia: o serviço roda inteiro, devolve o que MUDARIA e quem
chama decide se confirma. É por isso que nada aqui dá commit.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ..models import Cliente, HistoricoItemCliente, ImportacaoCarteira, MapaCodigoErp, Usuario
from . import configuracoes as config_svc
from . import importacao, rfm
from .fontes import banco_mestre
from .cnpj import normalizar_cnpj

TIPO_PACOTE = "banco-mestre"
TIPO_RELATORIO = "relatorio-vendas"


def _piso_risco(db: Session) -> float:
    return config_svc.obter_numero(db, config_svc.FATURAMENTO_MINIMO_RISCO)


def aplicar_pacote(db: Session, dados: dict) -> dict:
    """Aplica o pacote do banco mestre: carteira, histórico e de-para.

    O de-para é atualizado ANTES de tudo, porque é ele que permite o relatório
    diário funcionar no dia seguinte — e porque clientes de nome genérico que
    já são da carteira precisam dele para não serem descartados.
    """
    conhecidos = {
        chave
        for chave in (normalizar_cnpj(c) for (c,) in db.query(Cliente.cnpj).filter(Cliente.cnpj.isnot(None)))
        if chave
    }

    depara_novos = depara_atualizados = 0
    existentes_depara = {m.codigo: m for m in db.query(MapaCodigoErp).all()}
    for codigo, cnpj in (dados.get("depara") or {}).items():
        atual = existentes_depara.get(codigo)
        if atual is None:
            db.add(MapaCodigoErp(codigo=codigo, cnpj=cnpj))
            depara_novos += 1
        elif atual.cnpj != cnpj:
            atual.cnpj = cnpj
            depara_atualizados += 1

    # O pacote vem com TUDO, inclusive venda de balcão sem nome na nota. Aqui
    # é o único lugar que sabe quem já é cliente, então é aqui que se filtra:
    # genérico só entra se já for da carteira. A regra de "nome genérico" é a
    # mesma do leitor do banco mestre, de propósito — duas versões dela
    # divergiriam, e esse foi exatamente o erro de uma tentativa anterior.
    registros = [
        reg for reg in dados["carteira"]
        if reg.get("cnpj")
        and (not banco_mestre.e_nome_generico(reg.get("nome")) or reg["cnpj"] in conhecidos)
    ]
    rfm.calcular(registros, faturamento_minimo_risco=_piso_risco(db))
    relatorio = importacao.aplicar_vendas(db, registros)

    # primeira_compra não faz parte de CAMPOS_VENDAS (a atualização diária não
    # sabe a data real da primeira compra), mas o pacote sabe — e a cadência
    # depende dela.
    por_cnpj = {reg["cnpj"]: reg for reg in registros}
    for cliente in db.query(Cliente).filter(Cliente.cnpj.isnot(None)).all():
        reg = por_cnpj.get(normalizar_cnpj(cliente.cnpj))
        if reg and reg.get("primeira_compra"):
            cliente.primeira_compra = reg["primeira_compra"]

    historico = _aplicar_historico(db, dados.get("historico") or [])

    resumo = relatorio.resumo()
    resumo.update({
        "deparaNovos": depara_novos,
        "deparaAtualizados": depara_atualizados,
        "historicoLinhas": historico["linhas"],
        "historicoCriados": historico["criados"],
        "historicoAtualizados": historico["atualizados"],
        "geradoEm": dados.get("gerado_em"),
        "saiuDeRiscoNomes": relatorio.saiu_de_risco[:20],
        "mudouFaixaExemplos": [
            {"nome": n, "de": de, "para": para} for n, de, para in relatorio.mudou_faixa[:20]
        ],
        "nomesForaDaCarteira": relatorio.sem_cliente_na_carteira[:20],
    })
    return resumo


def _aplicar_historico(db: Session, registros: list[dict]) -> dict:
    existentes = {
        (h.cnpj_normalizado, h.codigo_produto): h
        for h in db.query(HistoricoItemCliente).all()
    }
    criados = atualizados = 0
    for reg in registros:
        chave = (reg["cnpj_normalizado"], reg["codigo_produto"])
        atual = existentes.get(chave)
        if atual is None:
            db.add(HistoricoItemCliente(**reg))
            criados += 1
        else:
            for campo, valor in reg.items():
                setattr(atual, campo, valor)
            atualizados += 1
    return {"linhas": len(registros), "criados": criados, "atualizados": atualizados}


def aplicar_relatorio(db: Session, pedidos: list) -> dict:
    """Aplica o relatório diário de vendas do ERP."""
    relatorio = importacao.aplicar_relatorio_vendas(
        db, pedidos, faturamento_minimo_risco=_piso_risco(db)
    )
    resumo = relatorio.resumo()
    resumo["saiuDeRiscoNomes"] = relatorio.saiu_de_risco[:20]
    resumo["mudouFaixaExemplos"] = [
        {"nome": n, "de": de, "para": para} for n, de, para in relatorio.mudou_faixa[:20]
    ]
    return resumo


def registrar(db: Session, tipo: str, arquivo: str | None, usuario: Usuario, resumo: dict) -> None:
    """Deixa rastro da importação — é como se responde 'o Raphael subiu hoje?'."""
    db.add(ImportacaoCarteira(
        tipo=tipo, arquivo=arquivo, usuario_id=usuario.id,
        resumo=json.dumps(resumo, ensure_ascii=False),
    ))


def historico_importacoes(db: Session, limite: int = 20) -> list[dict]:
    registros = (
        db.query(ImportacaoCarteira)
        .order_by(ImportacaoCarteira.criado_em.desc())
        .limit(limite)
        .all()
    )
    saida = []
    for r in registros:
        try:
            resumo = json.loads(r.resumo) if r.resumo else {}
        except ValueError:
            resumo = {}
        saida.append({
            "id": r.id,
            "tipo": r.tipo,
            "arquivo": r.arquivo,
            "usuario": r.usuario.nome if r.usuario else None,
            "criadoEm": r.criado_em,
            "resumo": resumo,
        })
    return saida
