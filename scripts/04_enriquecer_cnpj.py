#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
04 - Enriquece os CNPJs da carteira com dados de TAMANHO da empresa
(porte + capital social + CNAE) via BrasilAPI. Cache incremental.
"""
import os
import re
import json
import time
import requests
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(BASE_DIR, "saida")
CSV = os.path.join(SAIDA, "base_mestra.csv")
CACHE = os.path.join(SAIDA, "cnpj_cache.json")
LOG = os.path.join(SAIDA, "cnpj_log.txt")
UA = {"User-Agent": "fratelli-representacao/1.0"}


def log(m):
    with open(LOG, "a") as f:
        f.write(m + "\n")
    print(m, flush=True)


def digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def main():
    df = pd.read_csv(CSV)
    cnpjs = [c for c in df["cnpj"].dropna().unique() if len(digitos(c)) == 14]

    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            cache = json.load(f)

    pendentes = [c for c in cnpjs if digitos(c) not in cache]
    open(LOG, "w").close()
    log(f"CNPJs: {len(cnpjs)} | em cache: {len(cnpjs)-len(pendentes)} | a buscar: {len(pendentes)}")
    log(f"Tempo estimado: ~{len(pendentes)*0.6/60:.0f} min")

    for i, cnpj in enumerate(pendentes, 1):
        d = digitos(cnpj)
        try:
            r = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{d}", headers=UA, timeout=20)
            if r.status_code == 200:
                j = r.json()
                cache[d] = {
                    "porte": (j.get("porte") or j.get("descricao_porte") or "").strip(),
                    "capital_social": j.get("capital_social"),
                    "cnae": (j.get("cnae_fiscal_descricao") or "").strip(),
                    "abertura": (j.get("data_inicio_atividade") or "")[:10],
                    "telefone": (j.get("ddd_telefone_1") or "").strip(),
                    "telefone2": (j.get("ddd_telefone_2") or "").strip(),
                    "email": (j.get("email") or "").strip().lower(),
                }
            else:
                cache[d] = {"porte": "", "capital_social": None, "cnae": "", "abertura": ""}
        except Exception as e:
            cache[d] = {"porte": "", "capital_social": None, "cnae": "", "abertura": ""}
            log(f"  erro {d}: {e}")
        time.sleep(0.4)
        if i % 50 == 0:
            with open(CACHE, "w") as f:
                json.dump(cache, f, ensure_ascii=False)
            log(f"  progresso {i}/{len(pendentes)} ({100*i/len(pendentes):.0f}%)")

    with open(CACHE, "w") as f:
        json.dump(cache, f, ensure_ascii=False)

    # relatorio de portes
    portes = {}
    for v in cache.values():
        p = v.get("porte") or "(vazio)"
        portes[p] = portes.get(p, 0) + 1
    log("\n===== PORTE =====")
    for k, n in sorted(portes.items(), key=lambda x: -x[1]):
        log(f"  {k}: {n}")
    caps = [v["capital_social"] for v in cache.values() if v.get("capital_social")]
    if caps:
        caps.sort()
        log(f"\nCapital social: mediana R$ {caps[len(caps)//2]:,.0f} | max R$ {max(caps):,.0f}")
    log("CONCLUIDO.")


if __name__ == "__main__":
    main()
