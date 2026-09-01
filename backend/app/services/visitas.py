"""Regras do fluxo de visita: abrir, finalizar, relatório bloqueante e promessas."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..models import Cliente, Promessa, StatusVisita, Usuario, Visita
from ..schemas import ClienteAtualizar, PromessaOut, RelatorioVisita, VisitaOut
from . import clientes as clientes_svc
from .tempo import agora_utc, hoje_brasil, inicio_do_dia_brasil_em_utc


def _para_saida(v: Visita) -> VisitaOut:
    return VisitaOut(
        id=v.id,
        clienteId=v.cliente_id,
        vendedorId=v.vendedor_id,
        inicio=v.inicio,
        fim=v.fim,
        status=v.status,
        observacao=v.observacao,
        retornoDias=v.retorno_dias,
        retornoData=v.retorno_data,
        criadoEm=v.criado_em,
        promessas=[
            PromessaOut(
                id=p.id, clienteId=p.cliente_id, texto=p.texto,
                cumprida=p.cumprida, cumpridaEm=p.cumprida_em, criadoEm=p.criado_em,
            )
            for p in v.promessas
        ],
    )


def visita_pendente(db: Session, vendedor: Usuario) -> VisitaOut | None:
    """Visita em andamento (aberta ou aguardando relatório) do vendedor logado.
    Usado pra restaurar o estado bloqueante se o app recarregar no meio."""
    v = (
        db.query(Visita)
        .options(selectinload(Visita.promessas))
        .filter(
            Visita.vendedor_id == vendedor.id,
            Visita.status.in_([StatusVisita.ABERTA, StatusVisita.AGUARDANDO_RELATORIO]),
        )
        .order_by(Visita.inicio.desc())
        .first()
    )
    return _para_saida(v) if v else None


def abrir(db: Session, vendedor: Usuario, cliente_id: int) -> VisitaOut:
    if visita_pendente(db, vendedor) is not None:
        raise HTTPException(
            status_code=409,
            detail="Você já tem uma visita em andamento. Finalize-a antes de abrir outra.",
        )
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if not cliente.aceita_visita:
        raise HTTPException(
            status_code=400,
            detail="Este cliente está marcado como 'não aceita visita' — não é possível registrar uma visita presencial.",
        )
    v = Visita(cliente_id=cliente_id, vendedor_id=vendedor.id)
    db.add(v)
    db.commit()
    db.refresh(v)
    return _para_saida(v)


def cancelar(db: Session, vendedor: Usuario, visita_id: int) -> None:
    """Abandona uma visita ABERTA, apagando o registro.

    Existe porque a visita aberta é bloqueante: enquanto houver uma, o vendedor
    não consegue abrir nenhuma outra. Sem saída, uma visita esquecida (celular
    descarregou, saiu do app antes de finalizar) trava o sujeito em campo por
    tempo indeterminado — foi exatamente o que aconteceu.

    Apaga em vez de marcar como cancelada de propósito: uma visita abandonada
    não tem observação, nem promessa, nem hora de fim; não há o que preservar.
    Guardar exigiria um valor novo no tipo enumerado do Postgres, e uma
    migração de banco não é o que se quer no caminho de destravar alguém que
    já está parado. Nada de relatório é afetado — eles só contam visita
    FINALIZADA.

    Só a visita AGUARDANDO_RELATORIO não pode ser cancelada: essa já aconteceu
    de verdade e o relatório dela é obrigatório.
    """
    v = _buscar_da_vez(db, vendedor, visita_id)
    if v.status != StatusVisita.ABERTA:
        raise HTTPException(
            status_code=400,
            detail="Essa visita já foi finalizada — preencha o relatório para concluí-la.",
        )
    db.delete(v)
    db.commit()


def _buscar_da_vez(db: Session, vendedor: Usuario, visita_id: int) -> Visita:
    v = db.get(Visita, visita_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada")
    if v.vendedor_id != vendedor.id:
        raise HTTPException(status_code=403, detail="Essa visita não é sua")
    return v


def finalizar(db: Session, vendedor: Usuario, visita_id: int) -> VisitaOut:
    v = _buscar_da_vez(db, vendedor, visita_id)
    if v.status != StatusVisita.ABERTA:
        raise HTTPException(status_code=400, detail="Essa visita já foi finalizada")
    v.fim = agora_utc()
    v.status = StatusVisita.AGUARDANDO_RELATORIO
    db.commit()
    db.refresh(v)
    return _para_saida(v)


def salvar_relatorio(db: Session, vendedor: Usuario, visita_id: int, dados: RelatorioVisita) -> VisitaOut:
    v = _buscar_da_vez(db, vendedor, visita_id)
    if v.status != StatusVisita.AGUARDANDO_RELATORIO:
        raise HTTPException(
            status_code=400,
            detail="Essa visita não está aguardando relatório (finalize a visita primeiro).",
        )

    # valida e aplica ajustes de cliente ANTES de mexer na visita — se a
    # combinação for inválida (ex.: aceitaVisita=false sem motivo), nada
    # deve ficar meio-salvo.
    if dados.status is not None or dados.aceitaVisita is not None or dados.motivoRecusaVisita is not None:
        cliente = db.get(Cliente, v.cliente_id)
        clientes_svc.atualizar(cliente, ClienteAtualizar(
            status=dados.status,
            aceitaVisita=dados.aceitaVisita,
            motivoRecusaVisita=dados.motivoRecusaVisita,
        ))

    v.observacao = dados.observacao.strip()
    v.retorno_dias = dados.retornoDias
    # data de calendário em Brasília, não a do relógio do servidor (ver tempo.py)
    v.retorno_data = (hoje_brasil() + timedelta(days=dados.retornoDias)) if dados.retornoDias else None
    v.status = StatusVisita.FINALIZADA

    for texto in dados.promessas:
        texto = texto.strip()
        if texto:
            db.add(Promessa(cliente_id=v.cliente_id, visita_origem_id=v.id, texto=texto))

    db.commit()
    db.refresh(v)
    return _para_saida(v)


def historico_cliente(db: Session, cliente_id: int) -> list[VisitaOut]:
    visitas = (
        db.query(Visita)
        .options(selectinload(Visita.promessas))
        .filter(Visita.cliente_id == cliente_id, Visita.status == StatusVisita.FINALIZADA)
        .order_by(Visita.inicio.desc())
        .all()
    )
    return [_para_saida(v) for v in visitas]


def promessas_pendentes(db: Session, cliente_id: int) -> list[PromessaOut]:
    registros = (
        db.query(Promessa)
        .filter(Promessa.cliente_id == cliente_id, Promessa.cumprida.is_(False))
        .order_by(Promessa.criado_em)
        .all()
    )
    return [
        PromessaOut(id=p.id, clienteId=p.cliente_id, texto=p.texto, cumprida=p.cumprida,
                    cumpridaEm=p.cumprida_em, criadoEm=p.criado_em)
        for p in registros
    ]


def ids_com_promessa_pendente(db: Session, cliente_ids: list[int] | None = None) -> set[int]:
    """Cliente_ids que têm ao menos uma promessa não cumprida — usado pra
    marcar o ícone de presente nas listas sem consultar promessa por promessa."""
    q = db.query(Promessa.cliente_id).filter(Promessa.cumprida.is_(False)).distinct()
    if cliente_ids is not None:
        q = q.filter(Promessa.cliente_id.in_(cliente_ids))
    return {row[0] for row in q.all()}


def cliente_ids_visitados_hoje(db: Session, vendedor: Usuario) -> list[int]:
    """Clientes com visita FINALIZADA hoje (calendário de Brasília) pelo
    vendedor logado — usado pra marcar riscado/cinza na Rota do Dia."""
    limite = inicio_do_dia_brasil_em_utc(hoje_brasil())
    registros = (
        db.query(Visita.cliente_id)
        .filter(
            Visita.vendedor_id == vendedor.id,
            Visita.status == StatusVisita.FINALIZADA,
            Visita.inicio >= limite,
        )
        .distinct()
        .all()
    )
    return [r[0] for r in registros]


def cumprir_promessa(db: Session, promessa_id: int) -> PromessaOut:
    p = db.get(Promessa, promessa_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Promessa não encontrada")
    p.cumprida = True
    p.cumprida_em = agora_utc()
    db.commit()
    db.refresh(p)
    return PromessaOut(id=p.id, clienteId=p.cliente_id, texto=p.texto, cumprida=p.cumprida,
                        cumpridaEm=p.cumprida_em, criadoEm=p.criado_em)


# Quando voltar, para quem nunca combinou uma data no relatório. É a cadência
# de RELACIONAMENTO (de quanto em quanto tempo vale a pena aparecer), não a de
# compra — cliente Ouro merece presença mais frequente mesmo comprando pouco.
DIAS_ENTRE_VISITAS_POR_FAIXA = {"Ouro": 30, "Prata": 45, "Bronze": 60}
DIAS_ENTRE_VISITAS_PADRAO = 60


def agenda_de_visitas(db: Session, cliente_ids: list[int] | None = None) -> dict[int, dict]:
    """Última visita e data de retorno combinada, por cliente.

    É a informação que faltava para o Plano da Semana parar de repetir quem
    acabou de ser visitado: o vendedor JÁ escolhe "voltar em quantos dias" ao
    fechar cada relatório, e esse dado nunca era lido de volta.

    Vale para a empresa toda, não por vendedor: cliente visitado é cliente
    visitado, independente de quem foi — decisão explícita, para dois
    vendedores não baterem na mesma porta.

    Uma consulta agregada só, não uma por cliente: o banco fica longe do
    servidor e N idas e voltas custariam segundos na abertura da tela.
    """
    q = (
        db.query(
            Visita.cliente_id,
            func.max(Visita.inicio).label("ultima"),
            func.max(Visita.retorno_data).label("retorno"),
        )
        .filter(Visita.status == StatusVisita.FINALIZADA)
        .group_by(Visita.cliente_id)
    )
    if cliente_ids is not None:
        if not cliente_ids:
            return {}
        q = q.filter(Visita.cliente_id.in_(cliente_ids))

    return {
        cliente_id: {"ultima_visita": ultima, "retorno_data": retorno}
        for cliente_id, ultima, retorno in q.all()
    }


def proxima_visita(agenda: dict | None, faixa: str | None) -> tuple[date | None, date | None]:
    """(data da última visita, data em que vale voltar).

    Sem visita nenhuma, os dois são None — e "nunca visitado" é tratado como
    disponível agora, com prioridade, não como atrasado por tempo infinito.

    A data combinada pelo vendedor no relatório manda. Ela é uma decisão
    tomada na frente do cliente e vale mais que qualquer média estatística;
    só quando ela não existe é que se cai na cadência da faixa.
    """
    if not agenda or not agenda.get("ultima_visita"):
        return None, None

    ultima = agenda["ultima_visita"]
    ultima_data = ultima.date() if isinstance(ultima, datetime) else ultima

    combinada = agenda.get("retorno_data")
    if combinada:
        return ultima_data, combinada

    intervalo = DIAS_ENTRE_VISITAS_POR_FAIXA.get(faixa, DIAS_ENTRE_VISITAS_PADRAO)
    return ultima_data, ultima_data + timedelta(days=intervalo)
