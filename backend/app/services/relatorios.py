"""Consulta consolidada de visitas já realizadas — alimenta a tela de
Relatórios (visão do que o time fez, por período)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from ..models import PapelUsuario, StatusVisita, Usuario, Visita
from ..schemas import PromessaOut, RelatorioResumo, RelatorioVisitasOut, VisitaRelatorioItem
from .tempo import inicio_do_dia_brasil_em_utc


def relatorio_visitas(
    db: Session, *, usuario: Usuario, inicio: date, fim: date, vendedor_id: int | None
) -> RelatorioVisitasOut:
    """Visitas FINALIZADAS no período [inicio, fim] — datas de calendário em
    Brasília, ambas inclusive. Vendedor só enxerga as próprias visitas; admin
    vê de todo mundo por padrão, ou de um vendedor específico via vendedor_id."""
    if usuario.papel != PapelUsuario.ADMIN:
        if vendedor_id is not None and vendedor_id != usuario.id:
            raise HTTPException(status_code=403, detail="Você só pode ver suas próprias visitas.")
        vendedor_id = usuario.id

    limite_inicial = inicio_do_dia_brasil_em_utc(inicio)
    limite_final = inicio_do_dia_brasil_em_utc(fim + timedelta(days=1))  # exclusivo

    q = (
        db.query(Visita)
        .options(
            selectinload(Visita.promessas),
            selectinload(Visita.cliente),
            selectinload(Visita.vendedor),
        )
        .filter(
            Visita.status == StatusVisita.FINALIZADA,
            Visita.inicio >= limite_inicial,
            Visita.inicio < limite_final,
        )
    )
    if vendedor_id is not None:
        q = q.filter(Visita.vendedor_id == vendedor_id)
    visitas = q.order_by(Visita.inicio.desc()).all()

    return RelatorioVisitasOut(
        resumo=_montar_resumo(visitas),
        visitas=[_para_item(v) for v in visitas],
    )


def _para_item(v: Visita) -> VisitaRelatorioItem:
    duracao = round((v.fim - v.inicio).total_seconds() / 60) if v.fim else None
    return VisitaRelatorioItem(
        id=v.id,
        clienteId=v.cliente_id,
        clienteNome=v.cliente.nome if v.cliente else "Cliente removido",
        clienteCidade=v.cliente.cidade if v.cliente else None,
        vendedorId=v.vendedor_id,
        vendedorNome=v.vendedor.nome if v.vendedor else "—",
        inicio=v.inicio,
        fim=v.fim,
        duracaoMin=duracao,
        observacao=v.observacao,
        retornoDias=v.retorno_dias,
        retornoData=v.retorno_data,
        promessas=[
            PromessaOut(
                id=p.id, clienteId=p.cliente_id, texto=p.texto,
                cumprida=p.cumprida, cumpridaEm=p.cumprida_em, criadoEm=p.criado_em,
            )
            for p in v.promessas
        ],
    )


def _montar_resumo(visitas: list[Visita]) -> RelatorioResumo:
    duracoes = [(v.fim - v.inicio).total_seconds() / 60 for v in visitas if v.fim]
    return RelatorioResumo(
        totalVisitas=len(visitas),
        clientesUnicos=len({v.cliente_id for v in visitas}),
        duracaoMediaMin=round(sum(duracoes) / len(duracoes)) if duracoes else None,
        promessasFeitas=sum(len(v.promessas) for v in visitas),
        retornosAgendados=sum(1 for v in visitas if v.retorno_data is not None),
    )
