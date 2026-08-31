"""Ajustes do negócio — leitura para qualquer logado, escrita só para Admin."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario
from ..services import auth
from ..services import configuracoes as svc

router = APIRouter(prefix="/api/configuracoes", tags=["configuracoes"])


class ValorNumerico(BaseModel):
    valor: float


@router.get("")
def listar(
    _usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    return svc.listar(db)


@router.put("/{chave}")
def definir(
    chave: str,
    dados: ValorNumerico,
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Grava a opção e já reaplica o efeito dela na carteira.

    O piso de risco só existe gravado na coluna `em_risco` dos clientes —
    salvar sem reavaliar deixaria a tela do vendedor mostrando a marcação
    antiga até a próxima importação.
    """
    valor = svc.definir_numero(db, chave, dados.valor)
    efeito = None
    if chave == svc.FATURAMENTO_MINIMO_RISCO:
        efeito = svc.reavaliar_risco(db, valor)
    db.commit()
    return {"chave": chave, "valor": valor, "efeito": efeito}
