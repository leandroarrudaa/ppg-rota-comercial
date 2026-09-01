"""Rotas de clientes: listagem com filtros, ficha e histórico de itens."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Cliente, HistoricoItemCliente, PapelUsuario, Usuario
from ..schemas import (
    AlterarStatusLote,
    ClienteAtualizar,
    ClienteCriarManual,
    ClienteOut,
    ClientesPagina,
    FichaClienteOut,
    HistoricoItemOut,
    HistoricoItensPagina,
    PromessaOut,
    VisitaOut,
)
from ..services import auth
from ..services import clientes as svc
from ..services import vinculos as vinculos_svc
from ..services import visitas as visitas_svc
from ..services.cnpj import normalizar_cnpj

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


@router.get("", response_model=list[ClienteOut])
def listar(
    faixa: str | None = None,
    cidade: str | None = None,
    emRisco: bool | None = None,
    busca: str | None = None,
    incluirInativos: bool = False,
    origem: str | None = None,
    bbox: str | None = Query(default=None, description="minLat,minLng,maxLat,maxLng"),
    elegivelVisita: bool = Query(default=False, description="Exclui inativos/aceitaVisita=false mesmo sem bbox — usado na busca da Rota do Dia"),
    _usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    bbox_tupla = None
    if bbox:
        try:
            partes = [float(x) for x in bbox.split(",")]
            if len(partes) != 4:
                raise ValueError
            bbox_tupla = tuple(partes)
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox inválido — use minLat,minLng,maxLat,maxLng")

    registros = svc.listar(
        db,
        faixa=faixa,
        cidade=cidade,
        em_risco=emRisco,
        busca=busca,
        incluir_inativos=incluirInativos,
        origem=origem,
        bbox=bbox_tupla,
        apenas_elegiveis_visita=elegivelVisita,
    )
    ids = [c.id for c in registros]
    pendentes = visitas_svc.ids_com_promessa_pendente(db, ids)
    # uma consulta agregada só para a carteira inteira — ver agenda_de_visitas
    agenda = visitas_svc.agenda_de_visitas(db, ids)
    return [
        svc.para_saida(c, tem_promessa=c.id in pendentes, agenda=agenda.get(c.id))
        for c in registros
    ]


@router.get("/admin", response_model=ClientesPagina)
def listar_admin(
    busca: str | None = None,
    faixa: str | None = None,
    cidade: str | None = None,
    origem: str | None = None,
    status: str | None = Query(default="ativo", description="ativo | inativo | todos"),
    aceitaVisita: bool | None = None,
    semLocalizacao: bool = False,
    vinculo: str | None = Query(default=None, description="com | sem"),
    ordenar: str = "faturamento",
    pagina: int = Query(default=1, ge=1),
    tamanho: int = Query(default=50, ge=1, le=200),
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Listagem de gestão da carteira — mostra inativo e quem não tem
    coordenada, ao contrário da listagem que alimenta o mapa e a rota."""
    registros, total = svc.listar_admin(
        db, busca=busca, faixa=faixa, cidade=cidade, origem=origem, status=status,
        aceita_visita=aceitaVisita, sem_localizacao=semLocalizacao, vinculo=vinculo,
        ordenar=ordenar, pagina=pagina, tamanho=tamanho,
    )
    pendentes = visitas_svc.ids_com_promessa_pendente(db, [c.id for c in registros])
    return ClientesPagina(
        total=total, pagina=pagina, tamanho=tamanho,
        itens=[svc.para_saida(c, tem_promessa=c.id in pendentes) for c in registros],
    )


