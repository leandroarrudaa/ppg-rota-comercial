#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
05 - Consulta a situação cadastral (ativa/baixada), o endereço atual, a
natureza jurídica, o MEI, os sócios e os CNAEs secundários de cada CNPJ da
carteira, via BrasilAPI. Só LÊ o banco do app; grava tudo num cache JSON
(saida/situacao_cache.json), incremental e retomável: pode interromper e
rodar de novo que ele continua de onde parou.

Uso:  python scripts/05_consultar_situacao_cnpj.py [--limite N] [--refazer]
"""
import argparse
import json
import os
import re
import sqlite3
import time

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANCO = os.path.join(BASE_DIR, "backend", "rota.db")
CACHE = os.path.join(BASE_DIR, "saida", "situacao_cache.json")
URL = "https://brasilapi.com.br/api/cnpj/v1/{}"
UA = {"User-Agent": "ppg-rota-comercial/1.0"}
PAUSA = 0.4          # não martela uma API pública gratuita
MAX_TENTATIVAS = 4


def digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def carregar_cnpjs():
    """CNPJs de 14 dígitos da carteira (banco aberto só para leitura)."""
    con = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    try:
        linhas = con.execute("select cnpj from clientes where cnpj is not null").fetchall()
    finally:
        con.close()
    vistos, saida = set(), []
    for (c,) in linhas:
        d = digitos(c)
        if len(d) == 14 and d not in vistos:
            vistos.add(d)
            saida.append(d)
    return saida


def resumir(j):
    """Só o que importa pra decidir se vale a visita."""
    socios = [(s.get("nome_socio") or "").strip() for s in (j.get("qsa") or [])]
    return {
        "consulta": "ok",
        "situacao": (j.get("descricao_situacao_cadastral") or "").strip(),
        "data_situacao": (j.get("data_situacao_cadastral") or "")[:10],
        "natureza_juridica": (j.get("natureza_juridica") or "").strip(),
        "mei": bool(j.get("opcao_pelo_mei")),
        "simples": bool(j.get("opcao_pelo_simples")),
        "matriz": j.get("identificador_matriz_filial") == 1,
        "nome_fantasia": (j.get("nome_fantasia") or "").strip(),
        "n_socios": len(socios),
        "socios": [s for s in socios if s][:3],
        "cnaes_secundarios": [
            (c.get("descricao") or "").strip() for c in (j.get("cnaes_secundarios") or [])
        ][:10],
        "logradouro": " ".join(
            x for x in [(j.get("descricao_tipo_de_logradouro") or ""), (j.get("logradouro") or "")] if x
        ).strip(),
        "numero": (j.get("numero") or "").strip(),
        "bairro": (j.get("bairro") or "").strip(),
        "cep": (j.get("cep") or "").strip(),
        "municipio": (j.get("municipio") or "").strip(),
        "uf": (j.get("uf") or "").strip(),
    }


def consultar(d):
    """Devolve o resumo, ou {'consulta': 'nao_encontrado'/'erro'}."""
    for tentativa in range(MAX_TENTATIVAS):
        try:
            r = requests.get(URL.format(d), headers=UA, timeout=20)
        except requests.RequestException:
            time.sleep(2 * (tentativa + 1))
            continue
        if r.status_code == 200:
            return resumir(r.json())
        if r.status_code == 404:
            return {"consulta": "nao_encontrado"}
        # 429 (limite de uso) e 5xx: espera mais e tenta de novo
        time.sleep(3 * (tentativa + 1))
    return {"consulta": "erro"}


def salvar(cache):
    tmp = CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0, help="consulta só N CNPJs (teste)")
    ap.add_argument("--refazer", action="store_true", help="refaz também os que deram erro")
    args = ap.parse_args()

    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)

    todos = carregar_cnpjs()
    pendentes = [d for d in todos if d not in cache or (args.refazer and cache[d].get("consulta") == "erro")]
    ja_consultados = len(todos) - len(pendentes)
    if args.limite:
        pendentes = pendentes[: args.limite]
    print(f"CNPJs: {len(todos)} | ja consultados: {ja_consultados} | a consultar agora: {len(pendentes)}", flush=True)

    for i, d in enumerate(pendentes, 1):
        cache[d] = consultar(d)
        time.sleep(PAUSA)
        if i % 25 == 0:
            salvar(cache)
            print(f"  progresso {i}/{len(pendentes)}", flush=True)
    salvar(cache)

    cont = {}
    for d in todos:
        k = cache.get(d, {}).get("situacao") or cache.get(d, {}).get("consulta", "sem consulta")
        cont[k] = cont.get(k, 0) + 1
    print("Resumo:", cont, flush=True)


if __name__ == "__main__":
    main()
