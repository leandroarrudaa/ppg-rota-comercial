"""Ajustes do negócio configuráveis pelo Admin, sem precisar de deploy.

Cada opção é declarada aqui uma vez (tipo, padrão e explicação em português) e
a tela é montada a partir dessa declaração — assim não há como o backend
aceitar uma chave que a tela não sabe explicar, nem a tela mostrar uma opção
que o backend ignora.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Cliente, Configuracao

FATURAMENTO_MINIMO_RISCO = "faturamento_minimo_risco"


@dataclass(frozen=True)
class Opcao:
    chave: str
    rotulo: str
    ajuda: str
    padrao: float
    minimo: float = 0
    maximo: float | None = None


# Padrão 0 = comportamento de antes (só o quintil decide). Assim ligar a
# funcionalidade não muda nada sozinho — quem muda é o gerente, de propósito.
OPCOES: dict[str, Opcao] = {
    FATURAMENTO_MINIMO_RISCO: Opcao(
        chave=FATURAMENTO_MINIMO_RISCO,
        rotulo="Faturamento mínimo para alerta de risco",
        ajuda=(
            "O alerta 'conta grande parada — reativar já' só aparece para cliente "
            "que já faturou pelo menos este valor no histórico. Sem esse piso, o "
            "alerta é decidido só pela posição relativa na carteira e acaba "
            "marcando cliente pequeno, o que tira a força do aviso. Use 0 para "
            "desligar o piso."
        ),
        padrao=0,
        minimo=0,
        maximo=1_000_000,
    ),
}


def _opcao(chave: str) -> Opcao:
    opcao = OPCOES.get(chave)
    if opcao is None:
        raise HTTPException(status_code=404, detail="Essa configuração não existe.")
    return opcao


def obter_numero(db: Session, chave: str) -> float:
    """Valor da opção, ou o padrão dela se nunca foi definida.

    Valor ilegível no banco cai no padrão em vez de derrubar a requisição —
    uma configuração corrompida não pode tirar o app do ar em campo.
    """
    opcao = _opcao(chave)
    registro = db.get(Configuracao, chave)
    if registro is None:
        return opcao.padrao
    try:
        return float(registro.valor)
    except (TypeError, ValueError):
        return opcao.padrao


def definir_numero(db: Session, chave: str, valor: float) -> float:
    """Grava o valor depois de validar contra os limites declarados."""
    opcao = _opcao(chave)
    if valor < opcao.minimo or (opcao.maximo is not None and valor > opcao.maximo):
        limite = f"entre {opcao.minimo:,.0f} e {opcao.maximo:,.0f}".replace(",", ".")
        raise HTTPException(status_code=400, detail=f"Informe um valor {limite}.")

    registro = db.get(Configuracao, chave)
    if registro is None:
        db.add(Configuracao(chave=chave, valor=str(valor)))
    else:
        registro.valor = str(valor)
    return valor


def listar(db: Session) -> list[dict]:
    """Opções com o valor atual — é o que a tela de configurações desenha."""
    return [
        {
            "chave": o.chave,
            "rotulo": o.rotulo,
            "ajuda": o.ajuda,
            "valor": obter_numero(db, o.chave),
            "padrao": o.padrao,
            "minimo": o.minimo,
            "maximo": o.maximo,
        }
        for o in OPCOES.values()
    ]


def reavaliar_risco(db: Session, faturamento_minimo: float) -> dict:
    """Reaplica o piso de faturamento sobre a marcação de risco já gravada.

    `em_risco` é coluna persistida (calculada na importação), não expressão de
    consulta — mudar o piso precisa reescrever a marcação. É um UPDATE em cima
    de duas colunas indexadas, bem mais barato que recalcular na leitura de
    toda tela, que pagaria a latência do banco a cada abertura.

    O quintil continua mandando em quem PODE ser risco; o piso só remove quem
    é pequeno demais para merecer uma visita de reativação. Por isso a
    condição usa `m >= 4` — a mesma do cálculo de RFM.
    """
    marcados = removidos = 0
    for cliente in db.query(Cliente).filter((Cliente.m >= 4) | Cliente.em_risco.is_(True)).all():
        grande = (cliente.fat_total or 0) >= faturamento_minimo
        # Reproduz a regra do RFM: conta de valor alto (M>=4) com recência
        # ruim (R<=2). Sem R/M calculados ainda, não há como afirmar risco.
        deveria = bool(
            cliente.m is not None and cliente.r is not None
            and cliente.m >= 4 and cliente.r <= 2 and grande
        )
        if deveria and not cliente.em_risco:
            cliente.em_risco = True
            marcados += 1
        elif not deveria and cliente.em_risco:
            cliente.em_risco = False
            removidos += 1
    return {"marcados": marcados, "removidos": removidos}
