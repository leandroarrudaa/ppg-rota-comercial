"""Rotas de autenticação: setup inicial, login e gestão de usuários."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import PapelUsuario, Usuario
from ..schemas import LoginBody, SetupBody, TokenOut, UsuarioCriar, UsuarioOut
from ..services import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def status(db: Session = Depends(get_db)):
    """Informa se o app ainda precisa do setup inicial (nenhum usuário criado)."""
    tem_usuario = db.query(Usuario.id).first() is not None
    return {"precisa_setup": not tem_usuario}


@router.post("/setup", response_model=TokenOut)
def setup(body: SetupBody, db: Session = Depends(get_db)):
    """Cria o primeiro usuário (admin). Só funciona com o banco vazio."""
    if db.query(Usuario.id).first() is not None:
        raise HTTPException(status_code=400, detail="Setup já foi feito")
    usuario = Usuario(
        nome=body.nome.strip(),
        usuario=body.usuario.strip().lower(),
        senha_hash=auth.gerar_hash(body.senha),
        papel=PapelUsuario.ADMIN,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return TokenOut(token=auth.criar_token(usuario), usuario=UsuarioOut.model_validate(usuario))


@router.post("/login", response_model=TokenOut)
def login(body: LoginBody, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.usuario == body.usuario.strip().lower()).first()
    if usuario is None or not auth.verificar_senha(body.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
    return TokenOut(token=auth.criar_token(usuario), usuario=UsuarioOut.model_validate(usuario))


@router.get("/eu", response_model=UsuarioOut)
def eu(usuario: Usuario = Depends(auth.usuario_atual)):
    return usuario


@router.get("/usuarios", response_model=list[UsuarioOut])
def listar_usuarios(
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    return db.query(Usuario).order_by(Usuario.nome).all()


@router.post("/usuarios", response_model=UsuarioOut)
def criar_usuario(
    body: UsuarioCriar,
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    login_novo = body.usuario.strip().lower()
    if db.query(Usuario).filter(Usuario.usuario == login_novo).first():
        raise HTTPException(status_code=400, detail="Já existe um usuário com esse login")
    usuario = Usuario(
        nome=body.nome.strip(),
        usuario=login_novo,
        senha_hash=auth.gerar_hash(body.senha),
        papel=body.papel,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@router.delete("/usuarios/{usuario_id}")
def remover_usuario(
    usuario_id: int,
    admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    if usuario_id == admin.id:
        raise HTTPException(status_code=400, detail="Você não pode remover a si mesmo")
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    db.delete(usuario)
    db.commit()
    return {"ok": True}
