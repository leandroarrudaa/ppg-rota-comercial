"""Consultas e conversões de clientes (filtros da listagem + formato de saída)."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import Cliente, OrigemCliente, StatusCliente
from ..schemas import ClienteAtualizar, ClienteCriarManual, ClienteOut


def para_saida(c: Cliente, tem_promessa: bool = False) -> ClienteOut:
    """Converte o modelo do banco pro formato que o frontend já consome
    (mesmos nomes de campo do antigo clientes.json)."""
    return ClienteOut(
        id=c.id,
        cnpj=c.cnpj,
        nome=c.nome,
        endereco=c.endereco,
        bairro=c.bairro,
        cidade=c.cidade,
        uf=c.uf,
        lat=c.lat,
        lng=c.lng,
        geo=c.geo_status,
        origem=c.origem,
        faixa=c.faixa,
        emRisco=c.em_risco,
        fat=c.fat_total,
        compras=c.no_compras,
        ticket=c.ticket_medio,
        recencia=c.recencia_dias,
        cadencia=c.cadencia_dias,
        ultimaCompra=c.ultima_compra.isoformat() if c.ultima_compra else None,
        porte=c.porte,
        capital=c.capital_social,
        cnae=c.cnae,
        telefone=c.telefone,
        email=c.email,
        R=c.r,
        F=c.f,
        M=c.m,
        score=c.rfm_score,
        status=c.status,
        aceitaVisita=c.aceita_visita,
        motivoRecusaVisita=c.motivo_recusa_visita,
        contatoNome=c.contato_nome,
        contatoCelular=c.contato_celular,
        clienteMestreId=c.cliente_mestre_id,
        temPromessaPendente=tem_promessa,
    )


def listar(
    db: Session,
    faixa: str | None = None,
    cidade: str | None = None,
    em_risco: bool | None = None,
    busca: str | None = None,
    incluir_inativos: bool = False,
    origem: str | None = None,
    apenas_com_geo: bool = True,
    bbox: tuple[float, float, float, float] | None = None,
    apenas_elegiveis_visita: bool = False,
) -> list[Cliente]:
    """Lista clientes aplicando os filtros. Inativos ficam de fora por padrão
    (só entram com incluir_inativos=True — o checkbox opt-in da interface).

    Quando `bbox` é informado (viewport do mapa) OU `apenas_elegiveis_visita`
    é True (busca em toda a carteira na Rota do Dia, sem bbox), o resultado é
    sempre restrito a quem pode entrar numa rota de visita: nunca inclui
    inativos nem `aceita_visita=False`, independente de `incluir_inativos`."""
    q = db.query(Cliente)
    if bbox is not None or apenas_elegiveis_visita:
        incluir_inativos = False
        q = q.filter(Cliente.aceita_visita.is_(True))
    if not incluir_inativos:
        q = q.filter(Cliente.status == StatusCliente.ATIVO)
    if apenas_com_geo:
        q = q.filter(Cliente.lat.isnot(None), Cliente.lng.isnot(None))
    if bbox is not None:
        min_lat, min_lng, max_lat, max_lng = bbox
        q = q.filter(
            Cliente.lat >= min_lat, Cliente.lat <= max_lat,
            Cliente.lng >= min_lng, Cliente.lng <= max_lng,
        )
    if faixa:
        q = q.filter(Cliente.faixa == faixa)
    if cidade:
        q = q.filter(Cliente.cidade == cidade)
    if em_risco is not None:
        q = q.filter(Cliente.em_risco == em_risco)
    if origem:
        q = q.filter(Cliente.origem == origem)
    if busca:
        padrao = f"%{busca.strip()}%"
        q = q.filter(or_(Cliente.nome.ilike(padrao), Cliente.cnpj.ilike(padrao)))
    return q.order_by(Cliente.rfm_score.desc().nullslast(), Cliente.nome).all()


def criar_manual(db: Session, dados: ClienteCriarManual) -> Cliente:
    """Cadastro de lead em campo — o vendedor marca o pin no mapa, sem
    depender de geocodificação (decisão explícita: mais simples e mais
    preciso que tentar geocodificar um endereço digitado)."""
    cliente = Cliente(
        nome=dados.nome.strip(),
        endereco=dados.endereco,
        bairro=dados.bairro,
        cidade=dados.cidade,
        uf=dados.uf,
        cnpj=dados.cnpj or None,
        contato_nome=dados.contatoNome,
        contato_celular=dados.contatoCelular,
        lat=dados.lat,
        lng=dados.lng,
        geo_status="manual",
        origem=OrigemCliente.NOVO,
        status=StatusCliente.ATIVO,
        aceita_visita=True,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def atualizar(cliente: Cliente, dados: ClienteAtualizar) -> Cliente:
    """Aplica só os campos enviados (PATCH parcial). Exige motivo quando
    aceitaVisita passa a False — sem motivo a exclusão de listas de rota
    não teria explicação pra quem olhar depois."""
    valores = dados.model_dump(exclude_unset=True)

    aceita_final = valores.get("aceitaVisita", cliente.aceita_visita)
    motivo_final = valores.get("motivoRecusaVisita", cliente.motivo_recusa_visita)
    if aceita_final is False and motivo_final is None:
        raise HTTPException(
            status_code=400,
            detail="Informe o motivo (calote ou sem-visita) ao marcar que o cliente não aceita visita.",
        )
    if aceita_final is True:
        motivo_final = None  # volta a aceitar visita -> não faz sentido guardar motivo antigo

    if "contatoNome" in valores:
        cliente.contato_nome = valores["contatoNome"]
    if "contatoCelular" in valores:
        cliente.contato_celular = valores["contatoCelular"]
    if "status" in valores:
        cliente.status = valores["status"]
    if "aceitaVisita" in valores or "motivoRecusaVisita" in valores:
        cliente.aceita_visita = aceita_final
        cliente.motivo_recusa_visita = motivo_final
    return cliente
