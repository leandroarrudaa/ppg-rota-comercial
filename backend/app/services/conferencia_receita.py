"""Conferência dos prospectos na Receita (BrasilAPI): a empresa ainda existe?

A lista importada traz "ATIVA" para todo mundo, mas é uma foto antiga — muita
empresa já fechou. Aqui cada CNPJ é consultado e a situação real fica gravada;
quem não está ativa sai da lista por padrão (ver prospeccao._base).

Roda em lotes com orçamento de tempo, do mesmo jeito que a busca de CNAE dos
clientes (ver enriquecimento.py): é uma chamada HTTP por CNPJ, e a tela chama de
novo até não sobrar ninguém — não dá para fazer tudo numa chamada só sem
estourar o timeout do navegador (TIMEOUT_MS em lib/api.js).
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from sqlalchemy.orm import Session

from ..models import Prospecto

URL_BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1/{}"
TIMEOUT_REQUISICAO = 15
ORCAMENTO_SEGUNDOS = 12   # some da conta bem antes do timeout do frontend (20s)
PARALELO = 3              # poucas consultas juntas: é uma API pública e gratuita
PAUSA_ENTRE_ONDAS = 0.3
UA = {"User-Agent": "ppg-rota-comercial/1.0"}

NAO_ENCONTRADO = "NAO_ENCONTRADO"


class LimiteDeUso(Exception):
    """A BrasilAPI pediu para esperar (HTTP 429)."""


def _consultar(cnpj: str) -> dict | None:
    """Situação e sócios de um CNPJ.

    None = não deu para saber agora (rede fora, API instável) — quem chama NÃO
    marca a empresa como conferida, para tentar de novo depois. Marcar como
    "não existe" por causa de uma falha de rede esconderia empresa boa.
    """
    try:
        r = requests.get(URL_BRASILAPI.format(cnpj), headers=UA, timeout=TIMEOUT_REQUISICAO)
    except requests.RequestException:
        return None
    # 404 = a Receita não conhece; 400 = CNPJ com dígito verificador inválido
    # (número que não existe). Nos dois casos a empresa não existe — sem isto,
    # o CNPJ inválido ficaria pendente para sempre, tentando de novo a cada lote.
    if r.status_code in (400, 404):
        return {"situacao": NAO_ENCONTRADO, "socios": ""}
    if r.status_code == 429:
        raise LimiteDeUso()
    if r.status_code != 200:
        return None
    dados = r.json()
    situacao = (dados.get("descricao_situacao_cadastral") or "").strip().upper()
    if not situacao:
        return None
    socios = [(s.get("nome_socio") or "").strip() for s in (dados.get("qsa") or [])]
    return {"situacao": situacao, "socios": "; ".join(s for s in socios if s)[:300]}


def conferir_lote(db: Session, pendentes: list[Prospecto]) -> dict:
    """Consulta a Receita para os prospectos recebidos, dentro do orçamento de
    tempo. Não dá commit: quem chama decide."""
    inicio = time.monotonic()
    processados = ativas = nao_ativas = falhas = 0
    limite_de_uso = False

    for i in range(0, len(pendentes), PARALELO):
        if time.monotonic() - inicio > ORCAMENTO_SEGUNDOS:
            break
        onda = pendentes[i:i + PARALELO]
        try:
            with ThreadPoolExecutor(max_workers=PARALELO) as pool:
                respostas = list(pool.map(lambda p: _consultar(p.cnpj), onda))
        except LimiteDeUso:
            limite_de_uso = True
            break

        for prospecto, resposta in zip(onda, respostas):
            if resposta is None:
                falhas += 1
                continue
            prospecto.situacao_receita = resposta["situacao"]
            prospecto.socios = resposta["socios"] or None
            prospecto.verificado_em = datetime.utcnow()
            processados += 1
            if resposta["situacao"] == "ATIVA":
                ativas += 1
            else:
                nao_ativas += 1
        time.sleep(PAUSA_ENTRE_ONDAS)

    return {
        "processados": processados,
        "ativas": ativas,
        "naoAtivas": nao_ativas,
        "falhas": falhas,
        "limiteDeUso": limite_de_uso,
    }
