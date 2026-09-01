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

# Quantas linhas por vez nas gravações em massa. O serviço tem 512 MB de RAM e
# a primeira importação do banco mestre insere ~36 mil linhas de histórico —
# mandar tudo num comando só já derrubou o processo em produção uma vez. Em
# blocos, o pico de memória fica limitado e a transação continua sendo uma só
# (nada é confirmado no meio do caminho).
TAMANHO_BLOCO = 2_000


def _em_blocos(registros: list[dict]):
    for inicio in range(0, len(registros), TAMANHO_BLOCO):
        yield registros[inicio:inicio + TAMANHO_BLOCO]


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

    # Mesma lógica do histórico: só o que mudou, e sem carregar objetos.
    existentes_depara = dict(db.query(MapaCodigoErp.codigo, MapaCodigoErp.cnpj).all())
    depara_criar, depara_alterar = [], []
    for codigo, cnpj in (dados.get("depara") or {}).items():
        atual = existentes_depara.get(codigo)
        if atual is None:
            depara_criar.append({"codigo": codigo, "cnpj": cnpj})
        elif atual != cnpj:
            depara_alterar.append({"codigo": codigo, "cnpj": cnpj})
    for bloco in _em_blocos(depara_criar):
        db.bulk_insert_mappings(MapaCodigoErp, bloco)
    for bloco in _em_blocos(depara_alterar):
        db.bulk_update_mappings(MapaCodigoErp, bloco)
    depara_novos, depara_atualizados = len(depara_criar), len(depara_alterar)

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

    # primeira_compra vem junto no mesmo lote de aplicar_vendas — antes havia
    # aqui uma segunda varredura da carteira inteira só para ela, que carregava
    # todos os clientes de novo e gerava mais um UPDATE por linha.

    historico = _aplicar_historico(db, dados.get("historico") or [])

    resumo = relatorio.resumo()
    resumo.update({
        "deparaNovos": depara_novos,
        "deparaAtualizados": depara_atualizados,
        "historicoLinhas": historico["linhas"],
        "historicoCriados": historico["criados"],
        "historicoAtualizados": historico["atualizados"],
        "historicoInalterados": historico.get("inalterados", 0),
        "geradoEm": dados.get("gerado_em"),
        "saiuDeRiscoNomes": relatorio.saiu_de_risco[:20],
        "mudouFaixaExemplos": [
            {"nome": n, "de": de, "para": para} for n, de, para in relatorio.mudou_faixa[:20]
        ],
        "nomesForaDaCarteira": relatorio.sem_cliente_na_carteira[:20],
    })
    return resumo


# Campos comparados para decidir se a linha mudou de verdade.
_CAMPOS_HISTORICO = (
    "descricao_produto", "quantidade_total", "valor_total",
    "numero_compras", "ultima_compra",
)


def _aplicar_historico(db: Session, registros: list[dict]) -> dict:
    """Grava só o que MUDOU, em lote.

    São ~36 mil linhas de histórico, e de um mês para o outro a esmagadora
    maioria é idêntica — só muda quem comprou no período. A primeira versão
    reescrevia todas: com o banco a ~330ms de distância, o "confirmar" da tela
    não terminava (a prévia enganava porque faz rollback e, sem autoflush,
    nunca chega a enviar as escritas).

    Também não carrega objetos do ORM: lê só as colunas necessárias, porque
    36 mil objetos completos não cabem confortavelmente na memória do plano
    gratuito.
    """
    existentes = {
        (linha[0], linha[1]): linha[2:]
        for linha in db.query(
            HistoricoItemCliente.cnpj_normalizado,
            HistoricoItemCliente.codigo_produto,
            HistoricoItemCliente.id,
            *(getattr(HistoricoItemCliente, c) for c in _CAMPOS_HISTORICO),
        ).all()
    }

    novos, alterados = [], []
    for reg in registros:
        chave = (reg["cnpj_normalizado"], reg["codigo_produto"])
        atual = existentes.get(chave)
        if atual is None:
            novos.append(reg)
            continue
        id_atual, valores_atuais = atual[0], atual[1:]
        if tuple(reg[c] for c in _CAMPOS_HISTORICO) != valores_atuais:
            alterados.append({"id": id_atual, **reg})

    for bloco in _em_blocos(novos):
        db.bulk_insert_mappings(HistoricoItemCliente, bloco)
    for bloco in _em_blocos(alterados):
        db.bulk_update_mappings(HistoricoItemCliente, bloco)

    return {
        "linhas": len(registros),
        "criados": len(novos),
        "atualizados": len(alterados),
        "inalterados": len(registros) - len(novos) - len(alterados),
    }


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
