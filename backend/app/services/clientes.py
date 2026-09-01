"""Consultas e conversões de clientes (filtros da listagem + formato de saída)."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import Cliente, OrigemCliente, StatusCliente
from ..schemas import ClienteAtualizar, ClienteCriarManual, ClienteOut


def para_saida(c: Cliente, tem_promessa: bool = False, agenda: dict | None = None) -> ClienteOut:
    """Converte o modelo do banco pro formato que o frontend já consome
    (mesmos nomes de campo do antigo clientes.json)."""
    from .visitas import proxima_visita
    ultima_visita, proxima = proxima_visita(agenda, c.faixa)
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
        ultimaVisita=ultima_visita,
        proximaVisita=proxima,
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


def listar_admin(
    db: Session,
    *,
    busca: str | None = None,
    faixa: str | None = None,
    cidade: str | None = None,
    origem: str | None = None,
    status: str | None = None,      # ativo | inativo | todos
    aceita_visita: bool | None = None,
    sem_localizacao: bool = False,
    vinculo: str | None = None,     # com | sem
    ordenar: str = "faturamento",
    pagina: int = 1,
    tamanho: int = 50,
) -> tuple[list[Cliente], int]:
    """Listagem de gestão: TUDO é opcional e nada é escondido por padrão.

    Diferente de `listar` (que serve o mapa e a rota, e por isso esconde
    inativo e quem não tem coordenada), aqui o gerente precisa enxergar
    exatamente o que existe na base — inclusive o que está quebrado, que é o
    que ele veio consertar.

    Devolve (página, total) — a contagem é separada porque a carteira tem
    milhares de linhas e mandar tudo para o navegador a cada filtro seria
    lento no celular e caro no banco.
    """
    q = db.query(Cliente)

    if status == "ativo":
        q = q.filter(Cliente.status == StatusCliente.ATIVO)
    elif status == "inativo":
        q = q.filter(Cliente.status == StatusCliente.INATIVO)
    # "todos" (ou nada) não filtra — é como se acha o que foi inativado

    if busca:
        padrao = f"%{busca.strip()}%"
        q = q.filter(or_(
            Cliente.nome.ilike(padrao),
            Cliente.cnpj.ilike(padrao),
            Cliente.cidade.ilike(padrao),
        ))
    if faixa:
        q = q.filter(Cliente.faixa == faixa)
    if cidade:
        q = q.filter(Cliente.cidade == cidade)
    if origem:
        q = q.filter(Cliente.origem == origem)
    if aceita_visita is not None:
        q = q.filter(Cliente.aceita_visita.is_(aceita_visita))
    if sem_localizacao:
        # quem não tem coordenada não aparece no mapa nem entra em rota:
        # é a fila de trabalho de quem precisa marcar o pino
        q = q.filter(or_(Cliente.lat.is_(None), Cliente.lng.is_(None)))
    if vinculo == "com":
        q = q.filter(Cliente.cliente_mestre_id.isnot(None))
    elif vinculo == "sem":
        q = q.filter(Cliente.cliente_mestre_id.is_(None))

    total = q.count()

    ordenacoes = {
        "faturamento": Cliente.fat_total.desc().nullslast(),
        "nome": Cliente.nome.asc(),
        "recencia": Cliente.recencia_dias.asc().nullslast(),
        "atualizacao": Cliente.atualizado_em.desc(),
    }
    q = q.order_by(ordenacoes.get(ordenar, ordenacoes["faturamento"]))

    registros = q.offset((pagina - 1) * tamanho).limit(tamanho).all()
    return registros, total


def alterar_status_em_lote(db: Session, cliente_ids: list[int], status: StatusCliente) -> int:
    """Inativa/reativa vários clientes de uma vez.

    Em lote porque o servidor fica nos EUA e o banco no Brasil: uma chamada
    por cliente faria o gerente esperar ~330ms vezes o número de linhas
    selecionadas — inviável para limpar a lista, que é justamente o caso de
    uso. Não dá commit.
    """
    if not cliente_ids:
        return 0
    registros = db.query(Cliente).filter(Cliente.id.in_(cliente_ids)).all()
    for cliente in registros:
        cliente.status = status
    return len(registros)
