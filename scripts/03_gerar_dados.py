#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
03 - Gera o clientes.json consumido pela plataforma.
Lê a base mestra + o cache de geocodificação (funciona mesmo com a geo
ainda em andamento) e exporta só os clientes que já têm coordenadas.
"""
import os
import json
import math
import pandas as pd

import re
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(BASE_DIR, "saida")
CSV = os.path.join(SAIDA, "base_mestra.csv")
CACHE = os.path.join(SAIDA, "geo_cache.json")
CNPJ_CACHE = os.path.join(SAIDA, "cnpj_cache.json")
OUT = os.path.join(BASE_DIR, "app", "public", "clientes.json")


# classifica porte da Receita num rótulo curto e ordenável
def classificar_porte(porte, capital):
    p = (porte or "").upper()
    cap = capital or 0
    if "MICRO" in p or "MEI" in p:
        base = "Micro"
    elif "PEQUENO" in p:
        base = "Pequena"
    else:
        base = "Média/Grande"
    # capital social refina o topo
    if cap >= 1_000_000:
        base = "Grande"
    elif cap >= 100_000 and base == "Média/Grande":
        base = "Média"
    return base


def main():
    df = pd.read_csv(CSV, dtype={"cep": str})
    df["cep"] = df["cep"].fillna("").astype(str)

    # aplica cache de geo (recria a mesma chave do script 02)
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            cache = json.load(f)
    key = (
        df["endereco"].fillna("").str.upper().str.strip() + "|" +
        df["cidade"].fillna("").str.upper().str.strip() + "|" +
        df["uf"].fillna("").str.upper().str.strip()
    )
    df["lat"] = key.map(lambda k: (cache.get(k) or {}).get("lat"))
    df["lng"] = key.map(lambda k: (cache.get(k) or {}).get("lng"))
    df["geo_status"] = key.map(lambda k: (cache.get(k) or {}).get("status"))

    # dados de tamanho da empresa (porte/capital) por CNPJ
    cnpjc = {}
    if os.path.exists(CNPJ_CACHE):
        with open(CNPJ_CACHE) as f:
            cnpjc = json.load(f)

    def digitos(s):
        return re.sub(r"\D", "", str(s or ""))

    com_geo = df[df["lat"].notna()].copy()

    def val(x, default=None):
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return x

    registros = []
    for i, r in com_geo.reset_index(drop=True).iterrows():
        info = cnpjc.get(digitos(r["cnpj"]), {})
        capital = info.get("capital_social")
        cad = r["cadencia_dias"]
        registros.append({
            "id": int(i),
            "cnpj": val(r["cnpj"], ""),
            "nome": val(r["razao_social"], ""),
            "endereco": val(r["endereco"], ""),
            "bairro": val(r["bairro"], ""),
            "cidade": val(r["cidade"], ""),
            "uf": val(r["uf"], ""),
            "lat": round(float(r["lat"]), 6),
            "lng": round(float(r["lng"]), 6),
            "geo": val(r["geo_status"], ""),
            "faixa": val(r["faixa"], ""),
            "emRisco": bool(r["em_risco"]),
            "fat": round(float(val(r["fat_total"], 0)), 2),
            "compras": int(val(r["no_compras"], 0)),
            "ticket": round(float(val(r["ticket_medio"], 0)), 2),
            "recencia": int(val(r["recencia_dias"], 0)) if not pd.isna(r["recencia_dias"]) else None,
            "cadencia": int(cad) if not pd.isna(cad) else None,
            "ultimaCompra": str(val(r["ultima_compra"], ""))[:10],
            "porte": classificar_porte(info.get("porte"), capital) if info else None,
            "capital": round(float(capital), 2) if capital else None,
            "cnae": info.get("cnae") or None,
            "telefone": info.get("telefone") or None,
            "email": info.get("email") or None,
            "R": int(val(r["R"], 0)),
            "F": int(val(r["F"], 0)),
            "M": int(val(r["M"], 0)),
            "score": int(val(r["rfm_score"], 0)),
        })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False)

    print(f"Exportados {len(registros)} clientes com coordenadas -> {OUT}")
    print("Por faixa:", com_geo["faixa"].value_counts().to_dict())
    prec = com_geo["geo_status"].value_counts().to_dict()
    print("Precisão geo:", prec)


if __name__ == "__main__":
    main()
