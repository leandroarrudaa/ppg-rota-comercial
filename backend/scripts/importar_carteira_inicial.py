#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga/atualização da carteira antiga no banco do app.

Lê saida/base_mestra.csv + caches de geocodificação e CNPJ (mesma lógica do
scripts/03_gerar_dados.py) e faz UPSERT por CNPJ:
  - cria clientes que não existem;
  - atualiza SÓ as colunas de RFM/faturamento/endereço dos que já existem;
  - NUNCA toca nos campos donos do app (status, aceita_visita, contato_*).

Pode ser rodado quantas vezes for preciso (reimportação segura).
Uso:  python backend/scripts/importar_carteira_inicial.py
"""
import json
import math
import os
import sys
from datetime import date

import pandas as pd

# permite importar app.* rodando o script de qualquer diretório
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from app.database import Base, SessaoLocal, engine  # noqa: E402
from app.services.cnpj import normalizar_cnpj  # noqa: E402
from app.services.importacao import upsert_clientes_antigos  # noqa: E402

RAIZ = os.path.dirname(BACKEND_DIR)  # pasta ppg-rota-comercial
SAIDA = os.path.join(RAIZ, "saida")
CSV = os.path.join(SAIDA, "base_mestra.csv")
GEO_CACHE = os.path.join(SAIDA, "geo_cache.json")
CNPJ_CACHE = os.path.join(SAIDA, "cnpj_cache.json")


def _val(x, padrao=None):
    """NaN do pandas -> None/padrão."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return padrao
    return x


def _int(x):
    v = _val(x)
    return int(v) if v is not None else None


def _float(x):
    v = _val(x)
    return float(v) if v is not None else None


def _data(x) -> date | None:
    s = str(_val(x, ""))[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def classificar_porte(porte, capital):
    """Mesma regra do 03_gerar_dados.py: porte da Receita refinado pelo capital."""
    p = (porte or "").upper()
    cap = capital or 0
    if "MICRO" in p or "MEI" in p:
        base = "Micro"
    elif "PEQUENO" in p:
        base = "Pequena"
    else:
        base = "Média/Grande"
    if cap >= 1_000_000:
        base = "Grande"
    elif cap >= 100_000 and base == "Média/Grande":
        base = "Média"
    return base


def montar_registros() -> list[dict]:
    """Replica a junção do 03_gerar_dados.py: base + geo_cache + cnpj_cache."""
    df = pd.read_csv(CSV, dtype={"cep": str})
    df["cep"] = df["cep"].fillna("").astype(str)

    geo = {}
    if os.path.exists(GEO_CACHE):
        with open(GEO_CACHE, encoding="utf-8") as f:
            geo = json.load(f)
    chave = (
        df["endereco"].fillna("").str.upper().str.strip() + "|" +
        df["cidade"].fillna("").str.upper().str.strip() + "|" +
        df["uf"].fillna("").str.upper().str.strip()
    )
    df["lat"] = chave.map(lambda k: (geo.get(k) or {}).get("lat"))
    df["lng"] = chave.map(lambda k: (geo.get(k) or {}).get("lng"))
    df["geo_status"] = chave.map(lambda k: (geo.get(k) or {}).get("status"))

    cnpjc = {}
    if os.path.exists(CNPJ_CACHE):
        with open(CNPJ_CACHE, encoding="utf-8") as f:
            cnpjc = json.load(f)

    registros = []
    for _, r in df.iterrows():
        info = cnpjc.get(normalizar_cnpj(r["cnpj"]), {})
        capital = info.get("capital_social")
        lat = _float(r["lat"])
        registros.append({
            "cnpj": _val(r["cnpj"], ""),
            "nome": _val(r["razao_social"], ""),
            "endereco": _val(r["endereco"], "") or None,
            "bairro": _val(r["bairro"], "") or None,
            "cep": (str(_val(r["cep"], "")).strip() or None),
            "cidade": _val(r["cidade"], "") or None,
            "uf": _val(r["uf"], "") or None,
            "lat": lat,
            "lng": _float(r["lng"]),
            "geo_status": _val(r["geo_status"]) if lat is not None else "falhou",
            "faixa": _val(r["faixa"]),
            "em_risco": bool(r["em_risco"]),
            "fat_total": _float(r["fat_total"]),
            "no_compras": _int(r["no_compras"]),
            "ticket_medio": _float(r["ticket_medio"]),
            "recencia_dias": _int(r["recencia_dias"]),
            "cadencia_dias": _int(r["cadencia_dias"]),
            "ultima_compra": _data(r["ultima_compra"]),
            "r": _int(r["R"]),
            "f": _int(r["F"]),
            "m": _int(r["M"]),
            "rfm_score": _int(r["rfm_score"]),
            "porte": classificar_porte(info.get("porte"), capital) if info else None,
            "capital_social": _float(capital),
            "cnae": info.get("cnae") or None,
            "telefone": info.get("telefone") or None,
            "email": info.get("email") or None,
        })
    return registros


def main():
    Base.metadata.create_all(bind=engine)
    registros = montar_registros()
    print(f"Registros na base mestra: {len(registros)}")

    db = SessaoLocal()
    try:
        resultado = upsert_clientes_antigos(db, registros)
        db.commit()
        from app.models import Cliente  # import local só pra contagem final
        total = db.query(Cliente).count()
        com_geo = db.query(Cliente).filter(Cliente.lat.isnot(None)).count()
        print(f"Criados: {resultado['criados']} | Atualizados: {resultado['atualizados']}")
        print(f"Total no banco: {total} | Com coordenadas: {com_geo}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
