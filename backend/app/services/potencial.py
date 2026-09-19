"""Nota de potencial ouro (0 a 100) — quão bom candidato a virar cliente ouro.

É uma REGRA EXPLICÁVEL, não um modelo: cada parte tem pontos fixos e a tela mostra
como a nota foi montada. Os pesos são um primeiro palpite (não validado) e devem
ser ajustados depois de algumas visitas. Não usa distância da loja: ela mede
conveniência de balcão, e o objetivo aqui é venda externa.

Partes (soma 100 para quem já comprou):

    ramo             até 35   ramos onde já temos ouro (alta 35, média 22)
    estrutura        até 25   tem cara de ter comprador, e não dono fazendo o serviço
    capital social   até 20   tamanho da oportunidade
    histórico        até 10   já comprou antes, quantas vezes (relação existente)
    reativação       até 10   RECÊNCIA AO CONTRÁRIO: quem já comprou e PAROU de vir
                              vale mais — o objetivo é trazer de volta quem sumiu

Empresa que nunca comprou (prospecto ou cliente novo) não tem histórico nem
recência: as três primeiras partes valem 80 e a nota é reescalada para 0–100.
Cliente ouro não tem nota — já é ouro.
"""
from __future__ import annotations

from sqlalchemy import case, func

from .ramos import TIPO_EMPRESA

RAMOS_ALTA = (
    "Manutenção / montagem industrial",
    "Metalurgia / serralheria / esquadrias",
    "Construção civil / obras",
)
RAMOS_MEDIA = (
    "Varejo de ferragens / construção / elétrico",
    "Móveis / madeira",
    "Oficina / serviço de veículos",
    "Elétrica (instalação/manutenção)",
    "Fabricação de máquinas / equipamentos",
)
PTS_RAMO_ALTA, PTS_RAMO_MEDIA = 35, 22

# Portes que indicam empresa maior que micro (a lista usa "Demais"; a carteira, "Média"…)
PORTES_ACIMA_DE_MICRO = ("Pequena", "Média", "Média/Grande", "Grande", "Demais")
CAPITAL_ESTRUTURA = 50_000          # capital que conta como sinal de estrutura
PTS_ESTRUTURA = {"alta": 25, "media": 12, "baixa": 0}

MAXIMO_SEM_HISTORICO = 80           # ramo 35 + estrutura 25 + capital 20


def pontos_ramo(ramo: str | None) -> int:
    if ramo in RAMOS_ALTA:
        return PTS_RAMO_ALTA
    if ramo in RAMOS_MEDIA:
        return PTS_RAMO_MEDIA
    return 0


def nivel_estrutura(tipo: str | None, capital: float | None, porte: str | None) -> str:
    """alta | media | baixa, por três sinais: é empresa (não MEI/autônomo), tem
    capital de estrutura, é maior que micro. Não enxerga sócios nem funcionários —
    nenhuma base pública informa isso; a checagem final é do vendedor."""
    sinais = (
        (tipo == TIPO_EMPRESA)
        + (capital is not None and capital >= CAPITAL_ESTRUTURA)
        + (porte in PORTES_ACIMA_DE_MICRO)
    )
    return "alta" if sinais >= 2 else "media" if sinais == 1 else "baixa"


def pontos_capital(capital: float | None) -> int:
    if capital is None:
        return 8  # sem dado: neutro, nem premia nem pune
    return 20 if capital >= 100_000 else 13 if capital >= 30_000 else 7


def pontos_historico(compras: int | None) -> int:
    if not compras:
        return 0
    return 10 if compras >= 10 else 7 if compras >= 4 else 4 if compras >= 2 else 2


def pontos_reativacao(recencia_dias: int | None) -> int:
    """Quanto mais tempo sem comprar (tendo comprado antes), mais vale reativar.
    Passado de 2 anos cai um pouco: a chance de a empresa já ter fechado sobe."""
    if recencia_dias is None:
        return 0
    if recencia_dias <= 60:
        return 2       # está comprando bem — não é o alvo
    if recencia_dias <= 180:
        return 6
    if recencia_dias <= 730:
        return 10      # sumiu há meses: o alvo principal
    return 7


def calcular_nota(
    *, ramo: str | None, tipo: str | None, capital: float | None, porte: str | None,
    compras: int | None = None, recencia_dias: int | None = None,
) -> tuple[int, dict[str, int]]:
    """Devolve (nota 0–100, partes). `partes` alimenta a explicação na tela."""
    partes = {
        "ramo": pontos_ramo(ramo),
        "estrutura": PTS_ESTRUTURA[nivel_estrutura(tipo, capital, porte)],
        "capital": pontos_capital(capital),
    }
    tem_historico = bool(compras)
    if tem_historico:
        partes["historico"] = pontos_historico(compras)
        partes["reativacao"] = pontos_reativacao(recencia_dias)
        return sum(partes.values()), partes
    # arredonda a metade para CIMA (não o "round" do Python, que vai para o par): é a
    # mesma regra do SQL abaixo, senão a mesma empresa teria duas notas
    return int(sum(partes.values()) * 100 / MAXIMO_SEM_HISTORICO + 0.5), partes


def descricao_das_partes(partes: dict[str, int]) -> str:
    rotulos = {"ramo": "Ramo", "estrutura": "Estrutura", "capital": "Capital",
               "historico": "Histórico", "reativacao": "Reativação"}
    return " · ".join(f"{rotulos[k]} {v}" for k, v in partes.items())


def nota_de_cliente(c) -> tuple[int, dict[str, int]] | None:
    """Nota de um Cliente do banco. None para quem já é ouro ou está inativo."""
    from ..models import StatusCliente
    from .ramos import classificar_tipo, ramo_por_descricao

    if c.faixa == "Ouro" or c.status == StatusCliente.INATIVO:
        return None
    ramo = c.ramo or ramo_por_descricao(c.cnae)
    return calcular_nota(
        ramo=ramo, tipo=classificar_tipo(c.nome), capital=c.capital_social, porte=c.porte,
        compras=c.no_compras, recencia_dias=c.recencia_dias,
    )


# ------------------------------------------------------------------ versão SQL (prospectos)

def nota_sql(Prospecto):
    """A mesma nota de um prospecto, como expressão SQL: assim dá para ordenar e
    filtrar por ela no banco (a lista é paginada) e ela nunca fica velha — muda
    junto com os dados e com os pesos acima, sem precisar recalcular nada."""
    ramo = case(
        (Prospecto.ramo.in_(RAMOS_ALTA), PTS_RAMO_ALTA),
        (Prospecto.ramo.in_(RAMOS_MEDIA), PTS_RAMO_MEDIA),
        else_=0,
    )
    sinais = (
        case((Prospecto.tipo == TIPO_EMPRESA, 1), else_=0)
        + case((Prospecto.capital_social >= CAPITAL_ESTRUTURA, 1), else_=0)
        + case((Prospecto.porte.in_(PORTES_ACIMA_DE_MICRO), 1), else_=0)
    )
    estrutura = case(
        (sinais >= 2, PTS_ESTRUTURA["alta"]),
        (sinais == 1, PTS_ESTRUTURA["media"]),
        else_=PTS_ESTRUTURA["baixa"],
    )
    capital = case(
        (Prospecto.capital_social.is_(None), 8),
        (Prospecto.capital_social >= 100_000, 20),
        (Prospecto.capital_social >= 30_000, 13),
        else_=7,
    )
    return func.floor((ramo + estrutura + capital) * 100.0 / MAXIMO_SEM_HISTORICO + 0.5)
