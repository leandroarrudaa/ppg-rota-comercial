"""Rotas do fluxo de visita: abrir, finalizar, relatório bloqueante, promessas."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario
from ..schemas import PromessaOut, RelatorioVisita, VisitaAbrir, VisitaOut
from ..services import auth
from ..services import visitas as svc

router = APIRouter(prefix="/api/visitas", tags=["visitas"])


@router.get("/pendente", response_model=VisitaOut | None)
def pendente(
    usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    """Visita em andamento do vendedor logado (pra restaurar o modal bloqueante
    se o app recarregar no meio de uma visita)."""
    return svc.visita_pendente(db, usuario)


@router.get("/hoje", response_model=list[int])
def visitados_hoje(
    usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    """IDs dos clientes já visitados hoje pelo vendedor logado — usado pra
    marcar riscado/cinza na lista da Rota do Dia."""
    return svc.cliente_ids_visitados_hoje(db, usuario)


@router.post("", response_model=VisitaOut)
def abrir(
    body: VisitaAbrir,
    usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    return svc.abrir(db, usuario, body.clienteId)


@router.patch("/{visita_id}/finalizar", response_model=VisitaOut)
def finalizar(
    visita_id: int,
    usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    return svc.finalizar(db, usuario, visita_id)


@router.post("/{visita_id}/relatorio", response_model=VisitaOut)
def relatorio(
    visita_id: int,
    dados: RelatorioVisita,
    usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    return svc.salvar_relatorio(db, usuario, visita_id, dados)


@router.patch("/promessas/{promessa_id}/cumprir", response_model=PromessaOut)
def cumprir_promessa(
    promessa_id: int,
    _usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    return svc.cumprir_promessa(db, promessa_id)
