"""Rotas de vínculo de CNPJ: sugestões automáticas + criação/desfazimento manual."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario
from ..schemas import ClienteMestreOut, ClienteResumo, ResolverSugestao, SugestaoVinculoOut, VinculoManualCriar
from ..services import auth
from ..services import vinculos as svc

router = APIRouter(prefix="/api/vinculos", tags=["vinculos"])


@router.post("/gerar-sugestoes")
def gerar_sugestoes(
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    criadas = svc.gerar_sugestoes(db)
    return {"criadas": criadas}


@router.get("/sugestoes", response_model=list[SugestaoVinculoOut])
def listar_sugestoes(
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    return svc.listar_sugestoes_pendentes(db)


@router.patch("/sugestoes/{sugestao_id}")
def resolver_sugestao(
    sugestao_id: int,
    dados: ResolverSugestao,
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    svc.resolver_sugestao(db, sugestao_id, dados.aceitar)
    return {"ok": True}


@router.get("/buscar", response_model=list[ClienteResumo])
def buscar(
    q: str = Query(min_length=2),
    excluirId: int = Query(...),
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    return svc.buscar_para_vincular(db, q, excluirId)


@router.post("", response_model=ClienteMestreOut)
def criar_vinculo(
    dados: VinculoManualCriar,
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    mestre = svc.criar_vinculo_manual(db, dados.clienteIds)
    return svc.obter_consolidado(db, mestre.id)


@router.get("/{mestre_id}", response_model=ClienteMestreOut)
def obter(
    mestre_id: int,
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    return svc.obter_consolidado(db, mestre_id)


@router.delete("/{mestre_id}/membros/{cliente_id}")
def desvincular(
    mestre_id: int,
    cliente_id: int,
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    svc.desvincular(db, mestre_id, cliente_id)
    return {"ok": True}
