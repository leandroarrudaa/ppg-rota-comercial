"""Prospecção: importa a lista de empresas que ainda não são clientes e a consulta.

A importação segue o padrão do resto do app: roda tudo e devolve o resumo; quem
chama decide se dá commit ou rollback (é assim que a "prévia" não mente).
Reimportar o mesmo CNPJ atualiza os dados que vêm da lista e NUNCA mexe no que
a equipe decidiu (status, motivo, observação).
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import Integer, case, cast, func, or_
from sqlalchemy.orm import Session

from ..models import Cliente, Prospecto, StatusProspecto
from .cnpj import normalizar_cnpj
from .fontes.lista_prospectos import LinhaLista, ListaLida
from .ramos import TIPO_EMPRESA, TIPO_MEI, classificar_tipo, normalizar_porte, ramo_por_cnae

_LOTE_SQL = 500  # tamanho dos blocos em consultas com IN (...)

# Colunas que a listagem aceita para ordenar (nada vem direto da URL).
_ORDENAVEIS = {
    "razaoSocial": Prospecto.razao_social,
    "ramo": Prospecto.ramo,
    "tipo": Prospecto.tipo,
    "porte": Prospecto.porte,
    "capitalSocial": Prospecto.capital_social,
    "bairro": Prospecto.bairro,
    "cidade": Prospecto.cidade,
    "telefone": Prospecto.telefone,
    "situacaoLista": Prospecto.situacao_lista,
    "status": Prospecto.status,
}


def _cnpjs_da_carteira(db: Session) -> set[str]:
    """CNPJs (só dígitos) de quem já é cliente — o cadastro os guarda formatados."""
    return {normalizar_cnpj(c) for (c,) in db.query(Cliente.cnpj).filter(Cliente.cnpj.isnot(None)) if c}


def _campos_da_lista(linha: LinhaLista, arquivo: str | None, clientes: set[str]) -> dict:
    """Só os campos que vêm da lista — nunca os "donos do app"."""
    return {
        "razao_social": linha.razao_social,
        "capital_social": linha.capital_social,
        "porte": normalizar_porte(linha.porte),
        "situacao_lista": linha.situacao or None,
        "cnae_codigo": linha.cnae or None,
        "ramo": ramo_por_cnae(linha.cnae),
        "tipo": classificar_tipo(linha.razao_social),
        "logradouro": linha.logradouro or None,
        "numero": linha.numero or None,
        "bairro": linha.bairro or None,
        "cep": linha.cep or None,
        "cidade": linha.cidade or None,
        "uf": linha.uf or None,
        "telefone": linha.telefone or None,
        "email": linha.email or None,
        "ja_cliente": linha.cnpj in clientes,
        "lote": arquivo,
    }


def aplicar_lista(db: Session, lista: ListaLida, arquivo: str | None) -> dict:
    """Grava a lista (novos entram, existentes são atualizados) e devolve o resumo.

    Não dá commit: quem chama decide. Usa gravação em bloco — são dezenas de
    milhares de linhas num banco que fica longe do servidor, uma a uma seria
    inviável.
    """
    clientes = _cnpjs_da_carteira(db)
    existentes = {cnpj: id_ for id_, cnpj in db.query(Prospecto.id, Prospecto.cnpj)}

    novos, atualizados = [], []
    for linha in lista.linhas:
        campos = _campos_da_lista(linha, arquivo, clientes)
        if linha.cnpj in existentes:
            atualizados.append({"id": existentes[linha.cnpj], **campos})
        else:
            novos.append({"cnpj": linha.cnpj, "status": StatusProspecto.NOVO, **campos})

    if novos:
        db.bulk_insert_mappings(Prospecto, novos)
    if atualizados:
        db.bulk_update_mappings(Prospecto, atualizados)
    db.flush()
    _atualizar_ja_clientes(db, clientes)

    todos = novos + atualizados
    tipos = Counter(c["tipo"] for c in todos)
    ramos: dict[str, dict] = {}
    for c in todos:
        r = ramos.setdefault(c["ramo"], {"ramo": c["ramo"], "total": 0, "empresas": 0})
        r["total"] += 1
        r["empresas"] += c["tipo"] == TIPO_EMPRESA
    return {
        "linhasNoArquivo": len(lista.linhas) + lista.invalidas + lista.repetidas,
        "invalidas": lista.invalidas,
        "repetidas": lista.repetidas,
        "novos": len(novos),
        "atualizados": len(atualizados),
        "jaClientes": sum(1 for c in todos if c["ja_cliente"]),
        "empresas": tipos[TIPO_EMPRESA],
        "meiAutonomos": tipos[TIPO_MEI],
        "situacaoNoArquivo": dict(Counter(c["situacao_lista"] or "sem dado" for c in todos)),
        "cidades": [{"cidade": k or "sem cidade", "total": v}
                    for k, v in Counter(c["cidade"] for c in todos).most_common(8)],
        "ramos": sorted(ramos.values(), key=lambda r: -r["total"]),
    }


def _atualizar_ja_clientes(db: Session, clientes: set[str]) -> None:
    """Refaz a marca "já é cliente" em TODOS os prospectos, não só nos da lista:
    quem virou cliente desde a última importação precisa sair da lista de visita."""
    db.query(Prospecto).update({Prospecto.ja_cliente: False}, synchronize_session=False)
    lista = sorted(clientes)
    for i in range(0, len(lista), _LOTE_SQL):
        bloco = lista[i:i + _LOTE_SQL]
        db.query(Prospecto).filter(Prospecto.cnpj.in_(bloco)).update(
            {Prospecto.ja_cliente: True}, synchronize_session=False
        )


# ------------------------------------------------------------------ consulta

def _base(db: Session, cidade: str | None, incluir_clientes: bool = False):
    q = db.query(Prospecto)
    if not incluir_clientes:
        q = q.filter(Prospecto.ja_cliente.is_(False))
    if cidade:
        q = q.filter(Prospecto.cidade == cidade.strip().upper())
    return q


def resumo(db: Session, cidade: str | None = None) -> dict:
    """Números para a tela: tamanho da lista, e o que sobra por ramo depois de
    tirar quem já é cliente. Filtrar por cidade vale para tudo, menos para a
    lista de cidades (senão não dá para trocar de cidade)."""
    total_lista = db.query(func.count(Prospecto.id)).scalar() or 0
    ja_clientes = db.query(func.count(Prospecto.id)).filter(Prospecto.ja_cliente.is_(True)).scalar() or 0

    cidades = [
        {"cidade": c or "sem cidade", "total": n}
        for c, n in db.query(Prospecto.cidade, func.count(Prospecto.id))
        .filter(Prospecto.ja_cliente.is_(False))
        .group_by(Prospecto.cidade).order_by(func.count(Prospecto.id).desc())
    ]

    def soma(condicao):
        return func.coalesce(func.sum(cast(case((condicao, 1), else_=0), Integer)), 0)

    linhas = (
        _base(db, cidade)
        .with_entities(
            Prospecto.ramo,
            func.count(Prospecto.id),
            soma(Prospecto.tipo == TIPO_EMPRESA),
            soma((Prospecto.tipo == TIPO_EMPRESA) & (Prospecto.porte == "Micro")),
            soma((Prospecto.tipo == TIPO_EMPRESA) & (Prospecto.porte == "Pequena")),
            soma((Prospecto.tipo == TIPO_EMPRESA) & (Prospecto.porte == "Demais")),
        )
        .group_by(Prospecto.ramo)
        .all()
    )
    ramos = [
        {"ramo": r or "Outros", "total": t, "empresas": e, "micro": mi, "pequena": pe, "demais": de}
        for r, t, e, mi, pe, de in linhas
    ]
    ramos.sort(key=lambda r: -r["empresas"])
    return {
        "totalNaLista": total_lista,
        "jaClientes": ja_clientes,
        "naCidade": sum(r["total"] for r in ramos),
        "empresasNaCidade": sum(r["empresas"] for r in ramos),
        "cidades": cidades,
        "ramos": ramos,
    }


def listar(
    db: Session, *, cidade=None, ramo=None, tipo=None, porte=None, status=None, busca=None,
    ordenar="razaoSocial", direcao="asc", pagina=1, tamanho=50,
) -> tuple[list[Prospecto], int]:
    q = _base(db, cidade)
    if ramo:
        q = q.filter(Prospecto.ramo == ramo)
    if tipo:
        q = q.filter(Prospecto.tipo == tipo)
    if porte:
        q = q.filter(Prospecto.porte == porte)
    if status:
        q = q.filter(Prospecto.status == status)
    if busca and len(busca.strip()) >= 2:
        termo = f"%{busca.strip()}%"
        q = q.filter(or_(
            Prospecto.razao_social.ilike(termo),
            Prospecto.cnpj.ilike(f"%{normalizar_cnpj(busca) or busca.strip()}%"),
            Prospecto.bairro.ilike(termo),
        ))
    total = q.count()
    coluna = _ORDENAVEIS.get(ordenar, Prospecto.razao_social)
    ordem = coluna.desc() if direcao == "desc" else coluna.asc()
    # "nulos por último" nos dois sentidos, e o id de desempate mantém a
    # paginação estável quando muitas linhas têm o mesmo valor
    q = q.order_by(coluna.is_(None), ordem, Prospecto.id)
    itens = q.offset((pagina - 1) * tamanho).limit(tamanho).all()
    return itens, total


def para_saida(p: Prospecto) -> dict:
    return {
        "id": p.id,
        "cnpj": p.cnpj,
        "razaoSocial": p.razao_social,
        "capitalSocial": p.capital_social,
        "porte": p.porte,
        "ramo": p.ramo,
        "tipo": p.tipo,
        "logradouro": p.logradouro,
        "numero": p.numero,
        "bairro": p.bairro,
        "cep": p.cep,
        "cidade": p.cidade,
        "uf": p.uf,
        "telefone": p.telefone,
        "email": p.email,
        "situacaoLista": p.situacao_lista,
        "status": p.status.value if p.status else None,
        "lote": p.lote,
    }
