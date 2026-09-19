"""Prospecção: importação da lista de empresas novas e consulta — só Admin.

A importação segue o mesmo padrão da carteira: `?confirmar=false` (padrão) roda
tudo e desfaz, devolvendo o que MUDARIA; `?confirmar=true` grava.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import StatusProspecto, Usuario
from ..services import atualizacao
from ..services import auth
from ..services import conferencia_receita
from ..services import prospeccao as svc
from ..services.fontes import lista_prospectos
from .importacao import _ler_upload

router = APIRouter(prefix="/api/prospectos", tags=["prospectos"])

TIPO_IMPORTACAO = "prospectos"


@router.post("/importar")
async def importar_lista(
    arquivo: UploadFile = File(...),
    confirmar: bool = Query(default=False),
    usuario: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Lista de empresas (.xlsx ou .csv) — entram as novas, as já conhecidas
    são atualizadas, e o que a equipe decidiu sobre elas é preservado."""
    conteudo = await _ler_upload(arquivo)
    try:
        lista = lista_prospectos.ler(conteudo)
    except lista_prospectos.ListaInvalida as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    resumo = svc.aplicar_lista(db, lista, arquivo.filename)
    if not confirmar:
        db.rollback()
        return {"previa": True, "resumo": resumo}

    atualizacao.registrar(db, TIPO_IMPORTACAO, arquivo.filename, usuario, resumo)
    db.commit()
    return {"previa": False, "resumo": resumo}


@router.get("/resumo")
def resumo(
    cidade: str | None = None,
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Tamanho da lista e o que sobra por ramo, já sem quem é cliente."""
    return svc.resumo(db, cidade)


@router.get("")
def listar(
    cidade: str | None = None,
    ramo: str | None = None,
    tipo: str | None = Query(default=None, pattern="^(empresa|mei_autonomo)$"),
    porte: str | None = None,
    status: StatusProspecto | None = None,
    busca: str | None = None,
    situacao: str = Query(default="", pattern="^(|ativa|nao_conferida|nao_ativa|todas)$"),
    ordenar: str = "razaoSocial",
    direcao: str = Query(default="asc", pattern="^(asc|desc)$"),
    pagina: int = Query(default=1, ge=1),
    tamanho: int = Query(default=50, ge=1, le=200),
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    itens, total = svc.listar(
        db, cidade=cidade, ramo=ramo, tipo=tipo, porte=porte, status=status, busca=busca,
        situacao=situacao, ordenar=ordenar, direcao=direcao, pagina=pagina, tamanho=tamanho,
    )
    pendentes = svc.pendentes_de_conferencia(
        db, cidade=cidade, ramo=ramo, tipo=tipo, porte=porte, status=status, busca=busca,
    )
    return {
        "total": total, "pagina": pagina, "tamanho": tamanho,
        # quantas do filtro atual ainda não foram conferidas na Receita
        "pendentesConferencia": pendentes,
        "itens": [svc.para_saida(p) for p in itens],
    }


class FiltrosConferencia(BaseModel):
    """Os mesmos filtros da lista: confere só o que a tela está mostrando."""
    cidade: str | None = None
    ramo: str | None = None
    tipo: str | None = None
    porte: str | None = None
    busca: str | None = None


# Quantas empresas por chamada. O tempo de cada chamada é limitado por um
# orçamento (ver conferencia_receita); a tela chama de novo até zerar.
LOTE_CONFERENCIA = 45


@router.post("/conferir-receita")
def conferir_receita(
    filtros: FiltrosConferencia,
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Consulta a Receita para as empresas do filtro que ainda não foram
    conferidas e grava a situação. Quem não estiver ativa some da lista."""
    pendentes, _total = svc.pendentes_de_conferencia(db, limite=LOTE_CONFERENCIA, **filtros.model_dump())
    resultado = conferencia_receita.conferir_lote(db, pendentes)
    db.flush()  # a sessão roda com autoflush=False: sem isto, "restam" não veria este lote
    resultado["restam"] = svc.pendentes_de_conferencia(db, **filtros.model_dump())
    db.commit()
    return resultado
