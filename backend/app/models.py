"""Modelos do banco de dados (tabelas) da plataforma de representação comercial."""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class PapelUsuario(str, enum.Enum):
    """Perfil de acesso. ADMIN = tudo (cria contas, vínculos, importação);
    VENDEDOR = fluxo de campo (visitas, relatórios)."""
    ADMIN = "admin"
    VENDEDOR = "vendedor"


class Usuario(Base):
    """Usuário do app (login)."""
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    usuario: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[PapelUsuario] = mapped_column(Enum(PapelUsuario), default=PapelUsuario.VENDEDOR)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StatusCliente(str, enum.Enum):
    """Estado do cliente. INATIVO = empresa fechou; some das listas por padrão."""
    ATIVO = "ativo"
    INATIVO = "inativo"


class MotivoRecusaVisita(str, enum.Enum):
    """Por que o cliente não recebe visita presencial (continua ativo no RFM).
    CALOTE = não vende mais fiado, mas ainda compra à vista.
    SEM_VISITA = compra por telefone, não quer/não pode receber visita."""
    CALOTE = "calote"
    SEM_VISITA = "sem-visita"


class OrigemCliente(str, enum.Enum):
    """ANTIGO = carteira com histórico de compra (RFM real).
    NOVO = lead importado por planilha ou cadastrado manualmente."""
    ANTIGO = "antigo"
    NOVO = "novo"


class Cliente(Base):
    """Cliente da carteira (fonte de verdade — substitui o clientes.json estático).

    Campos de RFM/faturamento são preenchidos pelo pipeline de importação e só
    existem para origem=ANTIGO; leads (origem=NOVO) ficam com eles nulos.
    Campos "donos do app" (status, aceita_visita, contato_*) nunca são
    sobrescritos pela reimportação da carteira.
    """
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: lead cadastrado manualmente pode não ter CNPJ ainda.
    # Unicidade (quando presente) é validada em código, não por constraint,
    # porque UNIQUE em coluna nullable trata NULLs como distintos só em alguns bancos.
    cnpj: Mapped[str | None] = mapped_column(String(20), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    endereco: Mapped[str | None] = mapped_column(String(300))
    bairro: Mapped[str | None] = mapped_column(String(100))
    cep: Mapped[str | None] = mapped_column(String(12))
    cidade: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(String(2))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    # preciso | cep | cidade | manual (pin no mapa) | falhou
    geo_status: Mapped[str | None] = mapped_column(String(20))

    origem: Mapped[OrigemCliente] = mapped_column(Enum(OrigemCliente), default=OrigemCliente.ANTIGO)

    # ------- RFM / financeiro (pipeline; nulos para leads) -------
    faixa: Mapped[str | None] = mapped_column(String(10))  # Ouro | Prata | Bronze
    em_risco: Mapped[bool] = mapped_column(Boolean, default=False)
    fat_total: Mapped[float | None] = mapped_column(Float)
    no_compras: Mapped[int | None] = mapped_column(Integer)
    ticket_medio: Mapped[float | None] = mapped_column(Float)
    recencia_dias: Mapped[int | None] = mapped_column(Integer)
    cadencia_dias: Mapped[int | None] = mapped_column(Integer)
    primeira_compra: Mapped[date | None] = mapped_column(Date)
    ultima_compra: Mapped[date | None] = mapped_column(Date)
    r: Mapped[int | None] = mapped_column(Integer)
    f: Mapped[int | None] = mapped_column(Integer)
    m: Mapped[int | None] = mapped_column(Integer)
    rfm_score: Mapped[int | None] = mapped_column(Integer)

    # ------- Enriquecimento por CNPJ (BrasilAPI) -------
    porte: Mapped[str | None] = mapped_column(String(20))
    capital_social: Mapped[float | None] = mapped_column(Float)
    cnae: Mapped[str | None] = mapped_column(String(200))
    telefone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(120))

    # ------- Campos donos do app (nunca sobrescritos na reimportação) -------
    status: Mapped[StatusCliente] = mapped_column(Enum(StatusCliente), default=StatusCliente.ATIVO)
    aceita_visita: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo_recusa_visita: Mapped[MotivoRecusaVisita | None] = mapped_column(Enum(MotivoRecusaVisita))
    contato_nome: Mapped[str | None] = mapped_column(String(100))
    contato_celular: Mapped[str | None] = mapped_column(String(30))

    # Vínculo: aponta pro "cliente mestre" quando esse CNPJ foi agrupado com
    # outro(s) (empresa trocou de CNPJ, ou múltiplos CNPJs no mesmo endereço).
    cliente_mestre_id: Mapped[int | None] = mapped_column(ForeignKey("clientes_mestre.id"), index=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Índices das colunas que a listagem filtra. O caso mais comum, de longe, é
    # a Rota do Dia pedindo "quem está visível no mapa e pode receber visita" —
    # daí o índice composto de status + aceita_visita + coordenadas.
    __table_args__ = (
        Index("ix_clientes_listagem", "status", "aceita_visita", "lat", "lng"),
        Index("ix_clientes_cidade", "cidade"),
        Index("ix_clientes_faixa", "faixa"),
    )


class HistoricoItemCliente(Base):
    """Extrato do histórico de compra por produto, sincronizado do banco_mestre.db.

    Agregado por (cnpj, produto) — não por linha de nota — para reduzir volume.
    Alimentado pelo script sync_historico_itens.py, rodado manualmente quando o
    banco mestre é regenerado.
    """
    __tablename__ = "historico_itens_cliente"

    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj_normalizado: Mapped[str] = mapped_column(String(14), index=True)
    codigo_produto: Mapped[str] = mapped_column(String(60))
    descricao_produto: Mapped[str] = mapped_column(Text)
    quantidade_total: Mapped[float] = mapped_column(Float, default=0)
    valor_total: Mapped[float] = mapped_column(Float, default=0)
    numero_compras: Mapped[int] = mapped_column(Integer, default=0)
    ultima_compra: Mapped[date | None] = mapped_column(Date)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("cnpj_normalizado", "codigo_produto", name="uq_historico_cnpj_produto"),
    )


