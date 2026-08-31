"""Pacote de atualização gerado a partir do banco mestre.

O banco_mestre.db tem 139 MB e vive na máquina do escritório. Mandar isso para
um serviço de plano gratuito é pedir problema — e é desnecessário, porque só
uma fatia pequena interessa: a carteira agregada, o histórico por produto e o
de-para de código do ERP. Isso dá poucos MB comprimidos.

Então o fluxo é: um clique local lê o banco mestre e escreve este pacote; o
pacote é que sobe pela tela. Ninguém precisa lidar com senha de banco.

Formato: JSON comprimido com gzip. Simples de gerar, simples de ler, e o
"versao" permite recusar um arquivo de formato antigo com mensagem clara em
vez de estourar no meio da importação.
"""
from __future__ import annotations

import gzip
import json
from datetime import date

VERSAO = 1


class PacoteInvalido(Exception):
    """Arquivo que não é um pacote de atualização válido."""


def _json_padrao(valor):
    if isinstance(valor, date):
        return valor.isoformat()
    raise TypeError(f"Tipo não serializável: {type(valor)}")


def escrever(caminho: str, *, carteira: list[dict], historico: list[dict], depara: dict[str, str],
             nomes: dict[str, str] | None = None) -> int:
    """Grava o pacote e devolve o tamanho em bytes."""
    conteudo = {
        "versao": VERSAO,
        "gerado_em": date.today().isoformat(),
        "carteira": carteira,
        "historico": historico,
        "depara": depara,
        "nomes": nomes or {},
    }
    bruto = json.dumps(conteudo, default=_json_padrao, ensure_ascii=False).encode("utf-8")
    with gzip.open(caminho, "wb", compresslevel=9) as arquivo:
        arquivo.write(bruto)
    import os
    return os.path.getsize(caminho)


def _data(valor) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def ler(conteudo: bytes) -> dict:
    """Lê o pacote enviado pela tela, com erro amigável para arquivo errado."""
    try:
        bruto = gzip.decompress(conteudo)
    except (OSError, EOFError) as erro:
        raise PacoteInvalido(
            "Esse arquivo não é um pacote de atualização. Gere um novo com o "
            "atalho 'Preparar pacote do banco mestre' e envie o arquivo .ppg."
        ) from erro

    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as erro:
        raise PacoteInvalido("O pacote está corrompido. Gere um novo e tente de novo.") from erro

    if not isinstance(dados, dict) or "carteira" not in dados:
        raise PacoteInvalido("O pacote não tem o conteúdo esperado. Gere um novo.")

    versao = dados.get("versao")
    if versao != VERSAO:
        raise PacoteInvalido(
            f"Esse pacote é de uma versão antiga do sistema (versão {versao}). "
            "Gere um novo pacote e envie de novo."
        )

    for registro in dados["carteira"]:
        registro["primeira_compra"] = _data(registro.get("primeira_compra"))
        registro["ultima_compra"] = _data(registro.get("ultima_compra"))
    for registro in dados.get("historico", []):
        registro["ultima_compra"] = _data(registro.get("ultima_compra"))

    return dados
