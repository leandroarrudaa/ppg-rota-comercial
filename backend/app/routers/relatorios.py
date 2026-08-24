"""Rota de relatórios: visão consolidada das visitas já realizadas, por período."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario
from ..schemas import RelatorioVisitasOut
from ..services import auth
from ..services import relatorios as svc

router = APIRouter(prefix="/api/relatorios", tags=["relatorios"])


@router.get("/visitas", response_model=RelatorioVisitasOut)
def visitas(
    inicio: date = Query(..., description="Primeiro dia do período (calendário de Brasília)"),
    fim: date = Query(..., description="Último dia do período, inclusive"),
    vendedorId: int | None = Query(default=None, description="Admin só: filtra por vendedor. Omitido = todo mundo."),
    usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    if fim < inicio:
        raise HTTPException(status_code=400, detail="O fim do período não pode vir antes do início.")
    if (fim - inicio).days > 366:
        raise HTTPException(status_code=400, detail="Escolha um período de até 1 ano.")
    return svc.relatorio_visitas(db, usuario=usuario, inicio=inicio, fim=fim, vendedor_id=vendedorId)
