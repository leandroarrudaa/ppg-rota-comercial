"""Vínculo de CNPJ: sugestão automática (nome parecido e/ou endereço exato —
rua e número, não CEP) e criação/desfazimento manual do "cliente mestre" que
agrega N CNPJs.
"""
from __future__ import annotations

import difflib
import re
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Cliente, ClienteMestre, StatusCliente, StatusSugestaoVinculo, SugestaoVinculo
from ..schemas import ClienteMestreOut, ClienteResumo, SugestaoVinculoOut
from .tempo import agora_utc

SUFIXOS_SOCIETARIOS = {"LTDA", "ME", "EPP", "EIRELI", "SA", "S", "A", "MEI"}
LIMIAR_SIMILARIDADE = 0.82


def _nome_normalizado(nome: str) -> str:
    palavras = re.sub(r"[^\w\s]", " ", (nome or "").upper()).split()
    return " ".join(p for p in palavras if p not in SUFIXOS_SOCIETARIOS)


def _endereco_normalizado(endereco: str | None) -> str:
    return re.sub(r"\s+", " ", (endereco or "").upper().strip())


def _comparar(a: Cliente, b: Cliente) -> tuple[str, float] | tuple[None, None]:
    """CEP sozinho é largo demais (cobre a rua/quadra inteira, não um endereço
    específico) — o critério de endereço exige rua+número batendo exatamente.
    Nome parecido + endereço igual é o sinal mais forte (mesma empresa em CNPJs
    diferentes); endereço igual com nomes diferentes ainda vale a pena revisar
    (podem ser empresas do mesmo grupo/sócio no mesmo imóvel); nome parecido
    com endereços diferentes é o sinal mais fraco, mas ainda entra na fila."""
    end_a, end_b = _endereco_normalizado(a.endereco), _endereco_normalizado(b.endereco)
    mesmo_endereco = bool(end_a) and end_a == end_b

    na, nb = _nome_normalizado(a.nome), _nome_normalizado(b.nome)
    score_nome = difflib.SequenceMatcher(None, na, nb).ratio() if na and nb else 0.0
    nome_parecido = score_nome >= LIMIAR_SIMILARIDADE

    if mesmo_endereco and nome_parecido:
        return "mesmo endereço e nome parecido", round(max(score_nome, 0.95), 2)
    if mesmo_endereco:
        return "mesmo endereço", 0.85
    if nome_parecido:
        return "nome parecido", round(score_nome, 2)
    return None, None


def gerar_sugestoes(db: Session) -> int:
    """Gera candidatos a vínculo comparando clientes ativos sem mestre ainda,
    agrupados por cidade (comparar cidades diferentes não faz sentido aqui e
    evitaria O(n²) sobre a carteira inteira). Sugestões já recusadas não são
    recriadas (UniqueConstraint do par + checagem prévia)."""
    clientes = (
        db.query(Cliente)
        .filter(Cliente.status == StatusCliente.ATIVO, Cliente.cliente_mestre_id.is_(None))
        .all()
    )
    existentes = {
        (min(s.cliente_a_id, s.cliente_b_id), max(s.cliente_a_id, s.cliente_b_id))
        for s in db.query(SugestaoVinculo).all()
    }

    por_cidade: dict[str, list[Cliente]] = defaultdict(list)
    for c in clientes:
        por_cidade[(c.cidade or "").upper()].append(c)

    criadas = 0
    for grupo in por_cidade.values():
        for i in range(len(grupo)):
            for j in range(i + 1, len(grupo)):
                a, b = grupo[i], grupo[j]
                par = (min(a.id, b.id), max(a.id, b.id))
                if par in existentes:
                    continue
                motivo, score = _comparar(a, b)
                if motivo:
                    db.add(SugestaoVinculo(cliente_a_id=par[0], cliente_b_id=par[1], motivo=motivo, score=score))
                    existentes.add(par)
                    criadas += 1
    db.commit()
    return criadas


def _resumo(c: Cliente) -> ClienteResumo:
    return ClienteResumo(
        id=c.id, nome=c.nome, cnpj=c.cnpj, cidade=c.cidade, endereco=c.endereco,
        faixa=c.faixa, fat=c.fat_total,
    )


def listar_sugestoes_pendentes(db: Session) -> list[SugestaoVinculoOut]:
    pendentes = (
        db.query(SugestaoVinculo)
        .filter(SugestaoVinculo.status == StatusSugestaoVinculo.PENDENTE)
        .order_by(SugestaoVinculo.score.desc())
        .all()
    )
    saida = []
    for s in pendentes:
        a, b = db.get(Cliente, s.cliente_a_id), db.get(Cliente, s.cliente_b_id)
        if a is None or b is None:
            continue
        saida.append(SugestaoVinculoOut(id=s.id, clienteA=_resumo(a), clienteB=_resumo(b), motivo=s.motivo, score=s.score))
    return saida