class StatusVisita(str, enum.Enum):
    """ABERTA = em andamento. AGUARDANDO_RELATORIO = terminou (timestamp fim
    já gravado) mas o relatório bloqueante ainda não foi preenchido/salvo.
    FINALIZADA = relatório salvo, visita concluída."""
    ABERTA = "aberta"
    AGUARDANDO_RELATORIO = "aguardando_relatorio"
    FINALIZADA = "finalizada"


class Visita(Base):
    """Uma visita presencial a um cliente. O fluxo é bloqueante: entre
    'finalizar' (grava fim) e o relatório salvo, o vendedor não pode abrir
    outra visita — reforçado pelo backend (ver services/visitas.py) e pelo
    modal bloqueante do frontend."""
    __tablename__ = "visitas"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    vendedor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    inicio: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    fim: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[StatusVisita] = mapped_column(Enum(StatusVisita), default=StatusVisita.ABERTA)

    # relatório (preenchido só no fechamento)
    observacao: Mapped[str | None] = mapped_column(Text)
    # dias combinados até a próxima visita — sobrepõe a cadência estatística
    # inferida do histórico de compra quando presente (ver lib/recomendacao.js)
    retorno_dias: Mapped[int | None] = mapped_column(Integer)
    retorno_data: Mapped[date | None] = mapped_column(Date)

    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    promessas: Mapped[list["Promessa"]] = relationship(back_populates="visita_origem")
    # Só leitura (sem back_populates): usadas pela tela de Relatórios para
    # trazer nome do cliente e do vendedor sem uma consulta por visita.
    cliente: Mapped["Cliente"] = relationship()
    vendedor: Mapped["Usuario"] = relationship()

    # Índice pensado pra tela de Relatórios: filtra por vendedor + status
    # (só FINALIZADA) + período de datas — a mesma combinação que
    # cliente_ids_visitados_hoje já usa pro riscado da Rota do Dia.
    __table_args__ = (
        Index("ix_visitas_vendedor_status_inicio", "vendedor_id", "status", "inicio"),
    )


class Promessa(Base):
    """Compromisso feito numa visita (ex.: levar amostra). Fica pendente até
    ser marcada como cumprida — aparece destacada na próxima vez que a ficha
    do cliente for aberta."""
    __tablename__ = "promessas"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    visita_origem_id: Mapped[int | None] = mapped_column(ForeignKey("visitas.id"))
    texto: Mapped[str] = mapped_column(Text)
    cumprida: Mapped[bool] = mapped_column(Boolean, default=False)
    cumprida_em: Mapped[datetime | None] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    visita_origem: Mapped["Visita | None"] = relationship(back_populates="promessas")