@router.patch("/lote/status")
def alterar_status_lote(
    dados: AlterarStatusLote,
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Inativa/reativa vários clientes numa chamada só."""
    alterados = svc.alterar_status_em_lote(db, dados.clienteIds, dados.status)
    db.commit()
    return {"alterados": alterados}


@router.get("/cidades", response_model=list[str])
def cidades(
    _admin: Usuario = Depends(auth.requer_admin),
    db: Session = Depends(get_db),
):
    """Cidades distintas — alimenta o filtro da tela de gestão."""
    return [
        c for (c,) in db.query(Cliente.cidade).filter(Cliente.cidade.isnot(None))
        .distinct().order_by(Cliente.cidade)
    ]


@router.post("/manual", response_model=ClienteOut)
def cadastrar_manual(
    dados: ClienteCriarManual,
    _usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    """Cadastro de lead em campo — qualquer usuário logado pode cadastrar
    (não é restrito a admin: é o Taborda que descobre a empresa em campo)."""
    cliente = svc.criar_manual(db, dados)
    return svc.para_saida(cliente)


@router.get("/{cliente_id}", response_model=ClienteOut)
def obter(
    cliente_id: int,
    _usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    tem_promessa = cliente_id in visitas_svc.ids_com_promessa_pendente(db, [cliente_id])
    agenda = visitas_svc.agenda_de_visitas(db, [cliente_id]).get(cliente_id)
    return svc.para_saida(cliente, tem_promessa=tem_promessa, agenda=agenda)


@router.patch("/{cliente_id}", response_model=ClienteOut)
def atualizar(
    cliente_id: int,
    dados: ClienteAtualizar,
    _usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    svc.atualizar(cliente, dados)
    db.commit()
    db.refresh(cliente)
    tem_promessa = cliente_id in visitas_svc.ids_com_promessa_pendente(db, [cliente_id])
    agenda = visitas_svc.agenda_de_visitas(db, [cliente_id]).get(cliente_id)
    return svc.para_saida(cliente, tem_promessa=tem_promessa, agenda=agenda)


@router.get("/{cliente_id}/historico-itens", response_model=HistoricoItensPagina)
def historico_itens(
    cliente_id: int,
    pagina: int = Query(default=1, ge=1),
    tamanho: int = Query(default=20, ge=1, le=100),
    todos: bool = Query(default=False, description="Ignora paginação e traz a lista inteira (ordenação/paginação feita no navegador)"),
    _usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    """Histórico de compra por produto (maior valor primeiro por padrão)."""
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return _montar_historico(db, cliente, pagina=pagina, tamanho=tamanho, todos=todos)


def _montar_historico(
    db: Session, cliente: Cliente, *, pagina: int, tamanho: int, todos: bool
) -> HistoricoItensPagina:
    """Histórico por produto do cliente. Extraído para ser reaproveitado pela
    rota unificada da ficha, sem duplicar a consulta."""
    cnpj = normalizar_cnpj(cliente.cnpj)
    if not cnpj:
        return HistoricoItensPagina(total=0, pagina=1, tamanho=tamanho, itens=[])

    q = (
        db.query(HistoricoItemCliente)
        .filter(HistoricoItemCliente.cnpj_normalizado == cnpj)
        .order_by(HistoricoItemCliente.valor_total.desc())
    )
    total = q.count()
    if todos:
        registros = q.all()
    else:
        registros = q.offset((pagina - 1) * tamanho).limit(tamanho).all()
    itens = [
        HistoricoItemOut(
            codigoProduto=r.codigo_produto,
            descricaoProduto=r.descricao_produto,
            quantidadeTotal=r.quantidade_total,
            valorTotal=r.valor_total,
            numeroCompras=r.numero_compras,
            ultimaCompra=r.ultima_compra,
        )
        for r in registros
    ]
    if todos:
        return HistoricoItensPagina(total=total, pagina=1, tamanho=total, itens=itens)
    return HistoricoItensPagina(total=total, pagina=pagina, tamanho=tamanho, itens=itens)


@router.get("/{cliente_id}/visitas", response_model=list[VisitaOut])
def historico_visitas(
    cliente_id: int,
    _usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    """Visitas já concluídas (com relatório), mais recente primeiro."""
    return visitas_svc.historico_cliente(db, cliente_id)


@router.get("/{cliente_id}/ficha", response_model=FichaClienteOut)
def ficha(
    cliente_id: int,
    usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    """Ficha completa numa resposta só — cliente, promessas, visitas, histórico
    e vínculo. Substitui as 4-5 chamadas que a tela fazia ao abrir."""
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    tem_promessa = cliente_id in visitas_svc.ids_com_promessa_pendente(db, [cliente_id])

    # O vínculo é informação de admin — para vendedor a ficha vem sem ele,
    # igual ao que a tela já fazia quando pedia as coisas separadamente.
    vinculo = None
    if usuario.papel == PapelUsuario.ADMIN and cliente.cliente_mestre_id:
        try:
            vinculo = vinculos_svc.obter_consolidado(db, cliente.cliente_mestre_id)
        except HTTPException:
            vinculo = None

    return FichaClienteOut(
        cliente=svc.para_saida(cliente, tem_promessa=tem_promessa),
        promessas=visitas_svc.promessas_pendentes(db, cliente_id),
        visitas=visitas_svc.historico_cliente(db, cliente_id),
        historico=_montar_historico(db, cliente, pagina=1, tamanho=20, todos=True),
        vinculo=vinculo,
    )


@router.get("/{cliente_id}/promessas", response_model=list[PromessaOut])
def promessas_pendentes(
    cliente_id: int,
    _usuario: Usuario = Depends(auth.usuario_atual),
    db: Session = Depends(get_db),
):
    """Promessas ainda não cumpridas — aparecem em destaque na ficha."""
    return visitas_svc.promessas_pendentes(db, cliente_id)
