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


_LIMITE = object()  # marca "a Receita pediu para esperar" dentro de uma onda


def _tentar(cnpj: str):
    try:
        return _consultar(cnpj)
    except LimiteDeUso:
        return _LIMITE


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
        with ThreadPoolExecutor(max_workers=PARALELO) as pool:
            respostas = list(pool.map(lambda p: _tentar(p.cnpj), onda))

        for prospecto, resposta in zip(onda, respostas):
            if resposta is _LIMITE:
                limite_de_uso = True   # esta fica para depois; as outras da onda valem
                continue
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
        if limite_de_uso:
            break  # a Receita pediu para esperar: insistir só prolonga o bloqueio
        time.sleep(PAUSA_ENTRE_ONDAS)

    return {
        "processados": processados,
        "ativas": ativas,
        "naoAtivas": nao_ativas,
        "falhas": falhas,
        "limiteDeUso": limite_de_uso,
    }


# ====================================================================================
# Modo automático: confere TUDO em segundo plano, esperando a Receita liberar
# ====================================================================================
#
# A BrasilAPI aceita ~100 consultas por minuto por endereço e depois responde 429
# ("Too Many Requests") por uns 50 a 60 segundos (medido em 20/09/2026). Em vez de o
# usuário clicar de novo a cada bloqueio, o servidor mesmo espera e continua até
# acabar — mesmo com a página fechada. O que já foi conferido fica gravado a cada
# lote; se o servidor reiniciar (publicação nova), é só iniciar de novo e ele
# recomeça de onde parou, porque só consulta quem ainda não foi conferido.

import logging
import threading
from datetime import datetime as _datetime

log = logging.getLogger(__name__)

LOTE_AUTOMATICO = 45
ESPERA_APOS_LIMITE = 60        # segundos: um pouco mais que a janela medida (~50-60 s)
ESPERA_MAXIMA = 180
FALHAS_SEGUIDAS_PARA_DESISTIR = 6   # rede fora / API caída: para em vez de insistir para sempre


class ConferenciaEmSegundoPlano:
    """Uma conferência por vez (é um serviço só, com uma API pública de cota curta).

    `fabrica_sessao` devolve uma sessão de banco nova; `dormir` existe para os testes
    não esperarem de verdade; `em_thread=False` roda tudo na hora (também para testes).
    """

    def __init__(self, fabrica_sessao, dormir=time.sleep, em_thread=True):
        self._fabrica = fabrica_sessao
        self._dormir = dormir
        self._em_thread = em_thread
        self._trava = threading.Lock()
        self._parar = threading.Event()
        self._estado = self._estado_inicial()

    @staticmethod
    def _estado_inicial() -> dict:
        return {
            "rodando": False, "ativas": 0, "naoAtivas": 0, "falhas": 0, "restam": 0,
            "aguardandoAte": None, "esperaSegundos": 0, "iniciadoEm": None, "terminouEm": None,
            "mensagem": "",
        }

    def estado(self) -> dict:
        with self._trava:
            e = dict(self._estado)
        if e["aguardandoAte"] is not None:
            e["faltamSegundos"] = max(0, int(e["aguardandoAte"] - time.time()))
        else:
            e["faltamSegundos"] = 0
        e.pop("aguardandoAte")
        return e

    def _atualizar(self, **campos) -> None:
        with self._trava:
            self._estado.update(campos)

    def iniciar(self, filtros: dict, restam_inicial: int = 0) -> bool:
        """False se já tem uma conferência rodando."""
        with self._trava:
            if self._estado["rodando"]:
                return False
            self._estado = self._estado_inicial()
            self._estado.update(rodando=True, restam=restam_inicial, iniciadoEm=_datetime.utcnow().isoformat())
        self._parar.clear()
        if self._em_thread:
            threading.Thread(target=self._rodar, args=(filtros,), daemon=True, name="conferencia-receita").start()
        else:
            self._rodar(filtros)
        return True

    def parar(self) -> None:
        self._parar.set()

    def _esperar(self, segundos: int) -> None:
        """Espera em pedaços de 1 s, para o Parar valer na hora."""
        self._atualizar(aguardandoAte=time.time() + segundos, esperaSegundos=segundos)  # só para a tela mostrar a contagem
        for _ in range(segundos):
            if self._parar.is_set():
                break
            self._dormir(1)
        self._atualizar(aguardandoAte=None, esperaSegundos=0)

    def _rodar(self, filtros: dict) -> None:
        from . import prospeccao as svc  # aqui dentro: prospeccao também importa este módulo

        espera = ESPERA_APOS_LIMITE
        falhas_seguidas = 0
        mensagem = ""
        try:
            while not self._parar.is_set():
                db = self._fabrica()
                try:
                    pendentes, total = svc.pendentes_de_conferencia(db, limite=LOTE_AUTOMATICO, **filtros)
                    if not pendentes:
                        self._atualizar(restam=0)
                        mensagem = "Conferência terminada."
                        break
                    r = conferir_lote(db, pendentes)
                    db.commit()  # cada lote fica gravado: reiniciar o servidor não perde o que já foi feito
                    restam = svc.pendentes_de_conferencia(db, **filtros)
                finally:
                    db.close()

                with self._trava:
                    self._estado["ativas"] += r["ativas"]
                    self._estado["naoAtivas"] += r["naoAtivas"]
                    self._estado["falhas"] += r["falhas"]
                    self._estado["restam"] = restam

                if r["limiteDeUso"]:
                    # a Receita pediu para esperar; se ainda estiver bloqueada na volta, espera mais
                    self._esperar(espera)
                    espera = espera + 30 if r["processados"] == 0 else ESPERA_APOS_LIMITE
                    espera = min(espera, ESPERA_MAXIMA)
                    falhas_seguidas = 0
                elif r["processados"] == 0 and r["falhas"] > 0:
                    falhas_seguidas += 1
                    if falhas_seguidas >= FALHAS_SEGUIDAS_PARA_DESISTIR:
                        mensagem = "A Receita não está respondendo. Tente de novo mais tarde; o que já foi conferido ficou gravado."
                        break
                    self._esperar(10)
                else:
                    falhas_seguidas = 0
                    espera = ESPERA_APOS_LIMITE
            else:
                mensagem = "Parado. O que já foi conferido ficou gravado."
        except Exception:  # nunca deixar a tarefa de fundo morrer em silêncio
            log.exception("Falha na conferência em segundo plano")
            mensagem = "Deu um erro inesperado. O que já foi conferido ficou gravado; é só iniciar de novo."
        finally:
            self._atualizar(rodando=False, aguardandoAte=None, esperaSegundos=0,
                            terminouEm=_datetime.utcnow().isoformat(), mensagem=mensagem)


def _fabrica_padrao():
    from ..database import SessaoLocal
    return SessaoLocal()


# instância única do serviço (os testes trocam por uma própria)
conferencia = ConferenciaEmSegundoPlano(_fabrica_padrao)
