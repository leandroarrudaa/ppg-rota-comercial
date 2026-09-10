"""Busca o ramo de atividade (CNAE) de clientes que nunca tiveram essa
informação, consultando a BrasilAPI pelo CNPJ — mesma fonte usada no
enriquecimento original da carteira (ver scripts/04_enriquecer_cnpj.py, hoje
fora de uso porque rodava fora do servidor, sobre um CSV solto).

Roda em lotes pequenos, com orçamento de tempo: é uma chamada HTTP por CNPJ, e
o botão que dispara isso na tela de Gestão chama de novo até não sobrar
ninguém — não dá pra fazer tudo numa chamada só sem estourar o timeout do
navegador (ver TIMEOUT_MS em lib/api.js).
"""
from __future__ import annotations

import time

import requests
from sqlalchemy.orm import Session

from ..models import Cliente
from .cnpj import normalizar_cnpj

URL_BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1/{}"
TIMEOUT_REQUISICAO = 15
PAUSA_ENTRE_CHAMADAS = 0.4  # não martela uma API pública gratuita
ORCAMENTO_SEGUNDOS = 12     # some da conta bem antes do timeout do frontend (20s)
UA = {"User-Agent": "ppg-rota-comercial/1.0"}


def _pendentes_query(db: Session):
    """Cliente com CNPJ cadastrado mas cujo CNAE nunca foi buscado.

    ``cnae IS NULL`` é "nunca tentamos"; string vazia ("") é "tentamos e não
    achamos" (CNPJ inválido/baixado, ou a API não respondeu) — controla que a
    fila não fica repetindo pra sempre quem não tem resposta.
    """
    return (
        db.query(Cliente)
        .filter(Cliente.cnae.is_(None))
        .filter(Cliente.cnpj.isnot(None))
        .filter(Cliente.cnpj != "")
    )


def contar_pendentes(db: Session) -> int:
    return _pendentes_query(db).count()


def _buscar_cnae(cnpj: str) -> str | None:
    """None = não deu pra descobrir agora (CNPJ inválido, baixado, ou a API
    falhou/está fora do ar)."""
    try:
        r = requests.get(URL_BRASILAPI.format(cnpj), headers=UA, timeout=TIMEOUT_REQUISICAO)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return (r.json().get("cnae_fiscal_descricao") or "").strip() or None


def enriquecer_lote(db: Session, limite: int = 80) -> dict:
    """Busca o CNAE de até `limite` clientes pendentes, respeitando um
    orçamento de tempo — o que não coube nesse orçamento fica pra próxima
    chamada. Não dá commit: quem chama decide.

    Nunca sobrescreve um CNAE que já existe — só preenche quem está com
    `None` (o filtro "Todos os ramos" do Plano da Semana já trata "" como
    "sem ramo", então marcar como tentado não muda o que aparece lá).
    """
    pendentes = _pendentes_query(db).order_by(Cliente.id).limit(limite).all()
    inicio = time.monotonic()
    processados = encontrados = nao_encontrados = sem_cnpj_valido = 0

    for cliente in pendentes:
        if time.monotonic() - inicio > ORCAMENTO_SEGUNDOS:
            break
        processados += 1

        cnpj = normalizar_cnpj(cliente.cnpj)
        if len(cnpj) != 14:
            cliente.cnae = ""  # não é CNPJ de verdade — marca como tentado e segue
            sem_cnpj_valido += 1
            continue

        cnae = _buscar_cnae(cnpj)
        cliente.cnae = cnae or ""
        if cnae:
            encontrados += 1
        else:
            nao_encontrados += 1
        time.sleep(PAUSA_ENTRE_CHAMADAS)

    return {
        "processados": processados,
        "encontrados": encontrados,
        "naoEncontrados": nao_encontrados,
        "semCnpjValido": sem_cnpj_valido,
        # a sessão do app roda com autoflush=False (ver database.py) — sem
        # este flush, o SELECT de "quantos restam" não veria as mudanças
        # deste lote ainda não gravadas, e contaria quem acabou de ser
        # processado como se ainda estivesse pendente.
        "restam": _contar_pendentes_apos_flush(db),
    }


def _contar_pendentes_apos_flush(db: Session) -> int:
    db.flush()
    return contar_pendentes(db)
