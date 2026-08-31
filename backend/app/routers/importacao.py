"""Importação da carteira pela tela — prévia e confirmação, só para Admin.

Toda importação passa por duas etapas: `?confirmar=false` (padrão) roda tudo e
desfaz, devolvendo o que MUDARIA; `?confirmar=true` roda de novo e grava. É o
mesmo código nos dois casos, então a prévia não mente sobre o resultado.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Usuario
from ..services import atualizacao as svc
from ..services import auth
from ..services.fontes import pacote as pacote_fonte
from ..services.fontes import relatorio_vendas

router = APIRouter(prefix="/api/importacao", tags=["importacao"])

# Teto de tamanho do upload. O pacote real tem ~1 MB e o relatório do mês ~2 MB;
# 25 MB é folgado e ainda protege a memória do servidor (plano gratuito).
TAMANHO_MAXIMO = 25 * 1024 * 1024


async def _ler_upload(arquivo: UploadFile) -> bytes:
    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="O arquivo enviado está vazio.")
    if len(conteudo) > TAMANHO_MAXIMO:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo grande demais ({len(conteudo) / 1_048_576:.0f} MB). O limite é 25 MB.",
        )
    return conteudo


@router.post("/banco-mestre")
async def importar_banco_mestre(
    arquivo: UploadFile = File(...),
    confirmar: bool = Query(default=False),
    usuario: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Pacote mensal gerado do banco mestre — sobrepõe os números de venda."""
    conteudo = await _ler_upload(arquivo)
    try:
        dados = pacote_fonte.ler(conteudo)
    except pacote_fonte.PacoteInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    resumo = svc.aplicar_pacote(db, dados)
    if not confirmar:
        db.rollback()
        return {"previa": True, "resumo": resumo}

    svc.registrar(db, svc.TIPO_PACOTE, arquivo.filename, usuario, resumo)
    db.commit()
    return {"previa": False, "resumo": resumo}


@router.post("/relatorio-vendas")
async def importar_relatorio_vendas(
    arquivo: UploadFile = File(...),
    confirmar: bool = Query(default=False),
    usuario: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Relatório diário de vendas do ERP — soma os pedidos novos."""
    conteudo = await _ler_upload(arquivo)
    try:
        pedidos = relatorio_vendas.ler(conteudo)
    except relatorio_vendas.RelatorioInvalido as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    resumo = svc.aplicar_relatorio(db, pedidos)
    if not confirmar:
        db.rollback()
        return {"previa": True, "resumo": resumo}

    svc.registrar(db, svc.TIPO_RELATORIO, arquivo.filename, usuario, resumo)
    db.commit()
    return {"previa": False, "resumo": resumo}


@router.get("/historico")
def historico(
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Últimas importações — quem subiu o quê e quando."""
    return svc.historico_importacoes(db)
