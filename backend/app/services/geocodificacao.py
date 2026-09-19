"""Localiza no mapa os clientes novos que vieram da Prospecção (Nominatim / OpenStreetMap).

Mesma ideia do script de carga (backend/scripts/importar_clientes_novos_cruzados.py):
tenta a rua com número, depois o CEP, depois só a cidade. O `geo_status` diz quão
bom foi o resultado — "cidade" cai no centro da cidade e por isso fica de fora do
Plano da Semana (ver services/clientes.py).

O Nominatim é gratuito e pede no máximo 1 consulta por segundo; por isso roda em
lotes pequenos com orçamento de tempo, e a tela chama de novo até não sobrar ninguém.
"""
from __future__ import annotations

import re
import time

import requests
from sqlalchemy.orm import Session

from ..models import Cliente, OrigemCliente

URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = {"User-Agent": "ppg-rota-comercial/1.0 (rudderassessoria@gmail.com)"}
TIMEOUT_REQUISICAO = 15
PAUSA_ENTRE_CONSULTAS = 1.1   # regra de uso do Nominatim: 1 por segundo
ORCAMENTO_SEGUNDOS = 12       # some da conta bem antes do timeout do frontend (20s)


def _buscar(parametros: dict) -> tuple[float, float] | None:
    """Uma consulta ao Nominatim. None = não achou (ou o serviço falhou)."""
    try:
        r = requests.get(
            URL_NOMINATIM,
            params={**parametros, "format": "json", "limit": 1, "countrycodes": "br"},
            headers=UA, timeout=TIMEOUT_REQUISICAO,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    achados = r.json()
    if not achados:
        return None
    return float(achados[0]["lat"]), float(achados[0]["lon"])


def _tentativas(cliente: Cliente) -> list[tuple[str, dict]]:
    """Do mais preciso para o menos: (geo_status, parâmetros da consulta)."""
    cep = re.sub(r"\D", "", cliente.cep or "")
    tentativas: list[tuple[str, dict]] = []
    if cliente.endereco and cliente.cidade:
        # o Nominatim quer "número rua" no campo street; o cadastro guarda "RUA X, 89"
        partes = [p.strip() for p in cliente.endereco.rsplit(",", 1)]
        rua, numero = (partes[0], partes[1]) if len(partes) == 2 else (cliente.endereco, "")
        street = f"{numero} {rua}".strip()
        tentativas.append(("preciso", {"street": street, "city": cliente.cidade, "state": cliente.uf or "PR"}))
    if len(cep) == 8:
        tentativas.append(("cep", {"postalcode": f"{cep[:5]}-{cep[5:]}"}))
    if cliente.cidade:
        tentativas.append(("cidade", {"city": cliente.cidade, "state": cliente.uf or "PR"}))
    return tentativas


def localizar(cliente: Cliente) -> str:
    """Preenche lat/lng do cliente e devolve o geo_status (ou "falhou")."""
    for status, parametros in _tentativas(cliente):
        achado = _buscar(parametros)
        time.sleep(PAUSA_ENTRE_CONSULTAS)
        if achado:
            cliente.lat, cliente.lng = achado
            cliente.geo_status = status
            return status
    cliente.geo_status = "falhou"
    return "falhou"


def pendentes(db: Session):
    """Clientes novos que nunca tiveram a localização tentada."""
    return (
        db.query(Cliente)
        .filter(Cliente.origem == OrigemCliente.NOVO)
        .filter(Cliente.geo_status.is_(None))
        .filter(Cliente.lat.is_(None))
    )


def localizar_lote(db: Session) -> dict:
    """Localiza quantos couberem no orçamento de tempo. Não dá commit."""
    inicio = time.monotonic()
    processados = localizados = 0
    for cliente in pendentes(db).order_by(Cliente.id).limit(20).all():
        if time.monotonic() - inicio > ORCAMENTO_SEGUNDOS:
            break
        processados += 1
        if localizar(cliente) != "falhou":
            localizados += 1
    db.flush()  # a sessão roda com autoflush=False: sem isto, "restam" não veria este lote
    return {
        "processados": processados,
        "localizados": localizados,
        "semLocal": processados - localizados,
        "restam": pendentes(db).count(),
    }