class StatusSugestaoVinculo(str, enum.Enum):
    PENDENTE = "pendente"
    ACEITO = "aceito"
    RECUSADO = "recusado"


class ClienteMestre(Base):
    """'Cliente mestre': agrupa N CNPJs da mesma empresa (trocou de CNPJ, ou
    tem mais de um no mesmo endereço). RFM/faturamento consolidado é
    CALCULADO na hora (soma dos membros via Cliente.cliente_mestre_id), nunca
    persistido aqui — evita dessincronizar quando a carteira é reimportada."""
    __tablename__ = "clientes_mestre"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome_preferido: Mapped[str] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SugestaoVinculo(Base):
    """Candidato a vínculo gerado automaticamente (nome parecido / mesmo
    CEP-endereço). Fica pendente até o Admin aceitar ou recusar — recusar não
    faz a sugestão reaparecer numa próxima geração."""
    __tablename__ = "sugestoes_vinculo"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_a_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    cliente_b_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"), index=True)
    motivo: Mapped[str] = mapped_column(String(50))  # "nome parecido" | "mesmo CEP" | "mesmo endereço"
    score: Mapped[float] = mapped_column(Float)
    status: Mapped[StatusSugestaoVinculo] = mapped_column(
        Enum(StatusSugestaoVinculo), default=StatusSugestaoVinculo.PENDENTE
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("cliente_a_id", "cliente_b_id", name="uq_sugestao_par"),
    )


class Configuracao(Base):
    """Ajustes do negócio que o Admin muda pela tela, sem depender de deploy.

    Guardado como texto chave/valor de propósito: são poucas opções, mudam
    raramente e cada uma tem um jeito próprio de ser lida (ver
    services/configuracoes.py). Uma coluna por opção obrigaria migração de
    banco a cada ajuste novo.
    """
    __tablename__ = "configuracoes"

    chave: Mapped[str] = mapped_column(String(50), primary_key=True)
    valor: Mapped[str] = mapped_column(String(200))
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class MapaCodigoErp(Base):
    """De-para do código interno do ERP para o CNPJ do cliente.

    Existe porque o relatório diário de vendas identifica o cliente só por
    "729 - RAZÃO SOCIAL" — não há CNPJ em lugar nenhum dele, e casar por nome
    acerta 13% dos casos. O mapa vem do cadastro de clientes do banco mestre e
    é o que torna o relatório aproveitável.

    Códigos de pessoa física e de balcão não entram: não são carteira.
    """
    __tablename__ = "mapa_codigo_erp"

    codigo: Mapped[str] = mapped_column(String(20), primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(14), index=True)
    nome: Mapped[str | None] = mapped_column(String(200))
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PedidoImportado(Base):
    """Pedido de venda já contabilizado, para não somar duas vezes.

    A importação diária é incremental — ela ACRESCENTA ao acumulado do cliente.
    Sem esta tabela, reenviar o arquivo do mesmo mês (que vai acontecer:
    "será que subiu mesmo?") dobraria o faturamento de todo mundo. O número do
    pedido é único e sequencial no ERP, então serve de chave natural.
    """
    __tablename__ = "pedidos_importados"

    numero_pedido: Mapped[str] = mapped_column(String(20), primary_key=True)
    cnpj: Mapped[str | None] = mapped_column(String(14), index=True)
    data_pedido: Mapped[date | None] = mapped_column(Date)
    valor: Mapped[float] = mapped_column(Float, default=0)
    importado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ImportacaoCarteira(Base):
    """Histórico de importações — quem subiu o quê, quando e com que efeito.

    Serve para responder "o Raphael subiu a planilha ontem?" sem precisar
    procurar no banco linha por linha.
    """
    __tablename__ = "importacoes_carteira"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))  # relatorio-vendas | banco-mestre
    arquivo: Mapped[str | None] = mapped_column(String(255))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    resumo: Mapped[str | None] = mapped_column(Text)  # JSON com as contagens
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    usuario: Mapped["Usuario | None"] = relationship()