def _unir(db: Session, cliente_a: Cliente, cliente_b: Cliente) -> ClienteMestre:
    """Une dois clientes num único cliente mestre, fundindo grupos existentes
    se algum dos dois já tinha vínculo."""
    mestre_a = db.get(ClienteMestre, cliente_a.cliente_mestre_id) if cliente_a.cliente_mestre_id else None
    mestre_b = db.get(ClienteMestre, cliente_b.cliente_mestre_id) if cliente_b.cliente_mestre_id else None

    if mestre_a and mestre_b and mestre_a.id != mestre_b.id:
        # funde: move os membros de B pro grupo de A e remove o mestre de B
        for membro in db.query(Cliente).filter(Cliente.cliente_mestre_id == mestre_b.id).all():
            membro.cliente_mestre_id = mestre_a.id
        db.delete(mestre_b)
        return mestre_a
    if mestre_a:
        cliente_b.cliente_mestre_id = mestre_a.id
        return mestre_a
    if mestre_b:
        cliente_a.cliente_mestre_id = mestre_b.id
        return mestre_b

    nome_preferido = cliente_a.nome if (cliente_a.fat_total or 0) >= (cliente_b.fat_total or 0) else cliente_b.nome
    novo = ClienteMestre(nome_preferido=nome_preferido)
    db.add(novo)
    db.flush()  # garante novo.id antes de atribuir
    cliente_a.cliente_mestre_id = novo.id
    cliente_b.cliente_mestre_id = novo.id
    return novo


def resolver_sugestao(db: Session, sugestao_id: int, aceitar: bool):
    s = db.get(SugestaoVinculo, sugestao_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Sugestão não encontrada")
    if s.status != StatusSugestaoVinculo.PENDENTE:
        raise HTTPException(status_code=400, detail="Essa sugestão já foi resolvida")

    if aceitar:
        a, b = db.get(Cliente, s.cliente_a_id), db.get(Cliente, s.cliente_b_id)
        if a is None or b is None:
            raise HTTPException(status_code=404, detail="Cliente da sugestão não encontrado")
        _unir(db, a, b)
        s.status = StatusSugestaoVinculo.ACEITO
    else:
        s.status = StatusSugestaoVinculo.RECUSADO
    s.resolvido_em = agora_utc()
    db.commit()


def criar_vinculo_manual(db: Session, cliente_ids: list[int]) -> ClienteMestre:
    clientes = db.query(Cliente).filter(Cliente.id.in_(cliente_ids)).all()
    if len(clientes) != len(set(cliente_ids)):
        raise HTTPException(status_code=404, detail="Um ou mais clientes não foram encontrados")
    base = clientes[0]
    mestre = None
    for outro in clientes[1:]:
        mestre = _unir(db, base, outro)
    db.commit()
    db.refresh(mestre)
    return mestre


def buscar_para_vincular(db: Session, q: str, excluir_id: int) -> list[ClienteResumo]:
    padrao = f"%{q.strip()}%"
    registros = (
        db.query(Cliente)
        .filter(Cliente.id != excluir_id, (Cliente.nome.ilike(padrao)) | (Cliente.cnpj.ilike(padrao)))
        .order_by(Cliente.nome)
        .limit(20)
        .all()
    )
    return [_resumo(c) for c in registros]


def obter_consolidado(db: Session, mestre_id: int) -> ClienteMestreOut:
    mestre = db.get(ClienteMestre, mestre_id)
    if mestre is None:
        raise HTTPException(status_code=404, detail="Vínculo não encontrado")
    membros = db.query(Cliente).filter(Cliente.cliente_mestre_id == mestre_id).all()
    fat_total = sum(c.fat_total or 0 for c in membros)
    no_compras = sum(c.no_compras or 0 for c in membros)
    ordem_faixa = {"Ouro": 3, "Prata": 2, "Bronze": 1}
    melhor_faixa = max((c.faixa for c in membros if c.faixa), key=lambda f: ordem_faixa.get(f, 0), default=None)
    return ClienteMestreOut(
        id=mestre.id, nomePreferido=mestre.nome_preferido,
        membros=[_resumo(c) for c in membros],
        fatTotal=fat_total, noCompras=no_compras, faixa=melhor_faixa,
    )


def desvincular(db: Session, mestre_id: int, cliente_id: int):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None or cliente.cliente_mestre_id != mestre_id:
        raise HTTPException(status_code=404, detail="Cliente não pertence a esse vínculo")
    cliente.cliente_mestre_id = None
    db.flush()  # sessão é autoflush=False — sem isso a contagem abaixo não vê essa mudança
    restantes = db.query(Cliente).filter(Cliente.cliente_mestre_id == mestre_id).count()
    if restantes <= 1:
        # vínculo de 1 membro só não faz sentido — desfaz o grupo inteiro
        for membro in db.query(Cliente).filter(Cliente.cliente_mestre_id == mestre_id).all():
            membro.cliente_mestre_id = None
        mestre = db.get(ClienteMestre, mestre_id)
        if mestre:
            db.delete(mestre)
    db.commit()
