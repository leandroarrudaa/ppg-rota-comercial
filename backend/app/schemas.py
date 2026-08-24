"""Schemas Pydantic (entrada/saída da API)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from .models import MotivoRecusaVisita, OrigemCliente, PapelUsuario, StatusCliente, StatusVisita


# ----------------------------------------------------------- Auth

class LoginBody(BaseModel):
    usuario: str
    senha: str


class SetupBody(BaseModel):
    """Criação do primeiro usuário (admin), quando o banco ainda não tem ninguém."""
    nome: str
    usuario: str
    senha: str = Field(min_length=4)


class UsuarioCriar(BaseModel):
    nome: str
    usuario: str
    senha: str = Field(min_length=4)
    papel: PapelUsuario = PapelUsuario.VENDEDOR


class UsuarioOut(BaseModel):
    id: int
    nome: str
    usuario: str
    papel: PapelUsuario

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    token: str
    usuario: UsuarioOut


# ----------------------------------------------------------- Clientes

class ClienteOut(BaseModel):
    """Saída no MESMO formato do antigo clientes.json — o frontend existente
    (MapaView, PlanoView, etc.) consome esses nomes de campo sem alteração."""
    id: int
    cnpj: str | None = None
    nome: str
    endereco: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    lat: float | None = None
    lng: float | None = None
    geo: str | None = None
    origem: OrigemCliente
    faixa: str | None = None
    emRisco: bool = False
    fat: float | None = None
    compras: int | None = None
    ticket: float | None = None
    recencia: int | None = None
    cadencia: int | None = None
    ultimaCompra: str | None = None
    porte: str | None = None
    capital: float | None = None
    cnae: str | None = None
    telefone: str | None = None
    email: str | None = None
    R: int | None = None
    F: int | None = None
    M: int | None = None
    score: int | None = None
    # Campos novos do app
    status: StatusCliente
    aceitaVisita: bool = True
    motivoRecusaVisita: MotivoRecusaVisita | None = None
    contatoNome: str | None = None
    contatoCelular: str | None = None
    clienteMestreId: int | None = None
    temPromessaPendente: bool = False


class HistoricoItemOut(BaseModel):
    codigoProduto: str
    descricaoProduto: str
    quantidadeTotal: float
    valorTotal: float
    numeroCompras: int
    ultimaCompra: date | None = None


class ClienteCriarManual(BaseModel):
    """Cadastro de lead em campo: endereço é texto livre (sem geocodificação),
    a localização vem do pin que o usuário marca no mapa."""
    nome: str = Field(min_length=1)
    lat: float
    lng: float
    endereco: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    cnpj: str | None = None
    contatoNome: str | None = None
    contatoCelular: str | None = None


class ClienteAtualizar(BaseModel):
    """Campos editáveis pela interface (contato + status). Todos opcionais —
    o PATCH só toca no que for enviado."""
    contatoNome: str | None = None
    contatoCelular: str | None = None
    status: StatusCliente | None = None
    aceitaVisita: bool | None = None
    motivoRecusaVisita: MotivoRecusaVisita | None = None


class HistoricoItensPagina(BaseModel):
    total: int
    pagina: int
    tamanho: int
    itens: list[HistoricoItemOut]


# ----------------------------------------------------------- Visitas / promessas

class PromessaOut(BaseModel):
    id: int
    clienteId: int
    texto: str
    cumprida: bool
    cumpridaEm: datetime | None = None
    criadoEm: datetime

    model_config = {"from_attributes": True}


class VisitaAbrir(BaseModel):
    clienteId: int


class VisitaOut(BaseModel):
    id: int
    clienteId: int
    vendedorId: int
    inicio: datetime
    fim: datetime | None = None
    status: StatusVisita
    observacao: str | None = None
    retornoDias: int | None = None
    retornoData: date | None = None
    criadoEm: datetime
    promessas: list[PromessaOut] = []


class RelatorioVisita(BaseModel):
    """Corpo do relatório bloqueante, preenchido ao fechar a visita."""
    observacao: str = Field(min_length=1)
    retornoDias: int | None = None
    promessas: list[str] = []
    # ajustes de status feitos durante a própria visita (opcional)
    status: StatusCliente | None = None
    aceitaVisita: bool | None = None
    motivoRecusaVisita: MotivoRecusaVisita | None = None


# ----------------------------------------------------------- Vínculo de CNPJ

class ClienteResumo(BaseModel):
    id: int
    nome: str
    cnpj: str | None = None
    cidade: str | None = None
    endereco: str | None = None
    faixa: str | None = None
    fat: float | None = None


class SugestaoVinculoOut(BaseModel):
    id: int
    clienteA: ClienteResumo
    clienteB: ClienteResumo
    motivo: str
    score: float


class ResolverSugestao(BaseModel):
    aceitar: bool


class VinculoManualCriar(BaseModel):
    clienteIds: list[int] = Field(min_length=2)


class ClienteMestreOut(BaseModel):
    id: int
    nomePreferido: str
    membros: list[ClienteResumo]
    fatTotal: float
    noCompras: int
    faixa: str | None = None


# ----------------------------------------------------------- Ficha (resposta única)

class FichaClienteOut(BaseModel):
    """Tudo que a ficha do cliente precisa, numa resposta só.

    Antes a tela disparava 4 ou 5 requisições ao abrir — duas delas em série,
    porque o vínculo só era pedido depois que o cliente chegava. Com o servidor
    nos EUA e o banco em São Paulo, cada ida e volta custa ~350ms, e a ficha
    levava segundos para montar. `vinculo` só vem preenchido para admin,
    preservando o comportamento anterior.
    """
    cliente: ClienteOut
    promessas: list[PromessaOut] = []
    visitas: list[VisitaOut] = []
    historico: HistoricoItensPagina
    vinculo: ClienteMestreOut | None = None


# ----------------------------------------------------------- Relatórios

class VisitaRelatorioItem(BaseModel):
    """Uma visita finalizada, com nome do cliente e do vendedor já embutidos —
    a tela de Relatórios não precisa de uma requisição por cliente."""
    id: int
    clienteId: int
    clienteNome: str
    clienteCidade: str | None = None
    vendedorId: int
    vendedorNome: str
    inicio: datetime
    fim: datetime | None = None
    duracaoMin: int | None = None
    observacao: str | None = None
    retornoDias: int | None = None
    retornoData: date | None = None
    promessas: list[PromessaOut] = []


class RelatorioResumo(BaseModel):
    totalVisitas: int
    clientesUnicos: int
    duracaoMediaMin: int | None = None
    promessasFeitas: int
    retornosAgendados: int


class RelatorioVisitasOut(BaseModel):
    resumo: RelatorioResumo
    visitas: list[VisitaRelatorioItem]
